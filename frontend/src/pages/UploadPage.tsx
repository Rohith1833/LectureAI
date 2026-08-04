import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { FileDropzone } from "@/components/ui/form";
import { InfoCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SuccessAlert } from "@/components/ui/feedback";
import { HelpCircle, Trash2, ArrowRight, FileText, Sparkles, AlertCircle, Loader2 } from "lucide-react";
import { useUpload } from "@/contexts/uploadContext";
import { uploadTextbookFile } from "@/services/uploadService";
import { createJob } from "@/services/jobService";

export default function UploadPage() {
  const navigate = useNavigate();
  const {
    selectedFile,
    uploadMetadata,
    uploadStatus,
    uploadProgress,
    jobId,
    setSelectedFile,
    setUploadMetadata,
    setUploadStatus,
    setUploadProgress,
    setJobId,
    resetUploadState,
  } = useUpload();

  const [validationError, setValidationError] = useState<string | null>(null);

  const handleFileSelect = (file: File) => {
    setValidationError(null);
    
    // Validate File Extension & Type
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setValidationError("Only PDF files are allowed.");
      return;
    }
    
    // Validate File Size (100 MB max)
    if (file.size > 100 * 1024 * 1024) {
      setValidationError("File exceeds maximum allowed size of 100 MB.");
      return;
    }
    
    // Validate Empty File
    if (file.size === 0) {
      setValidationError("The uploaded file is empty.");
      return;
    }

    setSelectedFile(file);
    setUploadStatus("idle");
  };

  const createJobMutation = useMutation({
    mutationFn: (uploadId: string) => createJob(uploadId),
    onSuccess: (response) => {
      setJobId(response.data.job_id);
    },
    onError: (err: any) => {
      setUploadStatus("error");
      const errMsg = err?.response?.data?.detail || "Failed to initialize processing job.";
      setValidationError(errMsg);
    },
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) =>
      uploadTextbookFile(file, (progress) => {
        setUploadProgress(progress);
      }),
    onMutate: () => {
      setUploadStatus("uploading");
      setValidationError(null);
    },
    onSuccess: (response) => {
      setUploadStatus("success");
      setUploadMetadata(response.data);
      // Automatically trigger job initialization
      createJobMutation.mutate(response.data.upload_id);
    },
    onError: (err: any) => {
      setUploadStatus("error");
      const errMsg = err?.response?.data?.detail || "Upload failed. Please check your network and try again.";
      setValidationError(errMsg);
    },
  });

  const handleProceed = () => {
    if (jobId) {
      navigate(`/processing/${jobId}`);
    }
  };

  const handleStartUpload = () => {
    if (selectedFile) {
      uploadMutation.mutate(selectedFile);
    }
  };

  const handleRemoveFile = () => {
    resetUploadState();
    setValidationError(null);
  };

  const isInitializingJob = createJobMutation.isPending;

  return (
    <div className="space-y-8 py-6">
      {/* Page Header */}
      <div className="space-y-1.5">
        <h1 className="text-3xl font-bold tracking-tight">Upload Textbook</h1>
        <p className="text-sm text-muted-foreground">
          Import your textbook PDF to validate and securely cache it for presentation compiler agents.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Main Dropzone / File status */}
        <div className="lg:col-span-2 space-y-6">
          {validationError && uploadStatus !== "uploading" && (
            <div className="flex gap-2 p-3 border border-red-500/20 bg-red-500/5 text-red-700 dark:text-red-400 rounded-xl text-sm items-start">
              <AlertCircle className="size-4.5 shrink-0 mt-0.5" />
              <span>{validationError}</span>
            </div>
          )}

          {uploadStatus === "idle" && !selectedFile && (
            <FileDropzone onFileSelect={handleFileSelect} className="h-80" />
          )}

          {/* Selected File Details */}
          {selectedFile && uploadStatus !== "success" && (
            <InfoCard
              title={uploadStatus === "uploading" ? "Uploading Document..." : "Selected Document"}
              description={
                uploadStatus === "uploading"
                  ? "Transmitting byte stream to server"
                  : "Review file details before uploading"
              }
              action={
                uploadStatus !== "uploading" && (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={handleRemoveFile}
                    className="text-destructive hover:bg-destructive/10"
                    aria-label="Remove selected file"
                  >
                    <Trash2 className="size-4" />
                  </Button>
                )
              }
              className={`${
                uploadStatus === "error" ? "border-red-500/30 bg-red-500/5" : "border-violet-500/30"
              }`}
            >
              <div className="flex items-center gap-4 py-4">
                <div className="flex size-12 items-center justify-center rounded-xl bg-violet-500/10 text-violet-600 dark:bg-violet-500/20 dark:text-violet-400">
                  <FileText className="size-6" />
                </div>
                <div className="flex-1 min-w-0">
                  <h4 className="font-semibold text-base truncate">{selectedFile.name}</h4>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • PDF Document
                  </p>
                </div>
              </div>

              {/* Progress bar */}
              {uploadStatus === "uploading" && (
                <div className="space-y-2 py-2">
                  <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full transition-all duration-150 ease-out"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Uploading...</span>
                    <span>{uploadProgress}%</span>
                  </div>
                </div>
              )}

              {/* Action Buttons */}
              {uploadStatus !== "uploading" && (
                <div className="flex justify-end gap-3 pt-4 border-t border-border/40">
                  <Button variant="outline" onClick={handleRemoveFile}>
                    Clear
                  </Button>
                  <Button
                    onClick={handleStartUpload}
                    className="gap-2 bg-violet-600 hover:bg-violet-700 text-white dark:bg-violet-500 dark:hover:bg-violet-600 font-semibold"
                  >
                    {uploadStatus === "error" ? "Retry Upload" : "Upload File"}{" "}
                    <ArrowRight className="size-4" />
                  </Button>
                </div>
              )}
            </InfoCard>
          )}

          {/* Upload Success View */}
          {uploadStatus === "success" && uploadMetadata && (
            <InfoCard title="Upload Successful" className="border-emerald-500/30 bg-emerald-500/5 dark:bg-emerald-950/5 animate-in fade-in zoom-in-95 duration-200">
              <SuccessAlert
                title="File Cached Successfully"
                message={
                  isInitializingJob
                    ? "Initializing processing job..."
                    : "Textbook metadata generated and background job queued."
                }
              />

              <div className="mt-4 p-4 rounded-xl border border-emerald-500/10 bg-emerald-500/5 dark:bg-emerald-950/10 space-y-2 text-xs leading-normal">
                <div className="flex justify-between border-b border-border/20 pb-2">
                  <span className="text-muted-foreground">Upload ID:</span>
                  <span className="font-semibold select-all">{uploadMetadata.upload_id}</span>
                </div>
                {jobId && (
                  <div className="flex justify-between border-b border-border/20 pb-2">
                    <span className="text-muted-foreground">Job ID:</span>
                    <span className="font-semibold select-all text-violet-600 dark:text-violet-400">{jobId}</span>
                  </div>
                )}
                <div className="flex justify-between border-b border-border/20 pb-2">
                  <span className="text-muted-foreground">Original Name:</span>
                  <span className="font-semibold truncate max-w-[200px]">{uploadMetadata.original_filename}</span>
                </div>
                <div className="flex justify-between border-b border-border/20 pb-2">
                  <span className="text-muted-foreground">Stored Name:</span>
                  <span className="font-semibold truncate max-w-[200px]">{uploadMetadata.stored_filename}</span>
                </div>
                <div className="flex justify-between border-b border-border/20 pb-2">
                  <span className="text-muted-foreground">File Size:</span>
                  <span className="font-semibold">{(uploadMetadata.size_bytes / (1024 * 1024)).toFixed(2)} MB</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Timestamp:</span>
                  <span className="font-semibold">{new Date(uploadMetadata.uploaded_at).toLocaleString()}</span>
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-6 border-t border-border/40 mt-6">
                <Button variant="outline" onClick={handleRemoveFile} disabled={isInitializingJob}>
                  Upload Another
                </Button>
                <Button
                  onClick={handleProceed}
                  disabled={!jobId || isInitializingJob}
                  className="gap-2 bg-violet-600 hover:bg-violet-700 text-white dark:bg-violet-500 dark:hover:bg-violet-600 font-semibold"
                >
                  {isInitializingJob ? (
                    <>
                      <Loader2 className="size-4 animate-spin" /> Initializing...
                    </>
                  ) : (
                    <>
                      Continue to Processing <ArrowRight className="size-4" />
                    </>
                  )}
                </Button>
              </div>
            </InfoCard>
          )}

          {/* Formats Grid */}
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="rounded-xl border border-border bg-card p-4 flex flex-col justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">PDF Document</span>
              <span className="text-2xl font-bold text-violet-600 dark:text-violet-400 mt-2">Active</span>
              <span className="text-[10px] text-muted-foreground mt-1">Full support for layout analysis & OCR</span>
            </div>
            <div className="rounded-xl border border-dashed border-border/60 bg-muted/20 p-4 flex flex-col justify-between opacity-50 select-none">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Word (DOCX)</span>
              <span className="text-sm font-semibold text-muted-foreground mt-2">Future Support</span>
              <span className="text-[10px] text-muted-foreground mt-1">Importing outline documents</span>
            </div>
            <div className="rounded-xl border border-dashed border-border/60 bg-muted/20 p-4 flex flex-col justify-between opacity-50 select-none">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Text (TXT)</span>
              <span className="text-sm font-semibold text-muted-foreground mt-2">Future Support</span>
              <span className="text-[10px] text-muted-foreground mt-1">Direct syllabus mapping</span>
            </div>
          </div>
        </div>

        {/* Sidebar Info/Tips */}
        <div className="space-y-6">
          <InfoCard title="Processing Tips">
            <div className="space-y-4 text-sm leading-relaxed text-muted-foreground">
              <div className="flex gap-2">
                <HelpCircle className="size-4 text-violet-600 shrink-0 mt-0.5" />
                <p>
                  <strong>High Quality PDFs:</strong> Textbooks with digital text rather than scanned images process significantly faster.
                </p>
              </div>
              <div className="flex gap-2">
                <HelpCircle className="size-4 text-violet-600 shrink-0 mt-0.5" />
                <p>
                  <strong>Table of Contents:</strong> Our AI will extract the index automatically to help you select unit chapters.
                </p>
              </div>
              <div className="flex gap-2">
                <Sparkles className="size-4 text-violet-600 shrink-0 mt-0.5" />
                <p>
                  <strong>Clean Structures:</strong> Presentations will follow the exact order of learning modules detected.
                </p>
              </div>
            </div>
          </InfoCard>

          <InfoCard title="File Requirements">
            <ul className="space-y-2.5 text-xs text-muted-foreground list-disc pl-4">
              <li>Maximum file size: 100 megabytes (MB)</li>
              <li>Only <code>.pdf</code> format supported in this release</li>
              <li>Signature verification will validate the PDF format magic bytes</li>
            </ul>
          </InfoCard>
        </div>
      </div>
    </div>
  );
}
