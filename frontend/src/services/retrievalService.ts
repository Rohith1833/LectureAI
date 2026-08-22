import apiClient from "./apiClient";
import type { RetrievalRequest, RetrievalResult } from "../types/retrieval";

/**
 * Sends a retrieval query request to the backend FastAPI API router.
 */
export async function queryRetrieval(request: RetrievalRequest): Promise<RetrievalResult> {
  const response = await apiClient.post<RetrievalResult>(
    "/retrieval/query",
    request
  );
  return response.data;
}
