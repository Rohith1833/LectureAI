import apiClient from "./apiClient";
import type { PresentationJobStatus } from "@/types/presentation";

export async function startPresentationGeneration(
  uploadId: string,
  targetSlideCount: number | null = null
): Promise<PresentationJobStatus> {
  const response = await apiClient.post<PresentationJobStatus>(
    "/presentations/generate",
    {
      upload_id: uploadId,
      target_slide_count: targetSlideCount,
    }
  );
  return response.data;
}

export async function getPresentationJobStatus(
  jobId: string
): Promise<PresentationJobStatus> {
  const response = await apiClient.get<PresentationJobStatus>(
    `/presentations/${jobId}`
  );
  return response.data;
}

export function getPresentationDownloadUrl(jobId: string): string {
  const base = (import.meta.env.VITE_API_URL || "/api/v1").replace(/\/+$/, "");
  return `${base}/presentations/${jobId}/download`;
}
