import apiClient from "./apiClient";
import type { ArtifactJobCreate, ArtifactJobRead } from "@/types/artifact";

export const artifactService = {
  async generateArtifact(request: ArtifactJobCreate): Promise<ArtifactJobRead> {
    const response = await apiClient.post<ArtifactJobRead>("/artifacts/generate", request);
    return response.data;
  },

  async getJobStatus(jobId: string): Promise<ArtifactJobRead> {
    const response = await apiClient.get<ArtifactJobRead>(`/artifacts/${jobId}`);
    return response.data;
  },

  async listJobs(uploadId: string): Promise<ArtifactJobRead[]> {
    const response = await apiClient.get<ArtifactJobRead[]>(`/artifacts/jobs/${uploadId}`);
    return response.data;
  },

  getDownloadUrl(jobId: string): string {
    const base = apiClient.defaults.baseURL || import.meta.env.VITE_API_URL || "/api/v1";
    const cleanBase = String(base).replace(/\/+$/, "");
    return `${cleanBase}/artifacts/${jobId}/download`;
  },
};
