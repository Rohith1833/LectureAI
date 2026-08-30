import type { FC } from "react";
import { CheckSquare } from "lucide-react";
import type { GenerationClaim, GroundingStatus } from "@/types/generation";
import CitationChip from "./CitationChip";

interface ClaimsListProps {
  claims: GenerationClaim[];
}

function getClaimStatusBadge(status: GroundingStatus) {
  const base = "px-2 py-0.5 rounded-full text-[10px] font-bold tracking-wide uppercase shrink-0";
  switch (status) {
    case "SUPPORTED":
      return (
        <span className={`${base} bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300`}>
          Supported
        </span>
      );
    case "PARTIALLY_SUPPORTED":
      return (
        <span className={`${base} bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300`}>
          Partial
        </span>
      );
    case "INSUFFICIENT_CONTEXT":
      return (
        <span className={`${base} bg-sky-100 text-sky-800 dark:bg-sky-950/50 dark:text-sky-300`}>
          No Match
        </span>
      );
    case "UNSUPPORTED":
    default:
      return (
        <span className={`${base} bg-rose-100 text-rose-800 dark:bg-rose-950/50 dark:text-rose-300`}>
          Unsupported
        </span>
      );
  }
}

function getClaimBorder(status: GroundingStatus) {
  switch (status) {
    case "SUPPORTED":
      return "border-l-3 border-l-emerald-500 pl-3.5";
    case "PARTIALLY_SUPPORTED":
      return "border-l-3 border-l-amber-500 pl-3.5";
    case "INSUFFICIENT_CONTEXT":
      return "border-l-3 border-l-sky-500 pl-3.5";
    case "UNSUPPORTED":
    default:
      return "border-l-3 border-l-rose-500 pl-3.5";
  }
}

export const ClaimsList: FC<ClaimsListProps> = ({ claims }) => {
  if (!claims || claims.length === 0) return null;

  return (
    <div className="border border-border bg-card rounded-xl p-5 shadow-xs flex flex-col gap-4">
      <div className="flex items-center justify-between border-b border-border pb-2.5">
        <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
          <CheckSquare className="size-3.5 text-violet-600" />
          Verified Claims Breakdown ({claims.length})
        </h3>
        <span className="text-[10px] text-muted-foreground">Per-assertion grounding</span>
      </div>

      <div className="flex flex-col gap-3.5">
        {claims.map((claim) => (
          <div
            key={claim.claim_id}
            className={`flex flex-col gap-1.5 py-1 ${getClaimBorder(claim.grounding_status)}`}
          >
            <div className="flex items-center justify-between gap-4">
              <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider select-none">
                Claim {claim.claim_id}
              </span>
              <div className="flex items-center gap-1.5 flex-wrap">
                {getClaimStatusBadge(claim.grounding_status)}
                {claim.citation_ids.map((cid) => (
                  <CitationChip key={cid} citationId={cid} size="sm" />
                ))}
              </div>
            </div>
            <p className="text-xs text-foreground font-medium leading-relaxed">
              {claim.text}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ClaimsList;
