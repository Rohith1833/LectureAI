import type { FC } from "react";
import type { GenerationMode } from "@/types/generation";
import { GENERATION_MODES } from "@/constants/generationModes";

interface GenerationModeSelectorProps {
  currentMode: GenerationMode;
  onModeChange: (mode: GenerationMode) => void;
  disabled?: boolean;
}

export const GenerationModeSelector: FC<GenerationModeSelectorProps> = ({
  currentMode,
  onModeChange,
  disabled = false,
}) => {
  return (
    <div className="w-full flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
          Generation Mode
        </label>
        <span className="text-[11px] text-muted-foreground hidden sm:inline">
          Select an AI generation workflow
        </span>
      </div>

      <div
        role="tablist"
        aria-label="Generation Modes"
        className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 p-1.5 bg-muted/60 dark:bg-muted/30 border border-border rounded-xl"
      >
        {GENERATION_MODES.map((mode) => {
          const Icon = mode.icon;
          const isSelected = currentMode === mode.key;

          return (
            <button
              key={mode.key}
              type="button"
              role="tab"
              aria-selected={isSelected}
              disabled={disabled}
              onClick={() => onModeChange(mode.key)}
              className={`flex flex-col items-start gap-1.5 p-2.5 sm:p-3 rounded-lg text-left transition-all duration-200 cursor-pointer select-none relative disabled:opacity-50 disabled:cursor-not-allowed ${
                isSelected
                  ? "bg-card text-foreground shadow-xs border border-violet-500/30 dark:border-violet-400/30 ring-1 ring-violet-500/20"
                  : "text-muted-foreground hover:text-foreground hover:bg-card/50 border border-transparent"
              }`}
            >
              <div className="flex items-center justify-between w-full">
                <div
                  className={`p-1.5 rounded-md ${
                    isSelected
                      ? "bg-violet-600 text-white shadow-xs"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  <Icon className="size-3.5 sm:size-4 shrink-0" />
                </div>
                {isSelected && (
                  <span className="size-1.5 rounded-full bg-violet-600 animate-pulse" />
                )}
              </div>

              <div className="flex flex-col">
                <span
                  className={`text-xs font-bold truncate ${
                    isSelected ? "text-foreground" : "text-muted-foreground"
                  }`}
                >
                  {mode.shortLabel}
                </span>
                <span className="text-[10px] text-muted-foreground line-clamp-1 hidden md:block">
                  {mode.description}
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default GenerationModeSelector;
