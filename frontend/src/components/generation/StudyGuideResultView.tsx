import { useState, type FC, type ReactNode } from "react";
import {
  GraduationCap,
  BookOpen,
  Target,
  HelpCircle,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import type { StructuredStudyGuideOutput, StudyGuideReviewQuestion } from "@/types/generation";
import CitationChip from "./CitationChip";

interface StudyGuideResultViewProps {
  structuredOutput?: StructuredStudyGuideOutput | null;
  fallbackAnswer?: string;
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
      return <CitationChip key={index} citationId={citationId} size="sm" />;
    }
    return part;
  });
}

/**
 * Single Review Question Accordion Card
 */
const ReviewQuestionCard: FC<{
  item: StudyGuideReviewQuestion;
  index: number;
}> = ({ item, index }) => {
  const [isOpen, setIsOpen] = useState<boolean>(false);

  return (
    <div className="border border-border bg-card rounded-xl shadow-2xs overflow-hidden transition-all duration-200">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        className="w-full p-4 text-left flex items-start justify-between gap-3 hover:bg-muted/30 transition-colors duration-150 cursor-pointer"
      >
        <div className="flex items-start gap-2.5 min-w-0">
          <span className="bg-violet-100 dark:bg-violet-950/60 text-violet-800 dark:text-violet-300 font-bold text-xs size-6 rounded-md flex items-center justify-center shrink-0 border border-violet-200 dark:border-violet-800/60 select-none">
            {index + 1}
          </span>
          <h4 className="font-semibold text-xs sm:text-sm text-foreground leading-relaxed">
            {item.question}
          </h4>
        </div>
        <div className="text-muted-foreground p-1 shrink-0">
          {isOpen ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
        </div>
      </button>

      {isOpen && (
        <div className="p-4 pt-0 border-t border-dashed border-border/80 flex flex-col gap-3 text-xs bg-muted/10 animate-in fade-in duration-150">
          {/* Answer */}
          <div className="flex flex-col gap-1 pt-3">
            <span className="font-bold text-emerald-700 dark:text-emerald-400 uppercase tracking-wider text-[10px]">
              Target Answer
            </span>
            <p className="text-foreground leading-relaxed font-medium">
              {renderTextWithCitations(item.answer)}
            </p>
          </div>

          {/* Explanation */}
          {item.explanation && (
            <div className="flex flex-col gap-1 p-3 bg-muted/40 rounded-lg border border-border/60">
              <span className="font-bold text-muted-foreground uppercase tracking-wider text-[10px]">
                Pedagogical Explanation
              </span>
              <p className="text-muted-foreground leading-relaxed">
                {renderTextWithCitations(item.explanation)}
              </p>
            </div>
          )}

          {/* Explicit Citations */}
          {item.citation_ids && item.citation_ids.length > 0 && !item.answer.includes("[S") && (
            <div className="flex items-center gap-1.5 pt-1">
              <span className="text-[10px] font-semibold text-muted-foreground">Sources:</span>
              {item.citation_ids.map((cid) => (
                <CitationChip key={cid} citationId={cid} size="sm" />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export const StudyGuideResultView: FC<StudyGuideResultViewProps> = ({
  structuredOutput,
  fallbackAnswer,
}) => {
  if (!structuredOutput || Object.keys(structuredOutput).length === 0) {
    return (
      <div className="border border-border bg-card rounded-xl p-5 shadow-xs flex flex-col gap-3">
        <h3 className="font-bold text-sm text-foreground">Study Guide Material</h3>
        <p className="text-sm leading-relaxed text-muted-foreground whitespace-pre-wrap">
          {renderTextWithCitations(fallbackAnswer || "No structured study guide material returned.")}
        </p>
      </div>
    );
  }

  const {
    title = "Structured Study Guide",
    answer = fallbackAnswer || "",
    key_concepts = [],
    learning_objectives = [],
    review_questions = [],
  } = structuredOutput;

  return (
    <div className="flex flex-col gap-5 animate-in fade-in duration-300">
      {/* 1. Study Guide Title & Overview Card */}
      <div className="border border-border bg-card rounded-xl p-5 shadow-xs flex flex-col gap-3.5">
        <div className="flex items-center gap-2 text-violet-600 dark:text-violet-400">
          <GraduationCap className="size-5 shrink-0" />
          <h2 className="text-base sm:text-lg font-bold text-foreground tracking-tight">
            {title}
          </h2>
        </div>

        {answer && (
          <div className="text-xs sm:text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap pt-2 border-t border-border/60">
            {renderTextWithCitations(answer)}
          </div>
        )}
      </div>

      {/* 2. Key Concepts & Learning Objectives (Two-Column Layout) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
        {/* Key Concepts */}
        {key_concepts.length > 0 && (
          <div className="border border-border bg-card rounded-xl p-4 sm:p-5 shadow-xs flex flex-col gap-3">
            <div className="flex items-center gap-2 border-b border-border pb-2.5">
              <BookOpen className="size-4 text-violet-600 shrink-0" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Key Concepts ({key_concepts.length})
              </h3>
            </div>

            <div className="flex flex-col gap-2.5">
              {key_concepts.map((kc, idx) => (
                <div
                  key={idx}
                  className="flex flex-col gap-1 p-3 bg-muted/30 rounded-lg border border-border/60 text-xs"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold text-foreground">{kc.concept}</span>
                    {kc.citation_ids && kc.citation_ids.length > 0 && !kc.definition.includes("[S") && (
                      <div className="flex items-center gap-1">
                        {kc.citation_ids.map((cid) => (
                          <CitationChip key={cid} citationId={cid} size="sm" />
                        ))}
                      </div>
                    )}
                  </div>
                  <p className="text-muted-foreground leading-relaxed">
                    {renderTextWithCitations(kc.definition)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Learning Objectives */}
        {learning_objectives.length > 0 && (
          <div className="border border-border bg-card rounded-xl p-4 sm:p-5 shadow-xs flex flex-col gap-3">
            <div className="flex items-center gap-2 border-b border-border pb-2.5">
              <Target className="size-4 text-indigo-600 shrink-0" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Learning Objectives ({learning_objectives.length})
              </h3>
            </div>

            <ol className="flex flex-col gap-2 text-xs text-muted-foreground list-decimal list-inside pl-1">
              {learning_objectives.map((obj, idx) => (
                <li
                  key={idx}
                  className="p-2.5 bg-muted/30 rounded-lg border border-border/60 leading-relaxed text-foreground"
                >
                  <span>{renderTextWithCitations(obj)}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      {/* 3. Review Questions Accordion Section */}
      {review_questions.length > 0 && (
        <div className="border border-border bg-card rounded-xl p-4 sm:p-5 shadow-xs flex flex-col gap-4">
          <div className="flex items-center justify-between border-b border-border pb-3 flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <HelpCircle className="size-4 text-violet-600" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Review & Revision Questions ({review_questions.length})
              </h3>
            </div>

            <span className="text-[10px] text-muted-foreground italic">
              Click any question to reveal answers & verified explanations
            </span>
          </div>

          <div className="flex flex-col gap-2.5">
            {review_questions.map((rq, idx) => (
              <ReviewQuestionCard key={idx} item={rq} index={idx} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default StudyGuideResultView;
