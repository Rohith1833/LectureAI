import apiClient from "./apiClient";

export interface PipelineStep {
  agent: string;
  status: string;
}

export interface JobData {
  job_id: string;
  upload_id: string;
  status: "uploaded" | "queued" | "processing" | "completed" | "failed" | "cancelled";
  progress: number;
  current_stage: string;
  created_at: string;
  updated_at: string;
  pipeline: PipelineStep[];
  error: string | null;
  document_id?: string | null;
}

export interface JobCreateResponse {
  success: boolean;
  message: string;
  data: {
    job_id: string;
    status: string;
  };
}

export interface JobStatusResponse {
  success: boolean;
  data: JobData;
}

/**
 * Creates a background slide compilation job for the given upload ID.
 */
export async function createJob(uploadId: string): Promise<JobCreateResponse> {
  const response = await apiClient.post<JobCreateResponse>("/jobs", {
    upload_id: uploadId,
  });
  return response.data;
}

/**
 * Fetches the current processing progress and stage of a job by ID.
 */
export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const response = await apiClient.get<JobStatusResponse>(`/jobs/${jobId}`);
  return response.data;
}
