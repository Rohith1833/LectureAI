import type { FC } from "react";
import { BookOpen, FileText, Tag } from "lucide-react";
import type { ContextSource } from "@/types/generation";

interface CitationDetailsListProps {
  citations: Record<string, ContextSource>;
}

export const CitationDetailsList: FC<CitationDetailsListProps> = ({ citations }) => {
  const citationList = Object.values(citations);

  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex items-center justify-between px-1">
        <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
          <BookOpen className="size-3.5 text-violet-600" />
          Supporting Citations ({citationList.length})
        </h3>
        <span className="text-[10px] text-muted-foreground italic">
          Extracted from Canonical Knowledge Graph
        </span>
      </div>

      {citationList.length === 0 ? (
        <div className="p-4 border border-dashed border-border rounded-xl text-center bg-card/40">
          <p className="text-xs text-muted-foreground italic">
            No supporting source citations were resolved for this output.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3.5">
          {citationList.map((source) => (
            <div
              key={source.citation_id}
              id={`citation-${source.citation_id}`}
              tabIndex={-1}
              className="border border-border bg-card rounded-xl p-4 shadow-xs flex flex-col gap-3 transition-all duration-300 focus:outline-none"
            >
              {/* Card Header: Citation Badge, Title, Entity Type */}
              <div className="flex items-center justify-between border-b border-border pb-2.5">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="bg-violet-600 text-white font-extrabold text-xs px-2 py-0.5 rounded shadow-2xs shrink-0 select-none">
                    {source.citation_id}
                  </span>
                  <h4 className="font-bold text-sm text-foreground truncate max-w-sm sm:max-w-md">
                    {source.title}
                  </h4>
                </div>
                <span className="bg-muted text-muted-foreground font-bold text-[9px] tracking-wide uppercase px-2 py-0.5 rounded-md flex items-center gap-1 shrink-0 select-none">
                  <Tag className="size-3" /> {source.entity_type}
                </span>
              </div>

              {/* Entity Content Preview */}
              <div className="flex flex-col gap-1 text-xs">
                <span className="font-bold text-muted-foreground uppercase tracking-wider text-[9px]">
                  Canonical Entity Content
                </span>
                <p className="text-muted-foreground whitespace-pre-wrap leading-relaxed">
                  {source.content}
                </p>
              </div>

              {/* Verbatim Passage Box (if present) */}
              {source.passage && (
                <div className="flex flex-col gap-2 p-3 bg-muted/40 dark:bg-muted/20 rounded-lg border border-dashed border-border text-xs">
                  <span className="font-bold text-muted-foreground uppercase tracking-wider text-[9px] flex items-center gap-1.5">
                    <BookOpen className="size-3 text-violet-600" />
                    Verbatim Document Passage (Page {source.passage.page_number})
                  </span>
                  <p className="text-muted-foreground leading-relaxed italic">
                    "{source.passage.text}"
                  </p>
                  {source.provenance && (
                    <div className="flex items-center gap-2 text-[10px] text-muted-foreground mt-1 pt-1.5 border-t border-border border-dashed font-semibold select-none">
                      <FileText className="size-3" /> Origin Block: {source.provenance}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <p className="text-[10px] text-muted-foreground px-1 italic">
        * Citations identify supporting excerpts retrieved from approved knowledge graphs, not autonomous external proof.
      </p>
    </div>
  );
};

export default CitationDetailsList;
