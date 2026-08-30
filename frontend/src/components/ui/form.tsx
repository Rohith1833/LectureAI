import * as React from "react";
import { useState, useContext } from "react";
import { cn } from "@/lib/utils";
import { ChevronDown, Check, Upload, FileUp } from "lucide-react";

// ========================
// 1. INPUT COMPONENT
// ========================
export interface InputProps extends React.ComponentProps<"input"> {
  label?: string;
  helperText?: string;
  error?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type = "text", label, helperText, error, id, ...props }, ref) => {
    const generatedId = React.useId();
    const inputId = id || generatedId;
    return (
      <div className="w-full space-y-1.5">
        {label && (
          <label htmlFor={inputId} className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {label}
          </label>
        )}
        <input
          ref={ref}
          type={type}
          id={inputId}
          className={cn(
            "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50",
            error && "border-destructive focus-visible:ring-destructive/20 focus-visible:border-destructive",
            className
          )}
          {...props}
        />
        {error ? (
          <p className="text-xs text-destructive">{error}</p>
        ) : (
          helperText && <p className="text-xs text-muted-foreground">{helperText}</p>
        )}
      </div>
    );
  }
);
Input.displayName = "Input";

// ========================
// 2. TEXTAREA COMPONENT
// ========================
export interface TextareaProps extends React.ComponentProps<"textarea"> {
  label?: string;
  helperText?: string;
  error?: string;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, label, helperText, error, id, ...props }, ref) => {
    const generatedId = React.useId();
    const textareaId = id || generatedId;
    return (
      <div className="w-full space-y-1.5">
        {label && (
          <label htmlFor={textareaId} className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={textareaId}
          className={cn(
            "flex min-h-[60px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50",
            error && "border-destructive focus-visible:ring-destructive/20 focus-visible:border-destructive",
            className
          )}
          {...props}
        />
        {error ? (
          <p className="text-xs text-destructive">{error}</p>
        ) : (
          helperText && <p className="text-xs text-muted-foreground">{helperText}</p>
        )}
      </div>
    );
  }
);
Textarea.displayName = "Textarea";

// ========================
// 3. SWITCH COMPONENT (shadcn API Compatible)
// ========================
export interface SwitchProps extends Omit<React.ComponentProps<"button">, "value" | "onChange"> {
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  label?: string;
}

export const Switch = React.forwardRef<HTMLButtonElement, SwitchProps>(
  ({ className, checked = false, onCheckedChange, label, ...props }, ref) => {
    const buttonId = React.useId();

    const handleKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
      if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        onCheckedChange?.(!checked);
      }
    };

    return (
      <div className="flex items-center gap-3">
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          id={buttonId}
          ref={ref}
          onKeyDown={handleKeyDown}
          onClick={() => onCheckedChange?.(!checked)}
          className={cn(
            "peer inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border border-transparent shadow-xs transition-colors outline-none focus-visible:ring-ring/50 focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50",
            checked ? "bg-primary" : "bg-muted",
            className
          )}
          {...props}
        >
          <span
            className={cn(
              "pointer-events-none block size-4 rounded-full bg-background shadow-lg ring-0 transition-transform duration-200",
              checked ? "translate-x-4" : "translate-x-0.5"
            )}
          />
        </button>
        {label && (
          <label htmlFor={buttonId} className="text-sm font-medium text-foreground cursor-pointer select-none">
            {label}
          </label>
        )}
      </div>
    );
  }
);
Switch.displayName = "Switch";

// ========================
// 4. SLIDER COMPONENT (shadcn API Compatible)
// ========================
export interface SliderProps {
  min?: number;
  max?: number;
  step?: number;
  value: number[];
  onValueChange: (value: number[]) => void;
  label?: string;
  className?: string;
}

export function Slider({ min = 0, max = 100, step = 1, value, onValueChange, label, className }: SliderProps) {
  const currentValue = value[0] ?? min;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    onValueChange([val]);
  };

  const percentage = ((currentValue - min) / (max - min)) * 100;

  return (
    <div className={cn("w-full space-y-2", className)}>
      <div className="flex items-center justify-between">
        {label && <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>}
        <span className="text-sm font-semibold text-primary">{currentValue}</span>
      </div>
      <div className="relative flex items-center w-full h-5 select-none touch-none">
        {/* Track */}
        <div className="relative w-full h-1.5 rounded-full bg-muted overflow-hidden">
          <div
            className="absolute h-full bg-primary rounded-full"
            style={{ width: `${percentage}%` }}
          />
        </div>
        {/* Range Input element overlaying slider styling */}
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={currentValue}
          onChange={handleChange}
          className="absolute w-full h-full opacity-0 cursor-pointer"
        />
        {/* Thumb visualization */}
        <div
          className="absolute pointer-events-none size-4 rounded-full border border-primary/50 bg-background shadow-xs transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50"
          style={{
            left: `calc(${percentage}% - 8px)`,
          }}
        />
      </div>
    </div>
  );
}

// ========================
// 5. SELECT COMPONENT (shadcn/ui API structure compatible)
// ========================
interface SelectContextType {
  value?: string;
  onValueChange?: (value: string) => void;
  open: boolean;
  setOpen: (open: boolean) => void;
  selectedValueLabel: string;
  setSelectedValueLabel: (label: string) => void;
}

const SelectContext = React.createContext<SelectContextType | undefined>(undefined);

export function Select({
  children,
  value,
  onValueChange,
}: {
  children: React.ReactNode;
  value?: string;
  onValueChange?: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [selectedValueLabel, setSelectedValueLabel] = useState("");

  const containerRef = React.useRef<HTMLDivElement>(null);

  // Close dropdown on click outside
  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <SelectContext.Provider value={{ value, onValueChange, open, setOpen, selectedValueLabel, setSelectedValueLabel }}>
      <div ref={containerRef} className="relative w-full">
        {children}
      </div>
    </SelectContext.Provider>
  );
}

export function SelectTrigger({ className, children, ...props }: React.ComponentPropsWithoutRef<"button">) {
  const context = useContext(SelectContext);
  if (!context) throw new Error("SelectTrigger must be used inside Select");

  return (
    <button
      type="button"
      onClick={() => context.setOpen(!context.open)}
      className={cn(
        "flex h-9 w-full items-center justify-between rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus:border-ring focus:ring-ring/50 focus:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50 text-left cursor-pointer",
        className
      )}
      {...props}
    >
      {children || <span>{context.selectedValueLabel}</span>}
      <ChevronDown className="size-4 opacity-50 shrink-0" />
    </button>
  );
}

export function SelectValue({ placeholder }: { placeholder?: string }) {
  const context = useContext(SelectContext);
  if (!context) throw new Error("SelectValue must be used inside Select");

  return (
    <span className="truncate text-sm">
      {context.selectedValueLabel || placeholder}
    </span>
  );
}

export function SelectContent({ className, children }: { className?: string; children: React.ReactNode }) {
  const context = useContext(SelectContext);
  if (!context) throw new Error("SelectContent must be used inside Select");

  if (!context.open) return null;

  return (
    <div
      className={cn(
        "absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md animate-in fade-in slide-in-from-top-1 duration-100",
        className
      )}
    >
      {children}
    </div>
  );
}

export function SelectItem({
  value,
  children,
  className,
}: {
  value: string;
  children: React.ReactNode;
  className?: string;
}) {
  const context = useContext(SelectContext);
  if (!context) throw new Error("SelectItem must be used inside Select");

  const isSelected = context.value === value;

  const itemRef = React.useRef<HTMLDivElement>(null);

  // Sync initial label if selected
  React.useEffect(() => {
    if (isSelected && children) {
      context.setSelectedValueLabel(String(children));
    }
  }, [isSelected, children]);

  const handleSelect = () => {
    context.onValueChange?.(value);
    context.setSelectedValueLabel(String(children));
    context.setOpen(false);
  };

  return (
    <div
      ref={itemRef}
      onClick={handleSelect}
      className={cn(
        "relative flex w-full cursor-pointer select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-hidden hover:bg-accent hover:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
        isSelected && "bg-accent/40 font-medium",
        className
      )}
    >
      {isSelected && (
        <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
          <Check className="size-3.5 text-primary" />
        </span>
      )}
      <span className="truncate">{children}</span>
    </div>
  );
}

// ========================
// 6. PROGRESS BAR
// ========================
export function ProgressBar({
  value,
  max = 100,
  label,
  className,
}: {
  value: number;
  max?: number;
  label?: string;
  className?: string;
}) {
  const percentage = Math.min(Math.max((value / max) * 100, 0), 100);

  return (
    <div className={cn("w-full space-y-1.5", className)}>
      <div className="flex items-center justify-between text-xs font-semibold tracking-wide text-muted-foreground">
        {label && <span className="uppercase">{label}</span>}
        <span>{Math.round(percentage)}%</span>
      </div>
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        <div
          className="h-full bg-primary rounded-full transition-all duration-300 ease-out"
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

// ========================
// 7. FILE DROPZONE (PDF Only / UI Only)
// ========================
interface FileDropzoneProps {
  onFileSelect?: (file: File) => void;
  className?: string;
}

export function FileDropzone({ onFileSelect, className }: FileDropzoneProps) {
  const [dragOver, setDragOver] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => {
    setDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);

    const files = Array.from(e.dataTransfer.files);
    const pdfFile = files.find((file) => file.type === "application/pdf" || file.name.endsWith(".pdf"));

    if (pdfFile) {
      onFileSelect?.(pdfFile);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files[0]) {
      onFileSelect?.(files[0]);
    }
  };

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className={cn(
        "flex flex-col items-center justify-center border-2 border-dashed border-border/60 hover:border-violet-500 rounded-xl bg-card p-10 text-center transition-all cursor-pointer shadow-xs",
        dragOver && "border-violet-500 bg-violet-500/5 dark:bg-violet-950/5",
        className
      )}
    >
      <input
        type="file"
        ref={inputRef}
        onChange={handleFileChange}
        accept="application/pdf"
        className="hidden"
      />
      <div className="flex size-14 items-center justify-center rounded-2xl bg-violet-500/10 text-violet-600 dark:bg-violet-500/20 dark:text-violet-400 mb-4 transition-transform hover:scale-105">
        <FileUp className="size-7" />
      </div>
      <h3 className="font-semibold text-lg text-foreground mb-1.5">Drag & Drop PDF here</h3>
      <p className="text-sm text-muted-foreground max-w-sm mb-4 leading-relaxed">
        Click to browse or drag file. Only PDF files are supported for processing at this time.
      </p>
      <div className="inline-flex items-center gap-1.5 rounded-full bg-muted/60 px-3 py-1 text-xs text-muted-foreground border border-border/40">
        <Upload className="size-3" /> Max size: 50MB
      </div>
    </div>
  );
}
