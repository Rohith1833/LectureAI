import type { FC } from "react";
import { Plus, X, GitCompare } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ComparisonControlsProps {
  subjects: string[];
  dimensions: string;
  onSubjectsChange: (subjects: string[]) => void;
  onDimensionsChange: (dimensions: string) => void;
  disabled?: boolean;
}

export const ComparisonControls: FC<ComparisonControlsProps> = ({
  subjects,
  dimensions,
  onSubjectsChange,
  onDimensionsChange,
  disabled = false,
}) => {
  const handleSubjectChange = (index: number, value: string) => {
    const next = [...subjects];
    next[index] = value;
    onSubjectsChange(next);
  };

  const handleAddSubject = () => {
    if (subjects.length < 4) {
      onSubjectsChange([...subjects, ""]);
    }
  };

  const handleRemoveSubject = (index: number) => {
    if (subjects.length > 2) {
      const next = subjects.filter((_, i) => i !== index);
      onSubjectsChange(next);
    }
  };

  return (
    <fieldset className="flex flex-col gap-3 p-3.5 bg-muted/40 dark:bg-muted/20 border border-border rounded-xl">
      <legend className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5 px-1">
        <GitCompare className="size-3.5 text-violet-600" />
        Comparison Subjects & Dimensions
      </legend>

      {/* Subject Input Fields */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <label className="text-[11px] font-semibold text-muted-foreground">
            Comparison Subjects (2 – 4 explicit items):
          </label>
          <span className="text-[10px] text-muted-foreground font-mono">
            {subjects.length}/4 subjects
          </span>
        </div>

        <div className="flex flex-col gap-2">
          {subjects.map((subject, idx) => {
            const letter = String.fromCharCode(65 + idx); // A, B, C, D
            const isRemovable = subjects.length > 2 && idx >= 2;

            return (
              <div key={idx} className="flex items-center gap-1.5">
                <span className="text-xs font-bold text-violet-600 dark:text-violet-400 bg-violet-100 dark:bg-violet-950/50 border border-violet-200 dark:border-violet-800 rounded-md size-7 flex items-center justify-center shrink-0 select-none">
                  {letter}
                </span>
                <input
                  type="text"
                  value={subject}
                  disabled={disabled}
                  onChange={(e) => handleSubjectChange(idx, e.target.value)}
                  placeholder={`Subject ${letter} (e.g. ${
                    idx === 0 ? "Binary Search" : idx === 1 ? "Linear Search" : "Hash Table"
                  })`}
                  className="w-full px-3 py-1.5 text-xs bg-card border border-input rounded-lg focus:outline-none focus:ring-1 focus:ring-violet-500 text-foreground disabled:opacity-50"
                  aria-label={`Comparison Subject ${letter}`}
                />
                {isRemovable && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={disabled}
                    onClick={() => handleRemoveSubject(idx)}
                    className="p-1 size-7 text-muted-foreground hover:text-red-500 shrink-0 cursor-pointer"
                    aria-label={`Remove Subject ${letter}`}
                  >
                    <X className="size-3.5" />
                  </Button>
                )}
              </div>
            );
          })}
        </div>

        {subjects.length < 4 && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={disabled}
            onClick={handleAddSubject}
            className="text-[11px] font-semibold text-violet-600 dark:text-violet-400 border-dashed border-violet-300 dark:border-violet-800 hover:bg-violet-50 dark:hover:bg-violet-950/20 w-full py-1.5 flex items-center justify-center gap-1 cursor-pointer"
          >
            <Plus className="size-3" /> Add Subject ({String.fromCharCode(65 + subjects.length)})
          </Button>
        )}
      </div>

      {/* Optional Dimensions */}
      <div className="flex flex-col gap-1.5 pt-2 border-t border-dashed border-border">
        <label
          htmlFor="comparison-dimensions-input"
          className="text-[11px] font-semibold text-muted-foreground flex justify-between"
        >
          <span>Target Dimensions (Optional):</span>
          <span className="text-[10px] text-muted-foreground italic">Comma-separated</span>
        </label>
        <input
          id="comparison-dimensions-input"
          type="text"
          value={dimensions}
          disabled={disabled}
          onChange={(e) => onDimensionsChange(e.target.value)}
          placeholder="e.g. Time Complexity, Space Complexity, Prerequisites"
          className="w-full px-3 py-1.5 text-xs bg-card border border-input rounded-lg focus:outline-none focus:ring-1 focus:ring-violet-500 text-foreground disabled:opacity-50"
        />
      </div>
    </fieldset>
  );
};

export default ComparisonControls;
