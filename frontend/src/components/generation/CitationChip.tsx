import type { FC, MouseEvent } from "react";

interface CitationChipProps {
  citationId: string;
  className?: string;
  size?: "sm" | "default";
}

export const CitationChip: FC<CitationChipProps> = ({
  citationId,
  className = "",
  size = "default",
}) => {
  const handleClick = (e: MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    e.stopPropagation();

    const element = document.getElementById(`citation-${citationId}`);
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "center" });
      element.classList.add("ring-2", "ring-violet-500", "ring-offset-2");
      setTimeout(() => {
        element.classList.remove("ring-2", "ring-violet-500", "ring-offset-2");
      }, 2000);
    }
  };

  const sizeClasses =
    size === "sm"
      ? "px-1 py-0.2 text-[9px] font-bold"
      : "px-1.5 py-0.5 text-xs font-semibold";

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-label={`Jump to source citation ${citationId}`}
      className={`inline-flex items-center rounded bg-violet-100 dark:bg-violet-900/40 text-violet-800 dark:text-violet-300 hover:bg-violet-200 dark:hover:bg-violet-900/60 cursor-pointer mx-0.5 transition-all duration-200 border border-violet-200 dark:border-violet-800/60 focus:outline-none focus:ring-2 focus:ring-violet-500 ${sizeClasses} ${className}`}
    >
      {citationId}
    </button>
  );
};

export default CitationChip;
