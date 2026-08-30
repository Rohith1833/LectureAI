import type { FC } from "react";
import { GraduationCap, Minus, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

interface StudyGuideControlsProps {
  questionCount: number;
  difficulty: "basic" | "intermediate" | "advanced";
  onQuestionCountChange: (count: number) => void;
  onDifficultyChange: (diff: "basic" | "intermediate" | "advanced") => void;
  disabled?: boolean;
}

const DIFFICULTIES: {
  key: "basic" | "intermediate" | "advanced";
  label: string;
  desc: string;
}[] = [
  { key: "basic", label: "Basic", desc: "Foundational concepts & definitions" },
  { key: "intermediate", label: "Intermediate", desc: "Standard application & analysis" },
  { key: "advanced", label: "Advanced", desc: "In-depth synthesis & edge cases" },
];

export const StudyGuideControls: FC<StudyGuideControlsProps> = ({
  questionCount,
  difficulty,
  onQuestionCountChange,
  onDifficultyChange,
  disabled = false,
}) => {
  const handleDecrement = () => {
    if (questionCount > 1) {
      onQuestionCountChange(questionCount - 1);
    }
  };

  const handleIncrement = () => {
    if (questionCount < 10) {
      onQuestionCountChange(questionCount + 1);
    }
  };

  return (
    <fieldset className="flex flex-col gap-3.5 p-3.5 bg-muted/40 dark:bg-muted/20 border border-border rounded-xl">
      <legend className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5 px-1">
        <GraduationCap className="size-3.5 text-violet-600" />
        Study Guide Configuration
      </legend>

      {/* Question Count Stepper */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex flex-col">
          <label className="text-[11px] font-semibold text-muted-foreground">
            Review Questions Count:
          </label>
          <span className="text-[10px] text-muted-foreground">
            Bounded between 1 and 10 questions
          </span>
        </div>

        <div className="flex items-center gap-1.5 bg-card border border-input rounded-lg p-1 shadow-2xs">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={disabled || questionCount <= 1}
            onClick={handleDecrement}
            className="size-6 p-0 text-muted-foreground hover:text-foreground cursor-pointer disabled:opacity-30"
            aria-label="Decrease question count"
          >
            <Minus className="size-3" />
          </Button>

          <span
            className="w-6 text-center text-xs font-bold text-foreground font-mono select-none"
            aria-live="polite"
          >
            {questionCount}
          </span>

          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={disabled || questionCount >= 10}
            onClick={handleIncrement}
            className="size-6 p-0 text-muted-foreground hover:text-foreground cursor-pointer disabled:opacity-30"
            aria-label="Increase question count"
          >
            <Plus className="size-3" />
          </Button>
        </div>
      </div>

      {/* Difficulty Selector */}
      <div className="flex flex-col gap-1.5 pt-2 border-t border-dashed border-border">
        <label className="text-[11px] font-semibold text-muted-foreground">
          Cognitive Difficulty Level:
        </label>
        <div
          role="radiogroup"
          aria-label="Study Guide Difficulty"
          className="grid grid-cols-3 gap-1.5 p-1 bg-muted/60 dark:bg-muted/40 rounded-lg border border-border"
        >
          {DIFFICULTIES.map((d) => {
            const isSelected = difficulty === d.key;

            return (
              <button
                key={d.key}
                type="button"
                role="radio"
                aria-checked={isSelected}
                disabled={disabled}
                onClick={() => onDifficultyChange(d.key)}
                className={`py-1.5 px-2 rounded-md text-[11px] font-bold text-center transition-all duration-150 cursor-pointer select-none disabled:opacity-50 ${
                  isSelected
                    ? "bg-card text-violet-700 dark:text-violet-300 shadow-2xs border border-violet-500/30"
                    : "text-muted-foreground hover:text-foreground hover:bg-card/40 border border-transparent"
                }`}
                title={d.desc}
              >
                {d.label}
              </button>
            );
          })}
        </div>
      </div>
    </fieldset>
  );
};

export default StudyGuideControls;
