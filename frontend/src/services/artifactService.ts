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
    return `${import.meta.env.VITE_API_URL}/artifacts/${jobId}/download`;
  },
};
