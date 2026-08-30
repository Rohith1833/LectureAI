import type { FC } from "react";
import { CheckCircle2, AlertTriangle, XCircle, Info } from "lucide-react";
import type { GroundingStatus } from "@/types/generation";

interface GroundingStatusBannerProps {
  status: GroundingStatus;
}

export const GroundingStatusBanner: FC<GroundingStatusBannerProps> = ({ status }) => {
  switch (status) {
    case "SUPPORTED":
      return (
        <div
          role="status"
          className="flex flex-col gap-1 p-3.5 bg-emerald-50/80 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-900/50 rounded-xl text-emerald-900 dark:text-emerald-300 text-xs shadow-2xs"
        >
          <div className="flex items-center gap-2">
            <CheckCircle2 className="size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
            <span className="font-bold tracking-wide">Fully Grounded & Supported</span>
          </div>
          <p className="text-[11px] text-emerald-800/90 dark:text-emerald-300/80 pl-6 leading-relaxed">
            All assertions and statements map directly to verified source citations extracted from this document's knowledge base.
          </p>
        </div>
      );

    case "PARTIALLY_SUPPORTED":
      return (
        <div
          role="status"
          className="flex flex-col gap-1 p-3.5 bg-amber-50/80 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/50 rounded-xl text-amber-900 dark:text-amber-300 text-xs shadow-2xs"
        >
          <div className="flex items-center gap-2">
            <AlertTriangle className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
            <span className="font-bold tracking-wide">Partially Supported</span>
          </div>
          <p className="text-[11px] text-amber-800/90 dark:text-amber-300/80 pl-6 leading-relaxed">
            Certain claims or statements reference unverified context or lack full documentary grounding. Please review the highlighted citations.
          </p>
        </div>
      );

    case "INSUFFICIENT_CONTEXT":
      return (
        <div
          role="status"
          className="flex flex-col gap-1 p-3.5 bg-sky-50/80 dark:bg-sky-950/20 border border-sky-200 dark:border-sky-900/50 rounded-xl text-sky-900 dark:text-sky-300 text-xs shadow-2xs"
        >
          <div className="flex items-center gap-2">
            <Info className="size-4 shrink-0 text-sky-600 dark:text-sky-400" />
            <span className="font-bold tracking-wide">Insufficient Context Available</span>
          </div>
          <p className="text-[11px] text-sky-800/90 dark:text-sky-300/80 pl-6 leading-relaxed">
            The retrieval engine found insufficient source material for this prompt. To prevent hallucinations, the model has abstained from extrapolating.
          </p>
        </div>
      );

    case "UNSUPPORTED":
    default:
      return (
        <div
          role="status"
          className="flex flex-col gap-1 p-3.5 bg-rose-50/80 dark:bg-rose-950/20 border border-rose-200 dark:border-rose-900/50 rounded-xl text-rose-900 dark:text-rose-300 text-xs shadow-2xs"
        >
          <div className="flex items-center gap-2">
            <XCircle className="size-4 shrink-0 text-rose-600 dark:text-rose-400" />
            <span className="font-bold tracking-wide">Unsupported Content</span>
          </div>
          <p className="text-[11px] text-rose-800/90 dark:text-rose-300/80 pl-6 leading-relaxed">
            No claims could be matched to retrieved citations. The generated response lacks verifiable grounding in the underlying document.
          </p>
        </div>
      );
  }
};

export default GroundingStatusBanner;
