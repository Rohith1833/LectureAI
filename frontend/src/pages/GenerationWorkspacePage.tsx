import { useState, useEffect } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listFinalizedVersions } from "@/services/knowledgeService";
import { getDocument } from "@/services/documentService";
import { queryGeneration } from "@/services/generationService";
import { getConversation } from "@/services/conversationService";
import { Button } from "@/components/ui/button";
import {
  ArrowLeft,
  AlertTriangle,
  Sparkles,
  Layers,
  AlertCircle,
  HelpCircle,
} from "lucide-react";
import type { GenerationMode, GenerationRequest } from "@/types/generation";
import type { Conversation } from "@/types/conversation";
import GenerationModeSelector from "@/components/generation/GenerationModeSelector";
import GenerationControls from "@/components/generation/GenerationControls";
import GenerationResultRenderer from "@/components/generation/GenerationResultRenderer";
import ConversationSelector from "@/components/generation/ConversationSelector";
import ConversationHistoryView from "@/components/generation/ConversationHistoryView";
import { GENERATION_MODES } from "@/constants/generationModes";
import type { WorkspaceFormState } from "@/utils/generationRequest";

const VALID_MODES: GenerationMode[] = [
  "QA",
  "EXPLANATION",
  "SUMMARY",
  "COMPARISON",
  "STUDY_GUIDE",
];

function sanitizeMode(rawMode: string | null): GenerationMode {
  if (!rawMode) return "QA";
  const upper = rawMode.toUpperCase() as GenerationMode;
  return VALID_MODES.includes(upper) ? upper : "QA";
}

function getErrorMessage(error: any): string | null {
  if (!error) return null;
  const status = error.response?.status;
  const detail = error.response?.data?.detail;

  let detailStr = "";
  if (typeof detail === "string") {
    detailStr = detail;
  } else if (Array.isArray(detail)) {
    detailStr = detail.map((d: any) => d.msg || JSON.stringify(d)).join("; ");
  }

  if (status === 400) {
    return `Invalid request parameters. ${detailStr ? `Details: ${detailStr}` : ""}`;
  }
  if (status === 404) {
    return "Document or finalized knowledge version not found.";
  }
  if (status === 409) {
    return "Cannot generate in an archived conversation. Please create or select an active session.";
  }
  if (status === 422) {
    return `AI returned an unreadable response format or invalid request payload. ${
      detailStr ? `Details: ${detailStr}` : ""
    }`;
  }
  if (status === 502) {
    return `AI generation provider is temporarily unavailable. Please retry. ${
      detailStr ? `Details: ${detailStr}` : ""
    }`;
  }
  return `An unexpected error occurred: ${error.message || "Unknown error"}`;
}

export default function GenerationWorkspacePage() {
  const { id: documentId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();

  // Mode and Conversation synchronization with URL query parameters
  const initialMode = sanitizeMode(searchParams.get("mode"));
  const initialConvId = searchParams.get("conversation") || null;

  // Full Workspace Form State
  const [formState, setFormState] = useState<WorkspaceFormState>({
    mode: initialMode,
    query: "",
    selectedVersionId: null,
    conversationId: initialConvId,
    temperature: 0.0,
    topK: 10,
    includeRelationships: true,
    includeEvidence: true,
    includePassages: true,
    comparisonSubjects: ["", ""],
    comparisonDimensions: "",
    studyQuestionCount: 5,
    studyDifficulty: "intermediate",
  });

  // Synchronize when URL search param changes externally
  useEffect(() => {
    const urlMode = sanitizeMode(searchParams.get("mode"));
    const urlConvId = searchParams.get("conversation") || null;
    setFormState((prev) => {
      if (prev.mode !== urlMode || prev.conversationId !== urlConvId) {
        return { ...prev, mode: urlMode, conversationId: urlConvId };
      }
      return prev;
    });
  }, [searchParams]);

  // Handle user switching mode
  const handleModeChange = (newMode: GenerationMode) => {
    setFormState((prev) => ({ ...prev, mode: newMode }));
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("mode", newMode);
      return next;
    });
  };

  // 1. Fetch Document Metadata
  const docQuery = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => getDocument(documentId!),
    enabled: !!documentId,
  });

  // 2. Fetch Finalized Versions List
  const versionsQuery = useQuery({
    queryKey: ["versionsList", documentId],
    queryFn: () => listFinalizedVersions(documentId!),
    enabled: !!documentId,
  });

  // 3. Fetch Active Conversation if selected
  const activeConvQuery = useQuery({
    queryKey: ["conversation", formState.conversationId],
    queryFn: () => getConversation(formState.conversationId!),
    enabled: !!formState.conversationId,
  });

  // 4. Mode-Agnostic Generation Mutation
  const generationMutation = useMutation({
    mutationFn: (req: GenerationRequest) => queryGeneration(req),
    onSuccess: (_, variables) => {
      if (variables.conversation_id) {
        queryClient.invalidateQueries({
          queryKey: ["conversationMessages", variables.conversation_id],
        });
        queryClient.invalidateQueries({
          queryKey: ["conversations", documentId],
        });
      }
    },
  });

  const handleGenerate = (request: GenerationRequest) => {
    generationMutation.mutate(request);
  };

  const handleSelectConversation = (conv: Conversation | null) => {
    if (conv) {
      setFormState((prev) => ({
        ...prev,
        conversationId: conv.id,
        selectedVersionId: conv.knowledge_version_id || prev.selectedVersionId,
      }));
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("conversation", conv.id);
        return next;
      });
    } else {
      setFormState((prev) => ({ ...prev, conversationId: null }));
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.delete("conversation");
        return next;
      });
    }
  };

  const doc = docQuery.data?.data;
  const versions = versionsQuery.data || [];
  const activeConv = activeConvQuery.data || null;
  const result = generationMutation.data;
  const errorMsg = getErrorMessage(generationMutation.error);

  // Loading State
  if (docQuery.isLoading || versionsQuery.isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] gap-3">
        <div className="size-8 border-4 border-violet-600 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm text-muted-foreground animate-pulse">
          Loading Generation Workspace...
        </p>
      </div>
    );
  }

  // Error State: No Finalized Knowledge Available
  if (versions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 text-center max-w-lg mx-auto p-4">
        <div className="p-4 bg-amber-50 dark:bg-amber-950/20 text-amber-600 rounded-full">
          <AlertTriangle className="size-12" />
        </div>
        <h2 className="text-2xl font-bold tracking-tight">
          No Finalized Knowledge Available
        </h2>
        <p className="text-muted-foreground text-sm">
          This document does not have any finalized knowledge versions. Please ensure
          the academic graph is validated and approved before using generation tools.
        </p>
        <Button onClick={() => navigate(`/documents/${documentId}`)} variant="outline">
          Back to Document
        </Button>
      </div>
    );
  }

  const currentModeInfo = GENERATION_MODES.find((m) => m.key === formState.mode);

  return (
    <div className="flex flex-col gap-6 p-2 sm:p-4 max-w-7xl mx-auto">
      {/* 1. Header Section */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-5">
        <div className="flex flex-col gap-1">
          <Button
            onClick={() => navigate(`/documents/${documentId}`)}
            variant="ghost"
            className="pl-0 gap-1.5 text-muted-foreground hover:text-foreground cursor-pointer justify-start"
          >
            <ArrowLeft className="size-4" /> Back to Document Details
          </Button>
          <h1 className="text-2xl font-extrabold tracking-tight truncate max-w-2xl flex items-center gap-2">
            <Sparkles className="size-6 text-violet-600 shrink-0" />
            Generation Workspace
          </h1>
          <p className="text-xs text-muted-foreground">
            Document:{" "}
            <span className="font-semibold text-foreground">
              {doc?.metadata?.title || documentId}
            </span>
          </p>
        </div>

        {/* Target Version Selector */}
        <div className="flex items-center gap-2 sm:gap-3 bg-card border border-border rounded-xl p-2 sm:px-3 shadow-xs">
          <Layers className="size-4 text-violet-600 shrink-0 hidden sm:block" />
          <span className="text-xs font-semibold text-muted-foreground whitespace-nowrap">
            Knowledge Version:
          </span>
          <select
            value={formState.selectedVersionId || ""}
            disabled={generationMutation.isPending || !!activeConv?.knowledge_version_id}
            onChange={(e) =>
              setFormState((prev) => ({
                ...prev,
                selectedVersionId: e.target.value || null,
              }))
            }
            className="bg-muted text-foreground text-xs font-medium border border-input rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-violet-500 cursor-pointer disabled:opacity-50"
          >
            <option value="">Latest Finalized Version</option>
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                Version {v.approval_version} ({new Date(v.created_at * 1000).toLocaleDateString()})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* 2. Generation Mode Selector */}
      <GenerationModeSelector
        currentMode={formState.mode}
        disabled={generationMutation.isPending}
        onModeChange={handleModeChange}
      />

      {/* 3. Workspace Responsive Grid (Controls Left, Results/History Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Conversation Selector & Form Controls */}
        <div className="lg:col-span-5 flex flex-col gap-4">
          <ConversationSelector
            documentId={documentId!}
            selectedConversationId={formState.conversationId}
            selectedVersionId={formState.selectedVersionId}
            onSelectConversation={handleSelectConversation}
            disabled={generationMutation.isPending}
          />

          <GenerationControls
            documentId={documentId!}
            formState={formState}
            onFormStateChange={setFormState}
            onGenerate={handleGenerate}
            isPending={generationMutation.isPending}
            isArchived={activeConv?.status === "ARCHIVED"}
          />
        </div>

        {/* Right Column: Unified Results Workspace / Conversation History */}
        <div className="lg:col-span-7 flex flex-col gap-4 min-h-[50vh]">
          {/* A. Conversation History Stream if a conversation is active */}
          {activeConv && (
            <ConversationHistoryView conversation={activeConv} />
          )}

          {/* B. Loading State */}
          {generationMutation.isPending && (
            <div className="border border-border bg-card rounded-xl p-8 text-center flex flex-col items-center justify-center gap-4 h-full min-h-[240px] animate-pulse">
              <div className="size-10 border-4 border-violet-600 border-t-transparent rounded-full animate-spin" />
              <div className="flex flex-col gap-1">
                <h3 className="font-bold text-base text-foreground">
                  Synthesizing {currentModeInfo?.shortLabel} Response...
                </h3>
                <p className="text-muted-foreground text-xs max-w-sm leading-relaxed">
                  Retrieving canonical knowledge, building context sources, and prompting LLM with verified grounding rules...
                </p>
              </div>
            </div>
          )}

          {/* C. Transport / API Error State */}
          {errorMsg && (
            <div className="border border-rose-200 dark:border-rose-900/50 bg-rose-50/50 dark:bg-rose-950/10 rounded-xl p-5 flex flex-col gap-2">
              <div className="flex items-center gap-2 text-rose-600 dark:text-rose-400">
                <AlertCircle className="size-4 shrink-0" />
                <h3 className="font-bold text-xs sm:text-sm">Generation Notice</h3>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">{errorMsg}</p>
            </div>
          )}

          {/* D. Latest Grounded Generation Result View */}
          {result && !generationMutation.isPending && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between px-1">
                <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">
                  Latest Grounded Output
                </span>
              </div>
              <GenerationResultRenderer
                result={result}
                mode={formState.mode}
              />
            </div>
          )}

          {/* E. Idle / Empty State when no conversation is active and no result exists */}
          {!activeConv && !generationMutation.isPending && !result && !errorMsg && (
            <div className="border border-border bg-card rounded-xl p-8 text-center flex flex-col items-center justify-center gap-4 h-full min-h-[380px]">
              <div className="p-4 bg-muted/60 dark:bg-muted/30 rounded-full">
                <HelpCircle className="size-8 text-muted-foreground" />
              </div>
              <h3 className="font-bold text-lg text-foreground">
                {currentModeInfo?.label} Workspace
              </h3>
              <p className="text-muted-foreground text-xs sm:text-sm max-w-md leading-relaxed">
                {currentModeInfo?.description}. Configure parameters on the left or select a conversation session to synthesize grounded answers with verified citations.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
