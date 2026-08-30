import apiClient from "./apiClient";
import type { GenerationRequest, GenerationResult } from "../types/generation";

/**
 * Sends a grounded Q&A query generation request to the backend FastAPI router.
 * Uses a specific timeout of 60 seconds for this generation request to accommodate LLM latency,
 * leaving other API endpoints at their default 10-second timeout.
 */
export async function queryGeneration(request: GenerationRequest): Promise<GenerationResult> {
  const response = await apiClient.post<GenerationResult>(
    "/generation/query",
    request,
    { timeout: 60000 }
  );
  return response.data;
}
