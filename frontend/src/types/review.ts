export type NodeReviewState = "UNREVIEWED" | "ACCEPTED" | "MODIFIED" | "REJECTED";

export interface ReviewSummary {
  upload_id: string;
  document_id?: string;
  document_review_state: "NEEDS_REVIEW" | "APPROVED";
  base_graph_fingerprint: string;
  resolved_graph_fingerprint: string;
  reconciliation_status: "CLEAN" | "NEEDS_REVIEW" | "STALE_OVERRIDES" | "CONFLICTS" | "INVALID_GRAPH";
  total_nodes: number;
  unreviewed_count: number;
  accepted_count: number;
  modified_count: number;
  rejected_count: number;
  stale_overrides_count: number;
  conflicted_overrides_count: number;
  approval_readiness: boolean;
  warnings: string[];
  errors: string[];
  resolved_graph_version: number;
  pipeline_run_id: string;
  approval_history?: ApprovedSnapshotInfo[];
}

export interface ApprovedSnapshotInfo {
  approval_version: string;
  approved_revision: number;
  pipeline_run_id: string;
  approval_timestamp: number;
  reviewer_id: string;
  resolved_graph_fingerprint: string;
}

export interface AcademicNode {
  node_id: string;
  category: string;
  title: string;
  target_block_id: string | null;
  anchor_key: string | null;
  review_state: NodeReviewState;
  metadata: Record<string, any>;
}

export interface AcademicEdge {
  source_node_id: string;
  target_node_id: string;
  edge_type: string;
  confidence: number;
  metadata: Record<string, any>;
}

export interface ResolvedGraphResult {
  nodes: AcademicNode[];
  edges: AcademicEdge[];
  total_count: number;
  resolved_graph_version: number;
}

export interface NodeOriginalValues {
  category: string;
  title: string;
  parent_id: string | null;
}

export interface AuditHistoryEntry {
  audit_id: string;
  user_id: string;
  action_type: string;
  node_id: string;
  previous_state: Record<string, any>;
  new_state: Record<string, any>;
  comment: string | null;
  timestamp: number;
}

export interface NodeDetails {
  node_id: string;
  category: string;
  title: string;
  review_state: NodeReviewState;
  confidence: number;
  provenance: string;
  anchor_key: string | null;
  target_block_id: string | null;
  original_values: NodeOriginalValues;
  parent_id: string | null;
  child_ids: string[];
  override_ids: string[];
  audit_history: AuditHistoryEntry[];
}

export interface StaleOverride {
  override_id: string;
  anchor_key: string;
  action_type: string;
  payload: Record<string, any>;
  reason: string;
}

export interface ConflictedOverride {
  override_id: string;
  anchor_key: string;
  action_type: string;
  payload: Record<string, any>;
  reason: string;
}

export interface ReconciliationInfo {
  upload_id: string;
  reconciliation_status: string;
  stale_overrides: StaleOverride[];
  conflicted_overrides: ConflictedOverride[];
  validation_errors: string[];
  validation_warnings: string[];
}

export interface AuditHistoryResponse {
  audits: AuditHistoryEntry[];
  total_count: number;
}

export interface ApprovalCheck {
  code: string;
  passed: boolean;
  severity: "BLOCKER" | "WARNING" | "INFO";
  message: string;
}

export interface ApprovalReadiness {
  eligible: boolean;
  checks: ApprovalCheck[];
  blocking_reasons: string[];
  warnings: string[];
  current_revision: number;
  resolved_graph_fingerprint: string;
}

export interface ApprovedSnapshot {
  upload_id: string;
  approval_version: string;
  pipeline_run_id: string;
  approval_timestamp: number;
  reviewer_id: string;
  resolved_graph_fingerprint: string;
  schema_version: string;
  nodes: any[];
  edges: any[];
}
