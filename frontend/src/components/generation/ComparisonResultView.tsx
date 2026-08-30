import type { FC, ReactNode } from "react";
import { GitCompare, CheckCircle2, Split, Table } from "lucide-react";
import type { StructuredComparisonOutput } from "@/types/generation";
import CitationChip from "./CitationChip";

interface ComparisonResultViewProps {
  structuredOutput?: StructuredComparisonOutput | null;
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

export const ComparisonResultView: FC<ComparisonResultViewProps> = ({
  structuredOutput,
  fallbackAnswer,
}) => {
  if (!structuredOutput || Object.keys(structuredOutput).length === 0) {
    return (
      <div className="border border-border bg-card rounded-xl p-5 shadow-xs flex flex-col gap-3">
        <h3 className="font-bold text-sm text-foreground">Comparison Synthesis</h3>
        <p className="text-sm leading-relaxed text-muted-foreground whitespace-pre-wrap">
          {renderTextWithCitations(fallbackAnswer || "No structured comparison details returned.")}
        </p>
      </div>
    );
  }

  const {
    title = "Concept Comparison Matrix",
    subjects = [],
    comparison_table = [],
    similarities = [],
    differences = [],
  } = structuredOutput;

  return (
    <div className="flex flex-col gap-5 animate-in fade-in duration-300">
      {/* 1. Header & Subject Badges */}
      <div className="border border-border bg-card rounded-xl p-5 shadow-xs flex flex-col gap-3">
        <div className="flex items-center gap-2 text-violet-600 dark:text-violet-400">
          <GitCompare className="size-5 shrink-0" />
          <h2 className="text-base sm:text-lg font-bold text-foreground tracking-tight">
            {title}
          </h2>
        </div>

        {subjects.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap pt-1 border-t border-border/60">
            <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              Comparing:
            </span>
            {subjects.map((sub, idx) => (
              <div key={idx} className="flex items-center gap-1.5">
                <span className="bg-violet-100 dark:bg-violet-950/60 text-violet-800 dark:text-violet-300 font-bold text-xs px-2.5 py-1 rounded-lg border border-violet-200 dark:border-violet-800/60 shadow-2xs">
                  {sub}
                </span>
                {idx < subjects.length - 1 && (
                  <span className="text-[10px] font-extrabold text-muted-foreground uppercase">
                    vs
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 2. Structured Comparison Table */}
      {comparison_table.length > 0 && (
        <div className="border border-border bg-card rounded-xl shadow-xs overflow-hidden flex flex-col">
          <div className="p-4 border-b border-border bg-muted/30 flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              <Table className="size-3.5 text-violet-600" />
              Dimension Breakdown Table
            </h3>
            <span className="text-[10px] text-muted-foreground italic">
              Scroll horizontally if necessary
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs" aria-label="Comparison Table">
              <thead>
                <tr className="border-b border-border bg-muted/60 text-muted-foreground font-bold uppercase tracking-wider text-[10px]">
                  <th scope="col" className="p-3.5 min-w-[140px] max-w-[180px]">
                    Dimension
                  </th>
                  {subjects.map((subject, idx) => (
                    <th key={idx} scope="col" className="p-3.5 min-w-[180px]">
                      {subject}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {comparison_table.map((row, rowIdx) => (
                  <tr
                    key={rowIdx}
                    className="hover:bg-muted/20 transition-colors duration-150 align-top"
                  >
                    <th
                      scope="row"
                      className="p-3.5 font-bold text-foreground bg-muted/10 border-r border-border/60"
                    >
                      <div className="flex flex-col gap-1">
                        <span>{row.dimension}</span>
                        {row.explanation && (
                          <span className="text-[10px] font-normal text-muted-foreground italic leading-relaxed">
                            {row.explanation}
                          </span>
                        )}
                      </div>
                    </th>
                    {subjects.map((subj, subjIdx) => {
                      const valObj = row.values?.find(
                        (v) => v.subject?.toLowerCase() === subj.toLowerCase()
                      ) || row.values?.[subjIdx];

                      const rawVal = valObj?.value || "N/A";
                      const citations = valObj?.citation_ids || [];

                      return (
                        <td
                          key={subjIdx}
                          className="p-3.5 text-muted-foreground leading-relaxed border-r border-border/40 last:border-r-0"
                        >
                          <div className="flex flex-col gap-1">
                            <span className="text-foreground">{renderTextWithCitations(rawVal)}</span>
                            {citations.length > 0 && !rawVal.includes("[S") && (
                              <div className="flex items-center gap-1 mt-1 flex-wrap">
                                {citations.map((cid) => (
                                  <CitationChip key={cid} citationId={cid} size="sm" />
                                ))}
                              </div>
                            )}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 3. Similarities & Differences Two-Column Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
        {/* Similarities Card */}
        {similarities.length > 0 && (
          <div className="border border-border bg-card rounded-xl p-4 sm:p-5 shadow-xs flex flex-col gap-3">
            <div className="flex items-center gap-2 border-b border-border pb-2.5">
              <CheckCircle2 className="size-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Key Similarities ({similarities.length})
              </h3>
            </div>
            <ul className="flex flex-col gap-2.5 text-xs text-muted-foreground">
              {similarities.map((item, idx) => (
                <li
                  key={idx}
                  className="flex flex-col gap-1 p-2.5 bg-muted/30 rounded-lg border border-border/60 leading-relaxed text-foreground"
                >
                  <div>{renderTextWithCitations(item.text)}</div>
                  {item.citation_ids && item.citation_ids.length > 0 && !item.text.includes("[S") && (
                    <div className="flex items-center gap-1 mt-1 flex-wrap">
                      {item.citation_ids.map((cid) => (
                        <CitationChip key={cid} citationId={cid} size="sm" />
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Differences Card */}
        {differences.length > 0 && (
          <div className="border border-border bg-card rounded-xl p-4 sm:p-5 shadow-xs flex flex-col gap-3">
            <div className="flex items-center gap-2 border-b border-border pb-2.5">
              <Split className="size-4 text-amber-600 dark:text-amber-400 shrink-0" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Distinct Differences ({differences.length})
              </h3>
            </div>
            <ul className="flex flex-col gap-2.5 text-xs text-muted-foreground">
              {differences.map((item, idx) => (
                <li
                  key={idx}
                  className="flex flex-col gap-1 p-2.5 bg-muted/30 rounded-lg border border-border/60 leading-relaxed text-foreground"
                >
                  <div>{renderTextWithCitations(item.text)}</div>
                  {item.citation_ids && item.citation_ids.length > 0 && !item.text.includes("[S") && (
                    <div className="flex items-center gap-1 mt-1 flex-wrap">
                      {item.citation_ids.map((cid) => (
                        <CitationChip key={cid} citationId={cid} size="sm" />
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
};

export default ComparisonResultView;
