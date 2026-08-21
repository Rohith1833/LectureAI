import apiClient from "./apiClient";
import type {
  ReviewSummary,
  ResolvedGraphResult,
  NodeDetails,
  ReconciliationInfo,
  AuditHistoryResponse,
  ApprovalReadiness,
  ApprovedSnapshot
} from "../types/review";

export interface StandardResponse<T> {
  success: boolean;
  data: T;
}

export async function getReviewSummary(uploadId: string): Promise<ReviewSummary> {
  const response = await apiClient.get<StandardResponse<ReviewSummary>>(
    `/academic/review/${uploadId}`
  );
  return response.data.data;
}

export interface GetGraphParams {
  limit?: number;
  offset?: number;
  category?: string;
  reviewState?: string;
  lowConfidence?: boolean;
  orphan?: boolean;
}

export async function getAcademicGraph(
  uploadId: string,
  params: GetGraphParams = {}
): Promise<ResolvedGraphResult> {
  const response = await apiClient.get<StandardResponse<ResolvedGraphResult>>(
    `/academic/review/${uploadId}/graph`,
    {
      params: {
        limit: params.limit,
        offset: params.offset,
        category: params.category,
        review_state: params.reviewState,
        low_confidence: params.lowConfidence,
        orphan: params.orphan
      }
    }
  );
  return response.data.data;
}

export async function getAcademicNode(
  uploadId: string,
  nodeId: string
): Promise<NodeDetails> {
  const response = await apiClient.get<StandardResponse<NodeDetails>>(
    `/academic/review/${uploadId}/nodes/${nodeId}`
  );
  return response.data.data;
}

export interface ApplyActionParams {
  action_type: string;
  payload: Record<string, any>;
  expected_version: number;
  comment?: string;
}

export interface ApplyActionResponse {
  success: boolean;
  override_id: string;
  new_version: number;
}

export async function applyReviewAction(
  uploadId: string,
  params: ApplyActionParams
): Promise<ApplyActionResponse> {
  const response = await apiClient.post<StandardResponse<ApplyActionResponse>>(
    `/academic/review/${uploadId}/actions`,
    params
  );
  return response.data.data;
}

export async function getReconciliation(uploadId: string): Promise<ReconciliationInfo> {
  const response = await apiClient.get<StandardResponse<ReconciliationInfo>>(
    `/academic/review/${uploadId}/reconciliation`
  );
  return response.data.data;
}

export async function getAuditHistory(
  uploadId: string,
  limit = 50,
  offset = 0
): Promise<AuditHistoryResponse> {
  const response = await apiClient.get<StandardResponse<AuditHistoryResponse>>(
    `/academic/review/${uploadId}/audit`,
    {
      params: { limit, offset }
    }
  );
  return response.data.data;
}

export async function getApprovalReadiness(uploadId: string): Promise<ApprovalReadiness> {
  const response = await apiClient.get<StandardResponse<ApprovalReadiness>>(
    `/academic/review/${uploadId}/approval-readiness`
  );
  return response.data.data;
}

export async function approveGraph(
  uploadId: string,
  expectedRevision: number
): Promise<{ success: boolean; approval_version: string; approved_revision: number; resolved_graph_fingerprint: string }> {
  const response = await apiClient.post<
    StandardResponse<{ success: boolean; approval_version: string; approved_revision: number; resolved_graph_fingerprint: string }>
  >(`/academic/review/${uploadId}/approve`, {
    expected_revision: expectedRevision
  });
  return response.data.data;
}

export async function getApprovedGraph(
  uploadId: string,
  version?: string
): Promise<ApprovedSnapshot> {
  const response = await apiClient.get<StandardResponse<ApprovedSnapshot>>(
    `/academic/graph/${uploadId}`,
    {
      params: { version }
    }
  );
  return response.data.data;
}
