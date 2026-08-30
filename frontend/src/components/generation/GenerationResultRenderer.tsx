import { useState, type FC, type ReactNode } from "react";
import { Copy, Check, Cpu, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import type {
  GenerationResult,
  GenerationMode,
  StructuredComparisonOutput,
  StructuredStudyGuideOutput,
} from "@/types/generation";
import GroundingStatusBanner from "./GroundingStatusBanner";
import CitationChip from "./CitationChip";
import ClaimsList from "./ClaimsList";
import CitationDetailsList from "./CitationDetailsList";
import ComparisonResultView from "./ComparisonResultView";
import StudyGuideResultView from "./StudyGuideResultView";

interface GenerationResultRendererProps {
  result: GenerationResult;
  mode: GenerationMode;
}

/**
 * Parses raw text and converts [S1], [S2] citation markers into interactive CitationChip components.
 */
function renderTextWithCitations(text: string): ReactNode {
  if (!text) return null;
  const parts = text.split(/(\[S\d+\])/g);

  return parts.map((part, index) => {
    const match = part.match(/^\[(S\d+)\]$/);
    if (match) {
      const citationId = match[1];
      return <CitationChip key={index} citationId={citationId} />;
    }
    return part;
  });
}

export const GenerationResultRenderer: FC<GenerationResultRendererProps> = ({
  result,
  mode,
}) => {
  const [copied, setCopied] = useState<boolean>(false);

  const handleCopy = async () => {
    if (!result?.answer) return;
    try {
      await navigator.clipboard.writeText(result.answer);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback if clipboard API is restricted
    }
  };

  return (
    <div className="flex flex-col gap-5 animate-in fade-in duration-300">
      {/* 1. Grounding Status Banner */}
      <GroundingStatusBanner status={result.overall_grounding_status} />

      {/* 2. Mode-Specific Renderers */}
      {mode === "COMPARISON" ? (
        <ComparisonResultView
          structuredOutput={result.structured_output as StructuredComparisonOutput | null}
          fallbackAnswer={result.answer}
        />
      ) : mode === "STUDY_GUIDE" ? (
        <StudyGuideResultView
          structuredOutput={result.structured_output as StructuredStudyGuideOutput | null}
          fallbackAnswer={result.answer}
        />
      ) : (
        /* Standard Natural Language Card for QA, EXPLANATION, SUMMARY */
        <div className="border border-border bg-card rounded-xl p-5 sm:p-6 shadow-xs flex flex-col gap-4">
          {/* Card Header: Section Title, Model Metadata, Copy Button */}
          <div className="flex items-center justify-between border-b border-border pb-3 flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <MessageSquare className="size-4 text-violet-600" />
              <h2 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                {mode === "EXPLANATION"
                  ? "Step-by-Step Explanation"
                  : mode === "SUMMARY"
                  ? "Grounded Executive Summary"
                  : "Verified Answer"}
              </h2>
            </div>

            <div className="flex items-center gap-2">
              {result.model_metadata && (
                <div className="flex items-center gap-1.5 text-[10px] font-mono font-medium text-muted-foreground bg-muted px-2 py-0.5 rounded-md select-none">
                  <Cpu className="size-3 text-muted-foreground" />
                  {result.model_metadata.model_name && (
                    <span className="truncate max-w-[120px]">
                      {result.model_metadata.model_name}
                    </span>
                  )}
                  {result.model_metadata.token_usage?.total_tokens && (
                    <span>({result.model_metadata.token_usage.total_tokens} tokens)</span>
                  )}
                </div>
              )}

              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleCopy}
                className="text-xs py-1 px-2.5 h-auto flex items-center gap-1 text-muted-foreground hover:text-foreground cursor-pointer"
                aria-label="Copy answer to clipboard"
              >
                {copied ? (
                  <>
                    <Check className="size-3 text-emerald-600" />
                    <span className="text-[11px] text-emerald-600">Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="size-3" />
                    <span className="text-[11px]">Copy</span>
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* Answer Content */}
          <div className="text-sm leading-relaxed text-foreground whitespace-pre-wrap selection:bg-violet-100 dark:selection:bg-violet-950/60">
            {renderTextWithCitations(result.answer)}
          </div>
        </div>
      )}

      {/* 3. Claims Breakdown (when present) */}
      {result.claims && result.claims.length > 0 && (
        <ClaimsList claims={result.claims} />
      )}

      {/* 4. Supporting Citations Details List */}
      <CitationDetailsList citations={result.citations} />
    </div>
  );
};

export default GenerationResultRenderer;
