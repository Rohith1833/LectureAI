import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  listFinalizedVersions,
  getDocumentSelectableContainers,
} from "@/services/knowledgeService";
import { artifactService } from "@/services/artifactService";
import type { KnowledgeVersion } from "@/types/knowledge";
import {
  ArtifactType,
  ArtifactStatus,
  type ArtifactJobRead,
  type SelectableContainersData,
} from "@/types/artifact";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  Download,
  ExternalLink,
  Layers,
  Loader2,
  Search,
  BookOpen,
} from "lucide-react";
import InteractiveStudyModal from "@/components/study/InteractiveStudyModal";

// Active states that require polling
const ACTIVE_STATUSES: ArtifactStatus[] = [
  ArtifactStatus.PENDING,
  ArtifactStatus.PLANNING,
  ArtifactStatus.RENDERING,
];

const TERMINAL_STATUSES: ArtifactStatus[] = [
  ArtifactStatus.COMPLETED,
  ArtifactStatus.FAILED,
];

const AUDIENCE_LEVELS = [
  { value: "general", label: "General" },
  { value: "undergraduate", label: "Undergraduate" },
  { value: "graduate", label: "Graduate" },
  { value: "expert", label: "Expert" },
] as const;

const DEPTH_OPTIONS = [
  { value: "overview", label: "Overview" },
  { value: "standard", label: "Standard" },
  { value: "detailed", label: "Detailed" },
] as const;

function formatBackendError(err: unknown): string {
  if (err && typeof err === "object" && "response" in err) {
    const resp = (err as { response?: { data?: Record<string, unknown>; status?: number; statusText?: string } }).response;
    if (resp?.data) {
      const data = resp.data;
      if (typeof data.detail === "string") return data.detail;
      if (Array.isArray(data.detail)) {
        return data.detail.map((d: unknown) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: string }).msg) : JSON.stringify(d))).join("; ");
      }
      if (typeof data.message === "string") return data.message;
    }
    if (resp?.statusText) return `Error ${resp.status}: ${resp.statusText}`;
  }
  if (err instanceof Error) return err.message;
  return "An unexpected error occurred.";
}

export default function ArtifactWorkspacePage() {
  // Route param is Document.id — NOT upload_id
  const { id: documentId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isMountedRef = useRef(true);

  // --- Knowledge Version & Container State ---
  const [version, setVersion] = useState<KnowledgeVersion | null>(null);
  const [versionLoading, setVersionLoading] = useState(true);
  const [versionError, setVersionError] = useState<string | null>(null);

  const [containersData, setContainersData] = useState<SelectableContainersData | null>(null);
  const [containersLoading, setContainersLoading] = useState(false);
  const [containersError, setContainersError] = useState<string | null>(null);

  // --- Selection State ---
  // Intentional initial selection: empty selection
  const [selectedContainerIds, setSelectedContainerIds] = useState<string[]>([]);
  const [containerSearch, setContainerSearch] = useState("");

  // --- Configuration State ---
  const [artifactType, setArtifactType] = useState<ArtifactType>(ArtifactType.PPTX);
  const [audienceLevel, setAudienceLevel] = useState("general");
  const [depth, setDepth] = useState("standard");
  const [includeExamples, setIncludeExamples] = useState(true);
  const [includeQuestions, setIncludeQuestions] = useState(true);

  // --- Job & Submission State ---
  const [jobs, setJobs] = useState<ArtifactJobRead[]>([]);
  const [pollingJobId, setPollingJobId] = useState<string | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [studyingJob, setStudyingJob] = useState<ArtifactJobRead | null>(null);

  // Keep track of mounted state
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // --- Load finalized knowledge version and selectable containers ---
  useEffect(() => {
    if (!documentId) return;

    // Clear stale selections and errors on document change
    setSelectedContainerIds([]);
    setContainerSearch("");
    setGenerateError(null);
    setVersionError(null);
    setContainersError(null);
    setContainersData(null);
    setPollingJobId(null);
    setVersionLoading(true);

    let active = true;

    // Fetch version list and selectable containers in parallel
    Promise.all([
      listFinalizedVersions(documentId),
      getDocumentSelectableContainers(documentId).catch(() => {
        // May 404 if no finalized version yet
        return null;
      }),
    ])
      .then(([versions, cData]) => {
        if (!active || !isMountedRef.current) return;

        if (versions.length > 0) {
          setVersion(versions[0]);
          if (cData) {
            setContainersData(cData);
          }
        } else {
          setVersion(null);
          setVersionError(
            "No finalized knowledge version available for this document. Complete the Academic Review process first."
          );
        }
      })
      .catch((err) => {
        if (!active || !isMountedRef.current) return;
        setVersionError(formatBackendError(err) || "Failed to load knowledge versions.");
      })
      .finally(() => {
        if (active && isMountedRef.current) {
          setVersionLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [documentId]);

  // If version loaded but containersData not loaded yet, fetch selectable containers for version
  useEffect(() => {
    if (!version || containersData) return;

    let active = true;
    setContainersLoading(true);
    setContainersError(null);

    getDocumentSelectableContainers(version.document_id || documentId!)
      .then((data) => {
        if (active && isMountedRef.current) {
          setContainersData(data);
        }
      })
      .catch((err) => {
        if (active && isMountedRef.current) {
          setContainersError(
            formatBackendError(err) || "Failed to load selectable containers."
          );
        }
      })
      .finally(() => {
        if (active && isMountedRef.current) {
          setContainersLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [version, containersData, documentId]);

  // --- Load existing jobs for document upload_id ---
  const loadJobs = useCallback(async (uploadId: string) => {
    try {
      const data = await artifactService.listJobs(uploadId);
      if (!isMountedRef.current) return;
      setJobs(data);
      const activeJob = data.find((j) =>
        ACTIVE_STATUSES.includes(j.status as ArtifactStatus)
      );
      if (activeJob) {
        setPollingJobId(activeJob.id);
      }
    } catch {
      // Silently handle — no existing jobs is a normal state
    }
  }, []);

  useEffect(() => {
    if (version) {
      loadJobs(version.upload_id);
    }
  }, [version, loadJobs]);

  // --- Real-time WebSocket connection for job status ---
  useEffect(() => {
    if (!version) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    let wsBaseUrl = "";
    
    const apiBaseUrl = import.meta.env.VITE_API_URL || "/api/v1";
    if (apiBaseUrl.startsWith("http")) {
      wsBaseUrl = apiBaseUrl.replace(/^http/, "ws");
    } else {
      wsBaseUrl = `${protocol}//${window.location.host}${apiBaseUrl}`;
    }

    const wsUrl = `${wsBaseUrl}/artifacts/ws/${version.upload_id}`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      if (!isMountedRef.current) return;
      try {
        const data = JSON.parse(event.data);
        if (data.type === "job_update" && data.job) {
          const updated = data.job;
          setJobs((prev) => {
            const exists = prev.find((j) => j.id === updated.id);
            if (exists) {
              return prev.map((j) => (j.id === updated.id ? updated : j));
            } else {
              return [updated, ...prev];
            }
          });
          
          if (TERMINAL_STATUSES.includes(updated.status as ArtifactStatus)) {
            setPollingJobId((prev) => (prev === updated.id ? null : prev));
          }
        }
      } catch (err) {
        console.error("Failed to parse WebSocket message", err);
      }
    };

    ws.onerror = (err) => {
      console.warn("WebSocket error:", err);
    };

    return () => {
      ws.close();
    };
  }, [version]);

  // --- Polling fallback for active job ---
  useEffect(() => {
    if (!pollingJobId) return;

    let cancelled = false;

    const poll = async () => {
      try {
        const updated = await artifactService.getJobStatus(pollingJobId);
        if (cancelled || !isMountedRef.current) return;

        setJobs((prev) => {
          const exists = prev.find((j) => j.id === updated.id);
          if (exists) {
            return prev.map((j) => (j.id === updated.id ? updated : j));
          } else {
            return [updated, ...prev];
          }
        });

        if (TERMINAL_STATUSES.includes(updated.status as ArtifactStatus)) {
          setPollingJobId(null);
        }
      } catch {
        // Transient network error: keep polling without failing the job
      }
    };

    const interval = setInterval(poll, 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [pollingJobId]);

  // --- Filtered selectable containers ---
  const allContainers = useMemo(
    () => containersData?.containers || [],
    [containersData]
  );

  const filteredContainers = useMemo(() => {
    const q = containerSearch.trim().toLowerCase();
    if (!q) return allContainers;
    return allContainers.filter((c) => c.title.toLowerCase().includes(q));
  }, [allContainers, containerSearch]);

  const handleToggleContainer = (containerId: string) => {
    setSelectedContainerIds((prev) =>
      prev.includes(containerId)
        ? prev.filter((id) => id !== containerId)
        : [...prev, containerId]
    );
  };

  const handleSelectAll = () => {
    // If filtered, toggle all filtered items; otherwise toggle all items
    const targetIds = filteredContainers.map((c) => c.id);
    setSelectedContainerIds((prev) => {
      const nextSet = new Set(prev);
      targetIds.forEach((id) => nextSet.add(id));
      return Array.from(nextSet);
    });
  };

  const handleClearSelection = () => {
    setSelectedContainerIds([]);
  };

  // --- Generate handler ---
  const handleGenerate = async () => {
    if (!version || isSubmitting || pollingJobId) return;

    // Validate that at least one container is selected
    if (selectedContainerIds.length === 0) {
      setGenerateError("Please select at least one unit/chapter before generating.");
      return;
    }

    setGenerateError(null);
    setIsSubmitting(true);

    try {
      const newJob = await artifactService.generateArtifact({
        upload_id: version.upload_id, // Authoritative upload_id from finalized version
        knowledge_version_id: version.id,
        artifact_type: artifactType,
        config: {
          audience_level: audienceLevel,
          depth: depth,
          selected_unit_ids: selectedContainerIds, // Real entity IDs
          include_examples: includeExamples,
          include_questions: includeQuestions,
        },
      });

      if (isMountedRef.current) {
        setJobs((prev) => [newJob, ...prev]);
        setPollingJobId(newJob.id);
      }
    } catch (err: unknown) {
      if (isMountedRef.current) {
        setGenerateError(formatBackendError(err));
      }
    } finally {
      if (isMountedRef.current) {
        setIsSubmitting(false);
      }
    }
  };

  // --- Status label helper ---
  const statusLabel = (status: ArtifactStatus): string => {
    switch (status) {
      case ArtifactStatus.PENDING:
        return "Pending";
      case ArtifactStatus.PLANNING:
        return "Planning content…";
      case ArtifactStatus.RENDERING:
        return "Rendering artifact…";
      case ArtifactStatus.COMPLETED:
        return "Completed";
      case ArtifactStatus.FAILED:
        return "Failed";
      default:
        return String(status);
    }
  };

  const statusColor = (status: ArtifactStatus): string => {
    switch (status) {
      case ArtifactStatus.COMPLETED:
        return "bg-green-100 text-green-800 dark:bg-green-950/40 dark:text-green-400";
      case ArtifactStatus.FAILED:
        return "bg-red-100 text-red-800 dark:bg-red-950/40 dark:text-red-400";
      default:
        return "bg-blue-100 text-blue-800 dark:bg-blue-950/40 dark:text-blue-400 animate-pulse";
    }
  };

  const containerMode = containersData?.container_mode || "UNITS";
  const isReviewRequired = containerMode === "REVIEW_REQUIRED";
  const isChaptersMode = containerMode === "CHAPTERS";

  // --- Loading screen ---
  if (versionLoading) {
    return (
      <div
        className="flex justify-center items-center h-full p-8"
        data-testid="loading-spinner"
      >
        <div className="flex flex-col items-center gap-3">
          <div className="animate-spin h-8 w-8 border-4 border-indigo-600 rounded-full border-t-transparent" />
          <span className="text-sm text-gray-500">Loading finalized knowledge version…</span>
        </div>
      </div>
    );
  }

  // --- No finalized version ---
  if (versionError || !version) {
    return (
      <div className="p-8 max-w-2xl mx-auto">
        <div className="bg-red-50 border border-red-200 text-red-700 p-5 rounded-xl space-y-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="size-5 shrink-0" />
            <h3 className="font-semibold text-base">Cannot Generate Artifacts</h3>
          </div>
          <p data-testid="version-error" className="text-sm">
            {versionError ||
              "No finalized knowledge version available for this document. Complete the Academic Review process first."}
          </p>
          <div className="pt-2 flex gap-3">
            <button
              onClick={() => navigate(`/documents/${documentId}`)}
              className="px-4 py-2 bg-white text-red-700 border border-red-200 rounded-lg shadow-sm hover:bg-gray-50 text-sm font-medium cursor-pointer"
            >
              Back to Document
            </button>
            <button
              onClick={() => navigate("/upload")}
              className="px-4 py-2 bg-red-600 text-white rounded-lg shadow-sm hover:bg-red-700 text-sm font-medium cursor-pointer"
            >
              Upload Textbook
            </button>
          </div>
        </div>
      </div>
    );
  }

  const isGenerating = isSubmitting || !!pollingJobId;

  return (
    <div className="flex h-full flex-col bg-gray-50 overflow-hidden">
      {/* Header */}
      <header className="bg-white border-b px-6 py-4 flex items-center justify-between shadow-sm z-10">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">
            Artifact Generation Workspace
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Generate presentation decks from your textbook’s approved academic structure
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(`/academic/review/${version.upload_id}`)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 cursor-pointer"
          >
            <BookOpen className="size-3.5" /> Academic Review
          </button>
          <button
            onClick={() => navigate(`/documents/${documentId}`)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 cursor-pointer"
          >
            <ArrowLeft className="size-3.5" /> Document Details
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-auto p-6 max-w-5xl mx-auto w-full space-y-6">
        {/* Knowledge Version Identity Banner */}
        <div
          className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden"
          data-testid="version-info"
        >
          <div className="p-4 border-b border-gray-200 bg-emerald-50/70 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-emerald-950 flex items-center gap-2">
              <Check className="size-4 text-emerald-600" /> Finalized Knowledge Version
            </h2>
            {containersData?.approval_version && (
              <span className="bg-emerald-100 text-emerald-800 text-xs px-2 py-0.5 rounded font-bold font-mono">
                {containersData.approval_version}
              </span>
            )}
          </div>
          <div className="p-4 grid grid-cols-1 sm:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-gray-500 block text-xs font-medium uppercase tracking-wide">
                Version ID
              </span>
              <span
                className="font-mono text-gray-800 text-xs break-all"
                data-testid="version-id"
              >
                {version.id}
              </span>
            </div>
            <div>
              <span className="text-gray-500 block text-xs font-medium uppercase tracking-wide">
                Status
              </span>
              <span
                className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800"
                data-testid="version-status"
              >
                {version.status}
              </span>
            </div>
            <div>
              <span className="text-gray-500 block text-xs font-medium uppercase tracking-wide">
                Upload ID
              </span>
              <span
                className="font-mono text-gray-800 text-xs break-all"
                data-testid="version-upload-id"
              >
                {version.upload_id}
              </span>
            </div>
            <div>
              <span className="text-gray-500 block text-xs font-medium uppercase tracking-wide">
                Container Mode
              </span>
              <span
                className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold ${
                  isReviewRequired
                    ? "bg-amber-100 text-amber-800"
                    : isChaptersMode
                    ? "bg-blue-100 text-blue-800"
                    : "bg-purple-100 text-purple-800"
                }`}
                data-testid="container-mode-badge"
              >
                {containerMode}
              </span>
            </div>
          </div>
        </div>

        {/* REVIEW REQUIRED BANNER */}
        {isReviewRequired && (
          <div
            className="p-5 border border-amber-300 bg-amber-50 rounded-xl space-y-3"
            data-testid="review-required-banner"
          >
            <div className="flex items-start gap-3">
              <AlertTriangle className="size-5 text-amber-700 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <h3 className="font-semibold text-amber-900 text-sm">
                  Academic Review Required
                </h3>
                <p className="text-xs text-amber-800 leading-relaxed">
                  No selectable academic units or chapters were detected in this finalized knowledge version.
                  Please complete the academic review to classify containers before generating presentations.
                </p>
                {containersData?.diagnostics && containersData.diagnostics.length > 0 && (
                  <ul className="text-xs text-amber-800 list-disc list-inside mt-2 space-y-0.5">
                    {containersData.diagnostics.map((diag, idx) => (
                      <li key={idx}>{diag}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
            <div className="pt-2">
              <button
                onClick={() => navigate(`/academic/review/${version.upload_id}`)}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-semibold shadow-sm cursor-pointer"
              >
                Go to Academic Review <ExternalLink className="size-3.5" />
              </button>
            </div>
          </div>
        )}

        {/* CHAPTERS MODE NOTICE */}
        {isChaptersMode && (
          <div
            className="p-4 border border-blue-200 bg-blue-50/70 rounded-xl flex items-start gap-3"
            data-testid="chapters-mode-banner"
          >
            <Layers className="size-5 text-blue-700 shrink-0 mt-0.5" />
            <div className="space-y-0.5">
              <h4 className="font-semibold text-blue-900 text-xs">
                Chapters Mode Active
              </h4>
              <p className="text-xs text-blue-800 leading-relaxed">
                This textbook does not define separate syllabus units. Slides will be generated by chapter.
                Actual textbook chapter titles are preserved. Note that chapter numbers do not correspond to syllabus unit numbers.
              </p>
            </div>
          </div>
        )}

        {/* Selectable Container Selection Panel */}
        {!isReviewRequired && (
          <div
            className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden"
            data-testid="container-selection-panel"
          >
            <div className="p-5 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-gray-900">
                  {isChaptersMode ? "Select Chapters" : "Select Academic Units"}
                </h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  Select any single unit, any combination of units, or all available units.
                </p>
              </div>

              {/* Selected Count & Quick Actions */}
              <div className="flex items-center gap-2">
                <span
                  className="text-xs font-semibold text-gray-700 bg-gray-100 px-2.5 py-1 rounded-full"
                  data-testid="selected-count-badge"
                >
                  {selectedContainerIds.length} of {allContainers.length} selected
                </span>
                <button
                  type="button"
                  onClick={handleSelectAll}
                  disabled={isGenerating || allContainers.length === 0}
                  data-testid="select-all-button"
                  className="px-2.5 py-1 text-xs font-medium text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50 rounded border border-indigo-200 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {containerSearch.trim() ? "Select Filtered" : "Select All"}
                </button>
                <button
                  type="button"
                  onClick={handleClearSelection}
                  disabled={isGenerating || selectedContainerIds.length === 0}
                  data-testid="clear-selection-button"
                  className="px-2.5 py-1 text-xs font-medium text-gray-600 hover:text-gray-700 hover:bg-gray-100 rounded border border-gray-300 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Clear Selection
                </button>
              </div>
            </div>

            {/* Search filter for longer lists */}
            {allContainers.length >= 4 && (
              <div className="px-5 pt-3 pb-1 border-b border-gray-100 bg-gray-50/50 flex items-center gap-2">
                <Search className="size-4 text-gray-400 shrink-0" />
                <input
                  type="text"
                  placeholder={`Search ${isChaptersMode ? "chapters" : "units"} by title…`}
                  value={containerSearch}
                  onChange={(e) => setContainerSearch(e.target.value)}
                  disabled={isGenerating}
                  data-testid="container-search-input"
                  className="w-full text-xs py-1.5 px-2 bg-transparent border-0 focus:ring-0 focus:outline-none placeholder-gray-400"
                />
                {containerSearch && (
                  <button
                    onClick={() => setContainerSearch("")}
                    className="text-xs text-gray-400 hover:text-gray-600"
                  >
                    Clear
                  </button>
                )}
              </div>
            )}

            {/* Containers List */}
            <div className="p-5">
              {containersLoading ? (
                <div className="flex items-center justify-center p-6 text-xs text-gray-500 gap-2">
                  <Loader2 className="size-4 animate-spin text-indigo-600" />
                  Loading available {isChaptersMode ? "chapters" : "units"}…
                </div>
              ) : containersError ? (
                <div className="p-3 text-xs text-red-700 bg-red-50 border border-red-200 rounded-md">
                  {containersError}
                </div>
              ) : filteredContainers.length === 0 ? (
                <p className="text-xs text-gray-500 text-center py-4">
                  {containerSearch.trim()
                    ? "No matching units found."
                    : "No containers available in this finalized version."}
                </p>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="containers-list">
                  {filteredContainers.map((item) => {
                    const isSelected = selectedContainerIds.includes(item.id);
                    const hasValidPage =
                      item.source_page_start !== null &&
                      typeof item.source_page_start === "number" &&
                      item.source_page_start < 99999;

                    let pageLabel: string | null = null;
                    if (hasValidPage) {
                      if (
                        item.source_page_end !== null &&
                        typeof item.source_page_end === "number" &&
                        item.source_page_end > item.source_page_start! &&
                        item.source_page_end < 99999
                      ) {
                        pageLabel = `Pages ${item.source_page_start}–${item.source_page_end}`;
                      } else {
                        pageLabel = `Page ${item.source_page_start}`;
                      }
                    }

                    return (
                      <label
                        key={item.id}
                        htmlFor={`container-${item.id}`}
                        data-testid={`container-item-${item.id}`}
                        className={`flex items-start gap-3 p-3.5 rounded-lg border text-xs transition-all cursor-pointer select-none ${
                          isSelected
                            ? "border-indigo-500 bg-indigo-50/50 shadow-xs"
                            : "border-gray-200 bg-white hover:bg-gray-50/70"
                        } ${isGenerating ? "opacity-60 cursor-not-allowed" : ""}`}
                      >
                        <input
                          type="checkbox"
                          id={`container-${item.id}`}
                          data-testid={`container-checkbox-${item.id}`}
                          checked={isSelected}
                          onChange={() => handleToggleContainer(item.id)}
                          disabled={isGenerating}
                          className="mt-0.5 h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                        />
                        <div className="flex-1 min-w-0">
                          <span className="font-semibold text-gray-900 block truncate leading-snug">
                            {item.title}
                          </span>
                          <div className="flex items-center gap-2 mt-1 text-[11px] text-gray-500">
                            {pageLabel && (
                              <span
                                className="bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded font-mono"
                                data-testid={`container-pages-${item.id}`}
                              >
                                {pageLabel}
                              </span>
                            )}
                            {item.topic_count > 0 && (
                              <span className="text-gray-400">
                                {item.topic_count} topics
                              </span>
                            )}
                          </div>
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Configuration Panel */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
          <div className="p-5 border-b border-gray-200">
            <h2 className="text-base font-semibold text-gray-900">
              Generation Options
            </h2>
          </div>
          <div className="p-5 space-y-5">
            {/* Row 1: Artifact Type + Audience Level + Depth */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
              <div>
                <label
                  htmlFor="artifact-type"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Artifact Type
                </label>
                <select
                  id="artifact-type"
                  data-testid="artifact-type-select"
                  value={artifactType}
                  onChange={(e) => setArtifactType(e.target.value as ArtifactType)}
                  disabled={isGenerating}
                  className="w-full rounded-md border border-gray-300 py-2 px-3 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
                >
                  <option value={ArtifactType.PPTX}>PowerPoint (PPTX)</option>
                  <option value={ArtifactType.STUDY_GUIDE_MD}>Study Guide (Markdown)</option>
                  <option value={ArtifactType.FLASHCARDS_CSV}>Flashcards (CSV)</option>
                  <option value={ArtifactType.PRACTICE_EXAM_MD}>Practice Exam (Markdown)</option>
                </select>
              </div>

              <div>
                <label
                  htmlFor="audience-level"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Audience Level
                </label>
                <select
                  id="audience-level"
                  data-testid="audience-level-select"
                  value={audienceLevel}
                  onChange={(e) => setAudienceLevel(e.target.value)}
                  disabled={isGenerating}
                  className="w-full rounded-md border border-gray-300 py-2 px-3 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
                >
                  {AUDIENCE_LEVELS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label
                  htmlFor="depth"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Depth
                </label>
                <select
                  id="depth"
                  data-testid="depth-select"
                  value={depth}
                  onChange={(e) => setDepth(e.target.value)}
                  disabled={isGenerating}
                  className="w-full rounded-md border border-gray-300 py-2 px-3 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
                >
                  {DEPTH_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Row 2: Checkboxes */}
            <div className="flex flex-col sm:flex-row gap-5">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  data-testid="include-examples-checkbox"
                  checked={includeExamples}
                  onChange={(e) => setIncludeExamples(e.target.checked)}
                  disabled={isGenerating}
                  className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                />
                <span className="text-sm text-gray-700">Include Examples</span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  data-testid="include-questions-checkbox"
                  checked={includeQuestions}
                  onChange={(e) => setIncludeQuestions(e.target.checked)}
                  disabled={isGenerating}
                  className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                />
                <span className="text-sm text-gray-700">Include Questions</span>
              </label>
            </div>
          </div>

          {/* Generate Error Notice */}
          {generateError && (
            <div
              className="mx-5 mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700 space-y-1"
              data-testid="generate-error"
            >
              <div className="flex items-center gap-1.5 font-semibold">
                <AlertTriangle className="size-4 shrink-0 text-red-600" />
                Generation Error
              </div>
              <p className="text-xs leading-normal">{generateError}</p>
            </div>
          )}

          {/* Generate Button Footer */}
          <div className="p-5 bg-gray-50 border-t border-gray-200 flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="text-xs text-gray-500">
              {isReviewRequired ? (
                <span className="text-amber-700 font-medium">
                  Review is required before generation can begin.
                </span>
              ) : selectedContainerIds.length === 0 ? (
                <span className="text-gray-500">
                  Select at least one {isChaptersMode ? "chapter" : "unit"} to enable generation.
                </span>
              ) : (
                <span className="text-emerald-700 font-medium">
                  Ready to generate slides for {selectedContainerIds.length} {isChaptersMode ? "chapter(s)" : "unit(s)"}.
                </span>
              )}
            </div>

            <button
              onClick={handleGenerate}
              disabled={
                isReviewRequired ||
                isGenerating ||
                selectedContainerIds.length === 0
              }
              data-testid="generate-button"
              className="w-full sm:w-auto px-6 py-2.5 border border-transparent rounded-lg shadow-sm text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:bg-gray-300 disabled:text-gray-500 disabled:cursor-not-allowed transition-colors cursor-pointer"
            >
              {isSubmitting ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="size-4 animate-spin" /> Starting Generation…
                </span>
              ) : pollingJobId ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="size-4 animate-spin" /> Processing…
                </span>
              ) : (
                "Generate Presentation (.pptx)"
              )}
            </button>
          </div>
        </div>

        {/* Generation History */}
        {jobs.length > 0 && (
          <div
            className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden"
            data-testid="job-history"
          >
            <div className="p-5 border-b border-gray-200 flex items-center justify-between">
              <h2 className="text-base font-semibold text-gray-900">
                Generation History
              </h2>
              <span className="text-xs text-gray-500">
                {jobs.length} total {jobs.length === 1 ? "run" : "runs"}
              </span>
            </div>
            <ul className="divide-y divide-gray-200">
              {jobs.map((job) => {
                const isJobCompleted = job.status === ArtifactStatus.COMPLETED;
                const isJobFailed = job.status === ArtifactStatus.FAILED;
                const isJobActive = ACTIVE_STATUSES.includes(job.status as ArtifactStatus);

                // Safe timestamp parsing
                let dateDisplay = "";
                try {
                  const rawTs = job.created_at;
                  if (typeof rawTs === "number") {
                    dateDisplay = new Date(rawTs > 1e11 ? rawTs : rawTs * 1000).toLocaleString();
                  } else if (typeof rawTs === "string") {
                    dateDisplay = new Date(rawTs).toLocaleString();
                  }
                } catch {
                  dateDisplay = "";
                }

                return (
                  <li
                    key={job.id}
                    className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-gray-50 transition-colors"
                    data-testid={`job-row-${job.id}`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-gray-900">
                          {job.artifact_type} Presentation
                        </span>
                        {dateDisplay && (
                          <span className="text-xs text-gray-400">
                            • {dateDisplay}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-500 mt-0.5 font-mono">
                        Job ID: {job.id}
                      </p>

                      {/* Selected units count if stored in config */}
                      {job.config?.selected_unit_ids && Array.isArray(job.config.selected_unit_ids) && (
                        <p className="text-xs text-gray-500 mt-1">
                          Scope: {job.config.selected_unit_ids.length} selected container(s)
                        </p>
                      )}

                      {/* FAILED error_message */}
                      {isJobFailed && job.error_message && (
                        <p
                          className="text-xs text-red-700 mt-2 bg-red-50 p-2.5 rounded border border-red-200"
                          data-testid={`job-error-${job.id}`}
                        >
                          <strong>Failure:</strong> {job.error_message}
                        </p>
                      )}
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      {/* Status badge */}
                      <span
                        className={`px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5 ${statusColor(
                          job.status as ArtifactStatus
                        )}`}
                        data-testid={`job-status-${job.id}`}
                      >
                        {isJobActive && <Loader2 className="size-3 animate-spin" />}
                        {statusLabel(job.status as ArtifactStatus)}
                      </span>

                      {/* Study Deck button: for COMPLETED jobs with slides */}
                      {isJobCompleted && job.plan && Array.isArray((job.plan as any).slides) && (job.plan as any).slides.length > 0 && (
                        <button
                          type="button"
                          onClick={() => setStudyingJob(job)}
                          data-testid={`job-study-${job.id}`}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-violet-200 dark:border-violet-800 text-xs font-semibold rounded-lg text-violet-700 dark:text-violet-300 bg-violet-50 dark:bg-violet-950/40 hover:bg-violet-100 dark:hover:bg-violet-900/50 shadow-xs transition-colors cursor-pointer"
                        >
                          <BookOpen className="size-3.5 text-violet-600 dark:text-violet-400" />
                          Study Deck
                        </button>
                      )}

                      {/* Download button: ONLY for COMPLETED */}
                      {isJobCompleted && (
                        <a
                          href={artifactService.getDownloadUrl(job.id)}
                          download
                          data-testid={`job-download-${job.id}`}
                          className="inline-flex items-center gap-1.5 px-3.5 py-1.5 border border-transparent text-xs font-semibold rounded-lg text-white bg-indigo-600 hover:bg-indigo-700 shadow-xs transition-colors cursor-pointer"
                        >
                          <Download className="size-3.5" />
                          {job.artifact_type === ArtifactType.FLASHCARDS_CSV
                            ? "Download CSV"
                            : job.artifact_type === ArtifactType.STUDY_GUIDE_MD
                            ? "Download Guide (.md)"
                            : job.artifact_type === ArtifactType.PRACTICE_EXAM_MD
                            ? "Download Exam (.md)"
                            : "Download PPTX"}
                        </a>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </main>

      {/* Interactive In-Browser Study Deck Modal */}
      {studyingJob && (
        <InteractiveStudyModal
          job={studyingJob}
          isOpen={!!studyingJob}
          onClose={() => setStudyingJob(null)}
        />
      )}
    </div>
  );
}
