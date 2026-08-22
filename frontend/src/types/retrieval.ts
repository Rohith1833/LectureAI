import type { KnowledgeEntity, KnowledgeRelationship, KnowledgeEvidence } from "./knowledge";

export interface RetrievalScope {
  document_id: string;
  version_id: string | null;
  entity_types: string[] | null;
  relationship_types: string[] | null;
}

export interface RetrievalOptions {
  top_k: number;
  include_relationships: boolean;
  include_evidence: boolean;
  include_passages: boolean;
  relationship_depth: number;
  strategy: string;
}

export interface RetrievalRequest {
  query: string;
  scope: RetrievalScope;
  options: RetrievalOptions;
}

export interface PassageSchema {
  block_id: string;
  page_number: number;
  text: string;
  block_type: string;
  section_title: string | null;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface RetrievedEntity {
  entity: KnowledgeEntity;
  score: number;
  match_reason: string;
  outgoing_relationships: KnowledgeRelationship[];
  incoming_relationships: KnowledgeRelationship[];
  evidence: KnowledgeEvidence[];
  passages: PassageSchema[];
}

export interface RetrievalProvenance {
  knowledge_version_id: string;
  approval_version: number;
  document_id: string;
  strategy_used: string;
  query_terms: string[];
  total_candidates_considered: number;
}

export interface RetrievalResult {
  query: string;
  scope: RetrievalScope;
  provenance: RetrievalProvenance;
  entities: RetrievedEntity[];
  total_entity_count: number;
  has_more: boolean;
}
