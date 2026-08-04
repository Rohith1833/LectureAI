import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "@/services/healthService";

export function useHealthCheck(enabled: boolean) {
  return useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    enabled,
    retry: 1,
    staleTime: 30000,
  });
}
