import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { InfoCard } from "@/components/ui/card";
import { ProgressBar } from "@/components/ui/form";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/feedback";
import {
  Check,
  ArrowRight,
  Loader2,
  FileText,
  Cpu,
  ListTodo,
  Presentation,
  ShieldCheck,
  Download,
  AlertTriangle,
} from "lucide-react";
import { getJobStatus } from "@/services/jobService";

interface Step {
  stage: string;
  label: string;
  desc: string;
  icon: any;
}

const steps: Step[] = [
  { stage: "Preparing", label: "Preparing Workspace", desc: "Initializing runtime configuration settings.", icon: Cpu },
  { stage: "Reading Document", label: "Reading Document", desc: "Extracting document structures and pages.", icon: FileText },
  { stage: "OCR", label: "OCR Processing", desc: "Detecting formula syntax, figures, and scanned texts.", icon: Cpu },
  { stage: "Unit Detection", label: "Detecting Units", desc: "Structuring learning modules and textbook chapters.", icon: ListTodo },
  { stage: "Outline Generation", label: "Building Outline", desc: "Compiling learning objectives and outline targets.", icon: FileText },
  { stage: "Content Generation", label: "Generating Content", desc: "Drafting slides, titles, and speaker narratives.", icon: Presentation },
  { stage: "Visual Generation", label: "Visual Processing", desc: "Injecting aesthetic layouts, design tokens, and images.", icon: Presentation },
  { stage: "Quality Review", label: "Quality Review", desc: "Validating logical flow and educational completeness.", icon: ShieldCheck },
  { stage: "PPT Generation", label: "PPT Generation", desc: "Compiling output slides into PowerPoint buffers.", icon: Download },
  { stage: "Export", label: "Ready to Export", desc: "Structuring final presentations download links.", icon: Download },
];

export default function ProcessingPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  // Poll status endpoint every 2 seconds until completed, failed or cancelled
  const { data, error, isPending } = useQuery({
    queryKey: ["jobStatus", jobId],
    queryFn: () => getJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.data?.status;
      if (status === "completed" || status === "failed" || status === "cancelled") {
        return false;
      }
      return 2000;
    },
  });

  const job = data?.data;

  const handleContinue = () => {
    navigate("/units");
  };

  const handleRetryUpload = () => {
    navigate("/upload");
  };

  const getStepStatus = (stepStage: string): "idle" | "running" | "completed" | "failed" => {
    if (!job) return "idle";
    if (job.status === "completed") return "completed";
    if (job.status === "failed") {
      if (job.current_stage === stepStage) return "failed";
      const failedIdx = steps.findIndex((s) => s.stage === job.current_stage);
      const currentIdx = steps.findIndex((s) => s.stage === stepStage);
      if (currentIdx < failedIdx) return "completed";
      return "idle";
    }

    const activeIdx = steps.findIndex((s) => s.stage === job.current_stage);
    const currentIdx = steps.findIndex((s) => s.stage === stepStage);

    if (currentIdx < activeIdx) return "completed";
    if (currentIdx === activeIdx) return "running";
    return "idle";
  };

  if (isPending) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="text-center space-y-4">
          <Spinner size="lg" />
          <p className="text-sm text-muted-foreground">Connecting to processing pipeline...</p>
        </div>
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="space-y-6 py-6 max-w-2xl mx-auto">
        <div className="flex gap-3 p-4 border border-red-500/20 bg-red-500/5 text-red-700 dark:text-red-400 rounded-xl">
          <AlertTriangle className="size-5 shrink-0" />
          <div className="space-y-1">
            <h4 className="font-semibold text-sm">Failed to Load Job Status</h4>
            <p className="text-xs leading-normal">
              Could not retrieve status details for job ID: <code>{jobId}</code>. Please check your network and try again.
            </p>
          </div>
        </div>
        <div className="flex justify-center gap-3">
          <Button variant="outline" onClick={handleRetryUpload}>
            Back to Upload
          </Button>
        </div>
      </div>
    );
  }

  const isFailed = job.status === "failed";
  const isCompleted = job.status === "completed";

  return (
    <div className="space-y-8 py-6 max-w-4xl mx-auto">
      {/* Accessibility Screen Reader Announcer */}
      <div aria-live="polite" className="sr-only">
        {`Job status is ${job.status}, stage is ${job.current_stage}, progress is ${job.progress}%`}
      </div>

      {/* Header */}
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">AI Pipeline Processing</h1>
        <p className="text-sm text-muted-foreground max-w-lg mx-auto">
          Our cooperative agent team is analyzing your textbook. Check status updates below.
        </p>
      </div>

      {/* Error Banner */}
      {isFailed && (
        <div className="flex gap-3 p-4 border border-red-500/20 bg-red-500/5 text-red-700 dark:text-red-400 rounded-xl animate-in fade-in duration-200">
          <AlertTriangle className="size-5 shrink-0" />
          <div className="space-y-1">
            <h4 className="font-semibold text-sm">Processing Failure Detected</h4>
            <p className="text-xs leading-normal">
              Error details: {job.error || "An unknown error occurred inside the agent runtime."}
            </p>
          </div>
        </div>
      )}

      {/* Progress Card */}
      <InfoCard
        title="Extraction Progress"
        description={`Job ID: ${job.job_id}`}
        className="border border-border/40 bg-card/50"
      >
        <div className="space-y-4">
          <ProgressBar value={job.progress} label="Pipeline Execution" />
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              Active Stage: <strong>{job.current_stage}</strong>
            </span>
            {isCompleted ? (
              <span className="text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1">
                <Check className="size-3.5" /> All systems completed
              </span>
            ) : isFailed ? (
              <span className="text-red-600 dark:text-red-400 font-semibold flex items-center gap-1">
                Pipeline execution aborted
              </span>
            ) : (
              <span className="flex items-center gap-1.5">
                <Loader2 className="size-3.5 animate-spin text-primary" /> processing...
              </span>
            )}
          </div>
        </div>
      </InfoCard>

      {/* Steps List */}
      <div className="grid gap-4 sm:grid-cols-2">
        {steps.map((step) => {
          const Icon = step.icon;
          const statusVal = getStepStatus(step.stage);

          return (
            <div
              key={step.stage}
              className={`flex items-start gap-4 p-4 rounded-xl border transition-all duration-300 ${
                statusVal === "completed"
                  ? "border-emerald-500/20 bg-emerald-500/5 dark:bg-emerald-950/5 text-emerald-800 dark:text-emerald-400"
                  : statusVal === "running"
                  ? "border-violet-500/30 bg-violet-500/5 dark:bg-violet-950/5 shadow-md shadow-violet-500/5 animate-pulse"
                  : statusVal === "failed"
                  ? "border-red-500/30 bg-red-500/5 text-red-800 dark:text-red-400"
                  : "border-border/60 bg-muted/20 opacity-60"
              }`}
            >
              <div
                className={`p-2 rounded-lg ${
                  statusVal === "completed"
                    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                    : statusVal === "running"
                    ? "bg-violet-500/10 text-violet-600 dark:text-violet-400"
                    : statusVal === "failed"
                    ? "bg-red-500/10 text-red-600 dark:text-red-400"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {statusVal === "running" ? (
                  <Loader2 className="size-4.5 animate-spin" />
                ) : (
                  <Icon className="size-4.5" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold text-sm">{step.label}</h4>
                  {statusVal === "completed" && <Check className="size-4 text-emerald-600" />}
                  {statusVal === "failed" && <AlertTriangle className="size-4 text-red-600" />}
                </div>
                <p className="text-xs text-muted-foreground mt-0.5 leading-normal">{step.desc}</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Action Footer */}
      {(isCompleted || isFailed) && (
        <div className="flex justify-center gap-4 pt-4 animate-in fade-in zoom-in-95 duration-300">
          {isFailed && (
            <Button onClick={handleRetryUpload} size="lg" variant="outline">
              Back to Upload
            </Button>
          )}
          {isCompleted && (
            <div className="flex flex-col sm:flex-row gap-3">
              {job.document_id && (
                <Button
                  onClick={() => navigate(`/documents/${job.document_id}`)}
                  variant="outline"
                  size="lg"
                  className="gap-2 border-violet-500/30 text-violet-600 dark:text-violet-400 font-semibold hover:bg-violet-500/5 cursor-pointer"
                >
                  <Cpu className="size-4" /> Developer Preview
                </Button>
              )}
              <Button
                onClick={handleContinue}
                size="lg"
                className="gap-2 bg-violet-600 hover:bg-violet-700 text-white dark:bg-violet-500 dark:hover:bg-violet-600 font-semibold shadow-lg cursor-pointer"
              >
                Review Extracted Chapters <ArrowRight className="size-4" />
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
