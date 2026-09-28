import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { listFinalizedVersions } from "@/services/knowledgeService";
import { artifactService } from "@/services/artifactService";
import type { KnowledgeVersion } from "@/types/knowledge";
import { ArtifactType, ArtifactStatus } from "@/types/artifact";
import type { ArtifactJobRead } from "@/types/artifact";

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

export default function ArtifactWorkspacePage() {
  // Route param is Document.id — NOT upload_id
  const { id: documentId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  // --- Knowledge Version state ---
  const [version, setVersion] = useState<KnowledgeVersion | null>(null);
  const [versionLoading, setVersionLoading] = useState(true);
  const [versionError, setVersionError] = useState<string | null>(null);

  // --- Configuration state ---
  const [audienceLevel, setAudienceLevel] = useState("general");
  const [depth, setDepth] = useState("standard");
  const [numUnits, setNumUnits] = useState(3);
  const [includeExamples, setIncludeExamples] = useState(true);
  const [includeQuestions, setIncludeQuestions] = useState(true);

  // --- Job state ---
  const [jobs, setJobs] = useState<ArtifactJobRead[]>([]);
  const [pollingJobId, setPollingJobId] = useState<string | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  // --- Load finalized knowledge version ---
  useEffect(() => {
    if (!documentId) return;

    setVersionLoading(true);
    setVersionError(null);

    listFinalizedVersions(documentId)
      .then((versions: KnowledgeVersion[]) => {
        if (versions.length > 0) {
          setVersion(versions[0]);
        } else {
          setVersionError(
            "No finalized knowledge version available for this document. Complete the Academic Review process first."
          );
        }
      })
      .catch(() => {
        setVersionError("Failed to load knowledge versions.");
      })
      .finally(() => {
        setVersionLoading(false);
      });
  }, [documentId]);

  // --- Load existing jobs ONLY after version is loaded (need upload_id) ---
  const loadJobs = useCallback(async (uploadId: string) => {
    try {
      const data = await artifactService.listJobs(uploadId);
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

  // --- Poll for active job status ---
  useEffect(() => {
    if (!pollingJobId) return;

    const interval = setInterval(async () => {
      try {
        const updated = await artifactService.getJobStatus(pollingJobId);
        setJobs((prev) =>
          prev.map((j) => (j.id === pollingJobId ? updated : j))
        );

        if (TERMINAL_STATUSES.includes(updated.status as ArtifactStatus)) {
          setPollingJobId(null);
        }
      } catch {
        setPollingJobId(null);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [pollingJobId]);

  // --- Generate handler ---
  const handleGenerate = async () => {
    if (!version) return;

    setGenerateError(null);
    setGenerating(true);

    try {
      const newJob = await artifactService.generateArtifact({
        upload_id: version.upload_id, // Correct: use version.upload_id, NOT documentId
        knowledge_version_id: version.id,
        artifact_type: ArtifactType.PPTX,
        config: {
          audience_level: audienceLevel,
          depth: depth,
          num_units: numUnits,
          include_examples: includeExamples,
          include_questions: includeQuestions,
        },
      });
      setJobs((prev) => [newJob, ...prev]);
      setPollingJobId(newJob.id);
    } catch (err: unknown) {
      // Surface the backend's actual error detail
      let message = "Failed to start generation.";
      if (err && typeof err === "object" && "response" in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } };
        if (axiosErr.response?.data?.detail) {
          message = axiosErr.response.data.detail;
        }
      } else if (err instanceof Error) {
        message = err.message;
      }
      setGenerateError(message);
    } finally {
      setGenerating(false);
    }
  };

  // --- Status label helper ---
  const statusLabel = (status: ArtifactStatus): string => {
    switch (status) {
      case ArtifactStatus.PENDING:
        return "Pending";
      case ArtifactStatus.PLANNING:
        return "Planning slides…";
      case ArtifactStatus.RENDERING:
        return "Rendering PPTX…";
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
        return "bg-green-100 text-green-800";
      case ArtifactStatus.FAILED:
        return "bg-red-100 text-red-800";
      default:
        return "bg-blue-100 text-blue-800 animate-pulse";
    }
  };

  // --- Loading screen ---
  if (versionLoading) {
    return (
      <div
        className="flex justify-center items-center h-full p-8"
        data-testid="loading-spinner"
      >
        <div className="animate-spin h-8 w-8 border-4 border-indigo-600 rounded-full border-t-transparent" />
      </div>
    );
  }

  // --- No finalized version ---
  if (versionError || !version) {
    return (
      <div className="p-8">
        <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-lg">
          <p className="font-semibold">Cannot Generate Artifacts</p>
          <p data-testid="version-error">
            {versionError ||
              "No finalized knowledge version available for this document."}
          </p>
          <button
            onClick={() => navigate(`/documents/${documentId}`)}
            className="mt-4 px-4 py-2 bg-white text-red-700 border border-red-200 rounded shadow-sm hover:bg-gray-50"
          >
            Back to Document
          </button>
        </div>
      </div>
    );
  }

  const isGenerating = generating || !!pollingJobId;

  return (
    <div className="flex h-full flex-col bg-gray-50 overflow-hidden">
      {/* Header */}
      <header className="bg-white border-b px-6 py-4 flex items-center justify-between shadow-sm z-10">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">
            Artifact Generation Workspace
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Generate presentations from finalized knowledge
          </p>
        </div>
        <button
          onClick={() => navigate(`/documents/${documentId}`)}
          className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
        >
          Back to Document
        </button>
      </header>

      <main className="flex-1 overflow-auto p-6 max-w-5xl mx-auto w-full space-y-6">
        {/* Knowledge Version Identity */}
        <div
          className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden"
          data-testid="version-info"
        >
          <div className="p-5 border-b border-gray-200 bg-emerald-50">
            <h2 className="text-base font-semibold text-gray-900">
              Finalized Knowledge Version
            </h2>
          </div>
          <div className="p-5 grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-gray-500 block text-xs font-medium uppercase tracking-wide">
                Version ID
              </span>
              <span
                className="font-mono text-gray-800 break-all"
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
                className="font-mono text-gray-800 break-all"
                data-testid="version-upload-id"
              >
                {version.upload_id}
              </span>
            </div>
          </div>
        </div>

        {/* Configuration Panel */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
          <div className="p-5 border-b border-gray-200">
            <h2 className="text-base font-semibold text-gray-900">
              Artifact Configuration
            </h2>
          </div>
          <div className="p-5 space-y-5">
            {/* Row 1: Audience Level + Depth */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
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

            {/* Row 2: Number of Units */}
            <div>
              <label
                htmlFor="num-units"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Number of Units
              </label>
              <input
                type="number"
                id="num-units"
                data-testid="num-units-input"
                value={numUnits}
                onChange={(e) =>
                  setNumUnits(Math.max(1, parseInt(e.target.value, 10) || 1))
                }
                min={1}
                max={50}
                disabled={isGenerating}
                className="w-full sm:w-32 rounded-md border border-gray-300 py-2 px-3 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              />
            </div>

            {/* Row 3: Checkboxes */}
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
                <span className="text-sm text-gray-700">
                  Include Questions
                </span>
              </label>
            </div>
          </div>

          {/* Generate Error */}
          {generateError && (
            <div
              className="mx-5 mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700"
              data-testid="generate-error"
            >
              <strong>Error:</strong> {generateError}
            </div>
          )}

          {/* Generate Button */}
          <div className="p-5 bg-gray-50 border-t border-gray-200">
            <button
              onClick={handleGenerate}
              disabled={isGenerating}
              data-testid="generate-button"
              className="w-full flex justify-center py-3 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
            >
              {isGenerating
                ? "Generating…"
                : "Generate Presentation (.pptx)"}
            </button>
          </div>
        </div>

        {/* Generation History */}
        {jobs.length > 0 && (
          <div
            className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden"
            data-testid="job-history"
          >
            <div className="p-5 border-b border-gray-200">
              <h2 className="text-base font-semibold text-gray-900">
                Generation History
              </h2>
            </div>
            <ul className="divide-y divide-gray-200">
              {jobs.map((job) => (
                <li
                  key={job.id}
                  className="p-5 flex items-start sm:items-center justify-between gap-4 hover:bg-gray-50 transition-colors"
                  data-testid={`job-row-${job.id}`}
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-900">
                      {job.artifact_type} Presentation
                    </p>
                    <p className="text-xs text-gray-500 mt-1 font-mono">
                      Job: {job.id}
                    </p>

                    {/* FAILED error_message */}
                    {job.status === ArtifactStatus.FAILED &&
                      job.error_message && (
                        <p
                          className="text-sm text-red-600 mt-2 bg-red-50 p-2 rounded border border-red-100"
                          data-testid={`job-error-${job.id}`}
                        >
                          {job.error_message}
                        </p>
                      )}
                  </div>

                  <div className="flex items-center gap-3 shrink-0">
                    {/* Status badge */}
                    <span
                      className={`px-2.5 py-1 rounded-full text-xs font-medium uppercase tracking-wider ${statusColor(job.status as ArtifactStatus)}`}
                      data-testid={`job-status-${job.id}`}
                    >
                      {statusLabel(job.status as ArtifactStatus)}
                    </span>

                    {/* Download button: ONLY for COMPLETED */}
                    {job.status === ArtifactStatus.COMPLETED && (
                      <a
                        href={artifactService.getDownloadUrl(job.id)}
                        download
                        data-testid={`job-download-${job.id}`}
                        className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded text-indigo-700 bg-indigo-100 hover:bg-indigo-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors"
                      >
                        <svg
                          className="mr-1.5 h-4 w-4"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                          />
                        </svg>
                        Download PowerPoint
                      </a>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </main>
    </div>
  );
}
