import { createContext, useContext, useState } from "react";
import { type UploadResponseData } from "@/services/uploadService";

interface UploadContextType {
  selectedFile: File | null;
  uploadMetadata: UploadResponseData | null;
  uploadStatus: "idle" | "uploading" | "success" | "error";
  uploadProgress: number;
  jobId: string | null;
  setSelectedFile: (file: File | null) => void;
  setUploadMetadata: (metadata: UploadResponseData | null) => void;
  setUploadStatus: (status: "idle" | "uploading" | "success" | "error") => void;
  setUploadProgress: (progress: number) => void;
  setJobId: (jobId: string | null) => void;
  resetUploadState: () => void;
}

const UploadContext = createContext<UploadContextType | undefined>(undefined);

export function UploadProvider({ children }: { children: React.ReactNode }) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadMetadata, setUploadMetadata] = useState<UploadResponseData | null>(null);
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [jobId, setJobId] = useState<string | null>(null);

  const resetUploadState = () => {
    setSelectedFile(null);
    setUploadMetadata(null);
    setUploadStatus("idle");
    setUploadProgress(0);
    setJobId(null);
  };

  return (
    <UploadContext.Provider
      value={{
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
      }}
    >
      {children}
    </UploadContext.Provider>
  );
}

export function useUpload() {
  const context = useContext(UploadContext);
  if (!context) {
    throw new Error("useUpload must be used within an UploadProvider");
  }
  return context;
}
