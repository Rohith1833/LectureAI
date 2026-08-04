import apiClient from "./apiClient";
import type { HealthResponse } from "@/types/api";

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await apiClient.get<HealthResponse>("/health");
  return response.data;
}
