export interface KnowledgeVersion {
  id: string;
  document_id: string;
  upload_id: string;
  snapshot_id: string;
  schema_version: string;
  created_at: number;
  status: "BUILDING" | "FINALIZED";
  metadata?: Record<string, unknown> | null;
  entity_count: number;
  relationship_count: number;
  evidence_count: number;
  approval_version: number;
}

export interface KnowledgeEntity {
  id: string;
  knowledge_version_id: string;
  entity_type: string;
  title: string;
  content: string;
  stable_id: string;
  metadata?: Record<string, unknown> | null;
}

export interface KnowledgeRelationship {
  id: string;
  knowledge_version_id: string;
  source_entity_id: string;
  target_entity_id: string;
  relationship_type: string;
  confidence: number;
  is_inferred: boolean;
  is_human_confirmed: boolean;
  metadata?: Record<string, unknown> | null;
}

export interface KnowledgeEvidence {
  id: string;
  entity_id: string;
  document_id: string;
  page_number: number | null;
  section_title: string | null;
  source_node_id: string | null;
  source_anchor_key: string | null;
  text_reference: string | null;
  provenance: string;
  x0: number | null;
  y0: number | null;
  x1: number | null;
  y1: number | null;
  metadata?: Record<string, unknown> | null;
}

export interface EntityRelationshipsData {
  incoming: KnowledgeRelationship[];
  outgoing: KnowledgeRelationship[];
}

export interface PaginatedResult<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}
