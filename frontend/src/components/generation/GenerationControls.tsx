import { useState, type FC, type FormEvent } from "react";
import { Sliders, Send, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { GenerationRequest } from "@/types/generation";
import ComparisonControls from "./ComparisonControls";
import StudyGuideControls from "./StudyGuideControls";
import {
  type WorkspaceFormState,
  validateGenerationForm,
  buildGenerationRequest,
} from "@/utils/generationRequest";

interface GenerationControlsProps {
  documentId: string;
  formState: WorkspaceFormState;
  onFormStateChange: (updater: (prev: WorkspaceFormState) => WorkspaceFormState) => void;
  onGenerate: (request: GenerationRequest) => void;
  isPending: boolean;
  isArchived?: boolean;
}

function getQueryPlaceholder(mode: WorkspaceFormState["mode"]): string {
  switch (mode) {
    case "QA":
      return "Ask a specific question about definitions, theorems, or mechanisms...";
    case "EXPLANATION":
      return "What concept or topic would you like explained step-by-step?";
    case "SUMMARY":
      return "Specify key sections/topics to summarize, or leave broad for an overview...";
    case "COMPARISON":
      return "Describe the context or key criteria for comparing these subjects...";
    case "STUDY_GUIDE":
      return "Specify the lecture or topic focus for this study guide...";
    default:
      return "Enter your prompt or query...";
  }
}

function getQueryLabel(mode: WorkspaceFormState["mode"]): string {
  switch (mode) {
    case "QA":
      return "Question / Prompt:";
    case "EXPLANATION":
      return "Target Concept / Topic:";
    case "SUMMARY":
      return "Summary Focus / Scope:";
    case "COMPARISON":
      return "Comparison Goal / Prompt:";
    case "STUDY_GUIDE":
      return "Study Guide Topic Focus:";
    default:
      return "Prompt:";
  }
}

function getButtonLabel(mode: WorkspaceFormState["mode"]): string {
  switch (mode) {
    case "QA":
      return "Ask LectureAI";
    case "EXPLANATION":
      return "Generate Explanation";
    case "SUMMARY":
      return "Generate Summary";
    case "COMPARISON":
      return "Generate Comparison";
    case "STUDY_GUIDE":
      return "Generate Study Guide";
    default:
      return "Generate";
  }
}

export const GenerationControls: FC<GenerationControlsProps> = ({
  documentId,
  formState,
  onFormStateChange,
  onGenerate,
  isPending,
  isArchived = false,
}) => {
  const [showAdvanced, setShowAdvanced] = useState<boolean>(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (isArchived) return;
    const validation = validateGenerationForm(formState, documentId);
    if (!validation.isValid) {
      setValidationError(validation.errorMessage);
      return;
    }

    setValidationError(null);
    const request = buildGenerationRequest(formState, documentId);
    onGenerate(request);
  };

  const validation = validateGenerationForm(formState, documentId);

  return (
    <form
      onSubmit={handleSubmit}
      className="border border-border bg-card rounded-xl p-4 sm:p-5 shadow-xs flex flex-col gap-4"
    >
      {/* Mode-Specific Specialized Controls */}
      {formState.mode === "COMPARISON" && (
        <ComparisonControls
          subjects={formState.comparisonSubjects}
          dimensions={formState.comparisonDimensions}
          disabled={isPending || isArchived}
          onSubjectsChange={(subjects) =>
            onFormStateChange((prev) => ({ ...prev, comparisonSubjects: subjects }))
          }
          onDimensionsChange={(dimensions) =>
            onFormStateChange((prev) => ({ ...prev, comparisonDimensions: dimensions }))
          }
        />
      )}

      {formState.mode === "STUDY_GUIDE" && (
        <StudyGuideControls
          questionCount={formState.studyQuestionCount}
          difficulty={formState.studyDifficulty}
          disabled={isPending || isArchived}
          onQuestionCountChange={(count) =>
            onFormStateChange((prev) => ({ ...prev, studyQuestionCount: count }))
          }
          onDifficultyChange={(diff) =>
            onFormStateChange((prev) => ({ ...prev, studyDifficulty: diff }))
          }
        />
      )}

      {/* Main Query / Prompt Textarea */}
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="generation-query-input"
          className="text-xs font-semibold text-muted-foreground flex items-center justify-between"
        >
          <span>{getQueryLabel(formState.mode)}</span>
          <span className="text-[10px] text-muted-foreground font-normal">Required</span>
        </label>
        <textarea
          id="generation-query-input"
          value={formState.query}
          disabled={isPending || isArchived}
          onChange={(e) => {
            onFormStateChange((prev) => ({ ...prev, query: e.target.value }));
            if (validationError) setValidationError(null);
          }}
          placeholder={
            isArchived
              ? "This conversation is archived and read-only."
              : getQueryPlaceholder(formState.mode)
          }
          rows={formState.mode === "COMPARISON" || formState.mode === "STUDY_GUIDE" ? 3 : 4}
          className="w-full p-3 text-sm bg-muted/40 dark:bg-muted/20 border border-input rounded-lg focus:outline-none focus:ring-1 focus:ring-violet-500 text-foreground resize-none disabled:opacity-50"
        />
      </div>

      {/* Validation Error Banner */}
      {validationError && (
        <div className="flex items-center gap-2 p-2.5 bg-rose-50 dark:bg-rose-950/20 border border-rose-200 dark:border-rose-900/50 rounded-lg text-rose-800 dark:text-rose-300 text-xs animate-in fade-in duration-150">
          <AlertCircle className="size-4 shrink-0 text-rose-600" />
          <span>{validationError}</span>
        </div>
      )}

      {/* Primary Submit / Generate Button */}
      <Button
        type="submit"
        disabled={isPending || !validation.isValid || isArchived}
        className="bg-violet-600 hover:bg-violet-700 text-white rounded-lg w-full py-2.5 text-sm font-semibold flex items-center justify-center gap-2 cursor-pointer shadow-xs disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
      >
        {isPending ? (
          <>
            <div className="size-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            <span>Generating Response...</span>
          </>
        ) : isArchived ? (
          <span>Session Archived (Read-Only)</span>
        ) : (
          <>
            <Send className="size-4" />
            <span>{getButtonLabel(formState.mode)}</span>
          </>
        )}
      </Button>

      {/* Collapsible Advanced Retrieval & Model Settings */}
      <div className="flex flex-col gap-3 pt-2 border-t border-border">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-bold tracking-wider uppercase text-muted-foreground flex items-center gap-1.5">
            <Sliders className="size-3.5 text-violet-600" /> Advanced Options
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-[11px] font-semibold text-violet-600 dark:text-violet-400 p-0 h-auto hover:bg-transparent cursor-pointer"
            aria-expanded={showAdvanced}
          >
            {showAdvanced ? "Hide Advanced" : "Configure"}
          </Button>
        </div>

        {showAdvanced && (
          <div className="flex flex-col gap-3.5 pt-2 border-t border-dashed border-border animate-in fade-in duration-200">
            {/* Temperature Slider */}
            <div className="flex flex-col gap-1">
              <label
                htmlFor="temperature-slider"
                className="text-xs text-muted-foreground flex justify-between"
              >
                <span>Temperature (Sampling):</span>
                <span className="font-semibold text-foreground font-mono">
                  {formState.temperature.toFixed(1)}
                </span>
              </label>
              <input
                id="temperature-slider"
                type="range"
                min={0.0}
                max={1.0}
                step={0.1}
                disabled={isPending}
                value={formState.temperature}
                onChange={(e) =>
                  onFormStateChange((prev) => ({
                    ...prev,
                    temperature: parseFloat(e.target.value),
                  }))
                }
                className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-violet-600 disabled:opacity-50"
              />
            </div>

            {/* Top-K Slider */}
            <div className="flex flex-col gap-1">
              <label
                htmlFor="top-k-slider"
                className="text-xs text-muted-foreground flex justify-between"
              >
                <span>Top-K Retrieved Entities:</span>
                <span className="font-semibold text-foreground font-mono">
                  {formState.topK}
                </span>
              </label>
              <input
                id="top-k-slider"
                type="range"
                min={5}
                max={20}
                step={1}
                disabled={isPending}
                value={formState.topK}
                onChange={(e) =>
                  onFormStateChange((prev) => ({
                    ...prev,
                    topK: parseInt(e.target.value, 10),
                  }))
                }
                className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-violet-600 disabled:opacity-50"
              />
            </div>

            {/* Retrieval Toggles */}
            <div className="flex flex-col gap-2 pt-2 border-t border-dashed border-border">
              <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
                Retrieval Pipeline Filters
              </span>
              <label className="flex items-center gap-2 text-xs cursor-pointer select-none">
                <input
                  type="checkbox"
                  disabled={isPending}
                  checked={formState.includeRelationships}
                  onChange={(e) =>
                    onFormStateChange((prev) => ({
                      ...prev,
                      includeRelationships: e.target.checked,
                    }))
                  }
                  className="rounded border-input text-violet-600 focus:ring-violet-500"
                />
                <span className="text-muted-foreground">Include Graph Relationships</span>
              </label>

              <label className="flex items-center gap-2 text-xs cursor-pointer select-none">
                <input
                  type="checkbox"
                  disabled={isPending}
                  checked={formState.includeEvidence}
                  onChange={(e) =>
                    onFormStateChange((prev) => ({
                      ...prev,
                      includeEvidence: e.target.checked,
                    }))
                  }
                  className="rounded border-input text-violet-600 focus:ring-violet-500"
                />
                <span className="text-muted-foreground">Include Extraction Evidence</span>
              </label>

              <label className="flex items-center gap-2 text-xs cursor-pointer select-none">
                <input
                  type="checkbox"
                  disabled={isPending}
                  checked={formState.includePassages}
                  onChange={(e) =>
                    onFormStateChange((prev) => ({
                      ...prev,
                      includePassages: e.target.checked,
                    }))
                  }
                  className="rounded border-input text-violet-600 focus:ring-violet-500"
                />
                <span className="text-muted-foreground">Include Verbatim Layout Passages</span>
              </label>
            </div>
          </div>
        )}
      </div>
    </form>
  );
};

export default GenerationControls;
