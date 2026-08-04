import * as React from "react";
import { cn } from "@/lib/utils";
import { AlertCircle, CheckCircle, type LucideIcon, RefreshCw, XCircle } from "lucide-react";
import { Button } from "./button";

// 1. Spinner Loader
export function Spinner({ className, size = "md" }: { className?: string; size?: "sm" | "md" | "lg" }) {
  const sizeMap = {
    sm: "size-4 border-2",
    md: "size-8 border-3",
    lg: "size-12 border-4",
  };

  return (
    <div
      className={cn(
        "animate-spin rounded-full border-muted-foreground/20 border-t-primary",
        sizeMap[size],
        className
      )}
      role="status"
    />
  );
}

// 2. Skeleton Loader
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-muted/70 dark:bg-muted/50", className)}
      {...props}
    />
  );
}

// 3. Empty State
interface EmptyStateProps {
  title: string;
  description: string;
  icon?: LucideIcon;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({ title, description, icon: Icon, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center p-8 border border-dashed border-border/60 rounded-xl bg-muted/10",
        className
      )}
    >
      {Icon && (
        <div className="flex size-12 items-center justify-center rounded-xl bg-muted text-muted-foreground mb-4">
          <Icon className="size-6" />
        </div>
      )}
      <h3 className="font-semibold text-base text-foreground mb-1">{title}</h3>
      <p className="text-sm text-muted-foreground max-w-sm mb-5 leading-normal">{description}</p>
      {action && <div>{action}</div>}
    </div>
  );
}

// 4. Error State
interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({ title = "Something went wrong", message, onRetry, className }: ErrorStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center p-6 border border-destructive/20 rounded-xl bg-destructive/5 max-w-md mx-auto",
        className
      )}
    >
      <div className="flex size-10 items-center justify-center rounded-lg bg-destructive/10 text-destructive mb-3">
        <AlertCircle className="size-5" />
      </div>
      <h4 className="font-semibold text-sm text-foreground mb-1">{title}</h4>
      <p className="text-xs text-muted-foreground mb-4 leading-relaxed">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} className="gap-1.5">
          <RefreshCw className="size-3" /> Retry
        </Button>
      )}
    </div>
  );
}

// 5. Success Alert
export function SuccessAlert({
  title,
  message,
  className,
}: {
  title: string;
  message: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex gap-3 p-4 border border-emerald-500/20 bg-emerald-500/5 text-emerald-800 dark:text-emerald-400 rounded-xl",
        className
      )}
    >
      <CheckCircle className="size-5 text-emerald-600 dark:text-emerald-400 mt-0.5 shrink-0" />
      <div>
        <h4 className="font-semibold text-sm leading-none">{title}</h4>
        <p className="text-xs mt-1 text-muted-foreground dark:text-emerald-400/80 leading-normal">{message}</p>
      </div>
    </div>
  );
}

// 6. Toast Notification Interface
export interface ToastProps {
  id: string;
  type: "success" | "error" | "info" | "warning";
  title: string;
  message?: string;
  duration?: number;
}

export function ToastNotification({
  type,
  title,
  message,
  onClose,
}: {
  type: ToastProps["type"];
  title: string;
  message?: string;
  onClose: () => void;
}) {
  const iconMap = {
    success: <CheckCircle className="size-4 text-emerald-600 dark:text-emerald-400" />,
    error: <XCircle className="size-4 text-red-600 dark:text-red-400" />,
    warning: <AlertCircle className="size-4 text-amber-600 dark:text-amber-400" />,
    info: <AlertCircle className="size-4 text-blue-600 dark:text-blue-400" />,
  };

  const styleMap = {
    success: "border-emerald-500/20 dark:bg-emerald-950/20",
    error: "border-red-500/20 dark:bg-red-950/20",
    warning: "border-amber-500/20 dark:bg-amber-950/20",
    info: "border-blue-500/20 dark:bg-blue-950/20",
  };

  return (
    <div
      className={cn(
        "flex gap-3 items-start p-4 bg-background border rounded-xl shadow-lg w-full max-w-sm pointer-events-auto transition-all animate-in fade-in slide-in-from-bottom-5",
        styleMap[type]
      )}
    >
      <div className="mt-0.5">{iconMap[type]}</div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-foreground leading-none">{title}</p>
        {message && <p className="text-xs text-muted-foreground mt-1 leading-normal">{message}</p>}
      </div>
      <button
        onClick={onClose}
        className="text-muted-foreground hover:text-foreground p-0.5 rounded-sm outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        <span className="sr-only">Close</span>
        <svg className="size-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}
