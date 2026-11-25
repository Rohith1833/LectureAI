import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  Download,
  FileText,
  Info,
  Loader2,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import SlidePreview from "@/components/SlidePreview";
import { uploadTextbookFile } from "@/services/uploadService";
import {
  getPresentationDownloadUrl,
  getPresentationJobStatus,
  startPresentationGeneration,
} from "@/services/presentationService";
import type {
  PresentationJobStage,
  PresentationJobStatus,
} from "@/types/presentation";

const PROGRESS_STAGES: { key: PresentationJobStage; label: string }[] = [
  { key: "uploading", label: "Uploading document" },
  { key: "analyzing_pdf", label: "Analysing PDF" },
  { key: "extracting_content", label: "Extracting textbook content" },
  { key: "understanding_material", label: "Understanding educational material" },
  { key: "planning_presentation", label: "Planning presentation" },
  { key: "validating_content", label: "Validating content accuracy" },
  { key: "designing_slides", label: "Designing slides" },
  { key: "generating_pptx", label: "Generating PowerPoint" },
];

type SlideCountOption = "auto" | "10" | "15" | "20" | "30" | "custom";

const SLIDE_COUNT_OPTIONS: { value: SlideCountOption; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "10", label: "10 slides" },
  { value: "15", label: "15 slides" },
  { value: "20", label: "20 slides" },
  { value: "30", label: "30 slides" },
  { value: "custom", label: "Custom" },
];

export default function HomePage() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [slideCountOption, setSlideCountOption] = useState<SlideCountOption>("auto");
  const [customSlideCount, setCustomSlideCount] = useState<string>("12");

  const [phase, setPhase] = useState<"idle" | "uploading" | "processing" | "completed" | "failed">("idle");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [job, setJob] = useState<PresentationJobStatus | null>(null);

  const resolveTargetSlideCount = (): { value: number | null; error: string | null } => {
    if (slideCountOption === "auto") {
      return { value: null, error: null };
    }
    if (slideCountOption === "custom") {
      const parsed = Number.parseInt(customSlideCount, 10);
      if (Number.isNaN(parsed) || parsed < 3 || parsed > 120) {
        return { value: null, error: "Custom slide count must be between 3 and 120." };
      }
      return { value: parsed, error: null };
    }
    return { value: Number.parseInt(slideCountOption, 10), error: null };
  };

  const validateAndSelectFile = (file: File) => {
    setErrorMsg(null);
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setErrorMsg("Please select a valid PDF file (.pdf).");
      return;
    }
    if (file.size === 0) {
      setErrorMsg("The selected PDF file is empty.");
      return;
    }
    if (file.size > 100 * 1024 * 1024) {
      setErrorMsg("File exceeds the 100 MB limit.");
      return;
    }
    setSelectedFile(file);
  };

  const handleGenerate = async () => {
    if (!selectedFile) return;

    const { value: targetSlideCount, error: countError } = resolveTargetSlideCount();
    if (countError) {
      setErrorMsg(countError);
      return;
    }

    setErrorMsg(null);
    setPhase("uploading");
    setUploadProgress(0);
    setJob(null);

    try {
      const uploadRes = await uploadTextbookFile(selectedFile, (pct) => {
        setUploadProgress(pct);
      });
      const startedJob = await startPresentationGeneration(
        uploadRes.data.upload_id,
        targetSlideCount
      );
      setJob(startedJob);
      if (startedJob.status === "completed") {
        setPhase("completed");
      } else if (startedJob.status === "failed") {
        setErrorMsg(startedJob.error || "Presentation generation failed.");
        setPhase("failed");
      } else {
        setPhase("processing");
      }
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        "Failed to upload PDF and start presentation generation.";
      setErrorMsg(detail);
      setPhase("failed");
    }
  };

  useEffect(() => {
    if (phase !== "processing" || !job?.job_id) return;

    let cancelled = false;
    const poll = async () => {
      try {
        const updated = await getPresentationJobStatus(job.job_id);
        if (cancelled) return;
        setJob(updated);
        if (updated.status === "completed") {
          setPhase("completed");
        } else if (updated.status === "failed") {
          setErrorMsg(updated.error || "Presentation generation failed.");
          setPhase("failed");
        }
      } catch {
        // Keep polling on transient network hiccups
      }
    };

    const timer = setInterval(poll, 1500);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [phase, job?.job_id]);

  const handleReset = () => {
    setSelectedFile(null);
    setErrorMsg(null);
    setPhase("idle");
    setUploadProgress(0);
    setJob(null);
  };

  const currentStageKey: PresentationJobStage =
    phase === "uploading" ? "uploading" : job?.stage || "analyzing_pdf";

  const activeStageIdx = PROGRESS_STAGES.findIndex((s) => s.key === currentStageKey);
  const overallProgress =
    phase === "uploading"
      ? Math.max(2, Math.round(uploadProgress * 0.08))
      : phase === "completed"
      ? 100
      : job?.progress ?? 8;

  const deckNotice = job?.notice || job?.deck?.notice;
  const validationReport = job?.deck?.validation_report;

  return (
    <div className="mx-auto max-w-4xl py-8 space-y-12">
      {/* Header */}
      <section className="text-center space-y-4">
        <div className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/50 px-3.5 py-1 text-xs font-medium text-muted-foreground">
          <Sparkles className="size-3.5 text-indigo-600 dark:text-indigo-400" />
          AI Textbook-to-PowerPoint Generator
        </div>
        <h1 className="text-3xl sm:text-5xl font-bold tracking-tight text-foreground">
          Turn Your Textbook PDF into{" "}
          <span className="bg-gradient-to-r from-indigo-600 to-teal-500 bg-clip-text text-transparent">
            Presentation Slides
          </span>
        </h1>
        <p className="mx-auto max-w-2xl text-base text-muted-foreground leading-relaxed">
          Upload any digital or scanned textbook PDF. LectureAI extracts the content,
          organizes key concepts and examples, and builds a ready-to-teach PowerPoint deck.
        </p>
      </section>

      {/* Main Card */}
      <section className="rounded-2xl border border-border bg-card p-6 sm:p-8 shadow-sm space-y-6">
        {errorMsg && (
          <div className="flex items-start gap-3 rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-700 dark:text-red-400">
            <AlertCircle className="size-5 shrink-0 mt-0.5" />
            <div className="flex-1 space-y-1">
              <p className="font-semibold">Unable to Complete Request</p>
              <p className="text-xs leading-relaxed opacity-90">{errorMsg}</p>
            </div>
          </div>
        )}

        {/* IDLE / UPLOAD STATE */}
        {(phase === "idle" || (phase === "failed" && !job)) && (
          <div className="space-y-6">
            {!selectedFile ? (
              <div
                role="button"
                tabIndex={0}
                onClick={() => fileInputRef.current?.click()}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragging(true);
                }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                  const f = e.dataTransfer.files?.[0];
                  if (f) validateAndSelectFile(f);
                }}
                className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-12 text-center transition-colors cursor-pointer ${
                  isDragging
                    ? "border-indigo-500 bg-indigo-50/50 dark:bg-indigo-950/20"
                    : "border-border hover:border-indigo-400 hover:bg-muted/30"
                }`}
              >
                <div className="flex size-14 items-center justify-center rounded-2xl bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 mb-4">
                  <UploadCloud className="size-7" />
                </div>
                <p className="text-base font-semibold text-foreground">
                  Drop your textbook PDF here, or click to browse
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Supports digital, scanned, and mixed PDFs up to 100 MB
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,application/pdf"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) validateAndSelectFile(f);
                    e.target.value = "";
                  }}
                />
              </div>
            ) : (
              <div className="flex items-center justify-between gap-4 rounded-xl border border-indigo-500/30 bg-indigo-500/5 p-4">
                <div className="flex items-center gap-3.5 min-w-0">
                  <div className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white">
                    <FileText className="size-5" />
                  </div>
                  <div className="min-w-0">
                    <p className="font-semibold text-sm truncate text-foreground">
                      {selectedFile.name}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • PDF Document
                    </p>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleReset}
                  aria-label="Remove file"
                  className="text-muted-foreground hover:text-destructive"
                >
                  <Trash2 className="size-4" />
                </Button>
              </div>
            )}

            {/* Minimal Slide Count Selector */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-border/70 bg-muted/20 px-4 py-3">
              <span className="text-xs font-medium text-muted-foreground">
                Presentation length
              </span>
              <div className="flex flex-wrap items-center gap-1.5">
                {SLIDE_COUNT_OPTIONS.map((opt) => {
                  const active = slideCountOption === opt.value;
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => {
                        setSlideCountOption(opt.value);
                        setErrorMsg(null);
                      }}
                      className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors cursor-pointer ${
                        active
                          ? "bg-indigo-600 text-white shadow-2xs"
                          : "bg-background border border-border text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {opt.label}
                    </button>
                  );
                })}
                {slideCountOption === "custom" && (
                  <input
                    type="number"
                    min={3}
                    max={120}
                    aria-label="Custom slide count"
                    value={customSlideCount}
                    onChange={(e) => {
                      setCustomSlideCount(e.target.value);
                      setErrorMsg(null);
                    }}
                    className="w-20 rounded-lg border border-border bg-background px-2.5 py-1 text-xs font-medium text-foreground focus:border-indigo-500 focus:outline-hidden"
                    placeholder="Slides"
                  />
                )}
              </div>
            </div>

            <div className="flex justify-center">
              <Button
                size="lg"
                disabled={!selectedFile}
                onClick={handleGenerate}
                className="w-full sm:w-auto px-8 gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold shadow-sm cursor-pointer"
              >
                <Sparkles className="size-4" /> Generate PPT
              </Button>
            </div>
          </div>
        )}

        {/* PROCESSING STATE */}
        {phase === "processing" || phase === "uploading" ? (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-foreground">
                  Creating Your Presentation
                </h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {phase === "uploading"
                    ? `Uploading ${selectedFile?.name}...`
                    : job?.detail || "Working on your textbook..."}
                </p>
              </div>
              <span className="text-sm font-bold text-indigo-600 dark:text-indigo-400">
                {overallProgress}%
              </span>
            </div>

            <div className="h-2.5 w-full rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-indigo-600 to-teal-500 transition-all duration-300"
                style={{ width: `${overallProgress}%` }}
              />
            </div>

            <div className="grid gap-2.5 sm:grid-cols-2">
              {PROGRESS_STAGES.map((st, idx) => {
                const isDone = activeStageIdx > idx;
                const isActive = activeStageIdx === idx;
                return (
                  <div
                    key={st.key}
                    className={`flex items-center gap-3 rounded-xl border px-3.5 py-2.5 text-sm transition-colors ${
                      isDone
                        ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400"
                        : isActive
                        ? "border-indigo-500/30 bg-indigo-500/5 text-foreground font-medium"
                        : "border-border/50 bg-muted/20 text-muted-foreground opacity-60"
                    }`}
                  >
                    {isDone ? (
                      <CheckCircle2 className="size-4 shrink-0 text-emerald-600" />
                    ) : isActive ? (
                      <Loader2 className="size-4 shrink-0 animate-spin text-indigo-600" />
                    ) : (
                      <div className="size-4 shrink-0 rounded-full border border-muted-foreground/40" />
                    )}
                    <span className="text-xs sm:text-sm">{st.label}</span>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}

        {/* FAILED AFTER JOB STARTED */}
        {phase === "failed" && job && (
          <div className="flex justify-center pt-2">
            <Button variant="outline" onClick={handleReset} className="gap-2">
              <RotateCcw className="size-4" /> Try Another PDF
            </Button>
          </div>
        )}

        {/* COMPLETED STATE: PREVIEW + DOWNLOAD */}
        {phase === "completed" && job?.deck && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-4">
              <div>
                <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400 text-xs font-semibold uppercase tracking-wider">
                  <CheckCircle2 className="size-4" /> Presentation Ready
                </div>
                <h2 className="text-xl font-bold text-foreground mt-1">
                  {job.deck.title}
                </h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {job.deck.slides.length} slides generated
                  {job.deck.stats?.total_pages
                    ? ` • ${job.deck.stats.total_pages} pages analysed`
                    : ""}
                  {job.deck.stats?.ocr_pages
                    ? ` • ${job.deck.stats.ocr_pages} scanned page(s) processed with OCR`
                    : ""}
                </p>
              </div>

              <div className="flex items-center gap-2.5 shrink-0">
                <Button variant="outline" size="sm" onClick={handleReset} className="gap-1.5">
                  <RotateCcw className="size-3.5" /> New PDF
                </Button>
                <a href={getPresentationDownloadUrl(job.job_id)} download>
                  <Button
                    size="sm"
                    className="gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold shadow-sm cursor-pointer"
                  >
                    <Download className="size-4" /> Download PPTX
                  </Button>
                </a>
              </div>
            </div>

            {deckNotice && (
              <div className="flex items-start gap-2.5 rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-800 dark:text-amber-300">
                <Info className="size-4 shrink-0 mt-0.5" />
                <span>{deckNotice}</span>
              </div>
            )}

            {validationReport && (
              <div className="flex items-start gap-2.5 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-2.5 text-xs text-emerald-800 dark:text-emerald-300">
                <ShieldCheck className="size-4 shrink-0 mt-0.5" />
                <div className="space-y-0.5">
                  <span className="font-semibold">Content Validated: </span>
                  <span>{validationReport.summary}</span>
                </div>
              </div>
            )}

            <SlidePreview deck={job.deck} />
          </div>
        )}
      </section>

      {/* Simple 3-step overview when idle */}
      {phase === "idle" && (
        <section className="grid gap-6 sm:grid-cols-3 text-center">
          {[
            {
              icon: UploadCloud,
              title: "1. Upload PDF",
              desc: "Works with digital textbooks, scanned pages, or mixed documents.",
            },
            {
              icon: BookOpen,
              title: "2. AI Structures Content",
              desc: "Extracts concepts, definitions, examples, and tables into clear slides.",
            },
            {
              icon: Download,
              title: "3. Preview & Download",
              desc: "Review every slide online and download an editable PowerPoint file.",
            },
          ].map((item) => (
            <div
              key={item.title}
              className="rounded-xl border border-border/60 bg-card/50 p-5 space-y-2"
            >
              <div className="mx-auto flex size-10 items-center justify-center rounded-lg bg-muted text-indigo-600 dark:text-indigo-400">
                <item.icon className="size-5" />
              </div>
              <h3 className="font-semibold text-sm text-foreground">{item.title}</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
