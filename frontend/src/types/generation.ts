import type { RetrievalScope, RetrievalOptions, PassageSchema } from "./retrieval";

export type GroundingStatus =
  | "SUPPORTED"
  | "PARTIALLY_SUPPORTED"
  | "UNSUPPORTED"
  | "INSUFFICIENT_CONTEXT";

export type GenerationMode = "QA" | "EXPLANATION" | "SUMMARY" | "COMPARISON" | "STUDY_GUIDE";

export interface GenerationOptions {
  temperature: number;
  output_format: string;
}

export interface ComparisonOptions {
  subjects: string[];
  dimensions?: string[] | null;
}

export interface StudyGuideOptions {
  question_count?: number | null;
  difficulty?: "basic" | "intermediate" | "advanced" | null;
}

export interface GenerationRequest {
  query: string;
  scope: RetrievalScope;
  mode?: GenerationMode;
  retrieval_options: RetrievalOptions;
  generation_options: GenerationOptions;
  comparison_options?: ComparisonOptions | null;
  study_options?: StudyGuideOptions | null;
  conversation_id?: string | null;
  conversation_context?: Array<{ role: string; content: string }> | null;
}

export interface ContextSource {
  citation_id: string;
  entity_id: string;
  title: string;
  entity_type: string;
  content: string;
  passage: PassageSchema | null;
  provenance: string | null;
}

export interface Citation {
  citation_id: string;
}

export interface GenerationClaim {
  claim_id: string;
  text: string;
  citation_ids: string[];
  grounding_status: GroundingStatus;
}

export interface ComparisonValue {
  subject: string;
  value: string;
  citation_ids?: string[];
}

export interface ComparisonRow {
  dimension: string;
  values: ComparisonValue[];
  explanation?: string | null;
}

export interface ComparisonSimilarity {
  text: string;
  citation_ids?: string[];
}

export interface ComparisonDifference {
  text: string;
  citation_ids?: string[];
}

export interface StructuredComparisonOutput {
  title?: string;
  subjects?: string[];
  comparison_table?: ComparisonRow[];
  similarities?: ComparisonSimilarity[];
  differences?: ComparisonDifference[];
}

export interface StudyGuideKeyConcept {
  concept: string;
  definition: string;
  citation_ids?: string[];
}

export interface StudyGuideReviewQuestion {
  question: string;
  answer: string;
  explanation: string;
  citation_ids?: string[];
}

export interface StructuredStudyGuideOutput {
  title?: string;
  answer?: string;
  key_concepts?: StudyGuideKeyConcept[];
  learning_objectives?: string[];
  review_questions?: StudyGuideReviewQuestion[];
  claims?: GenerationClaim[];
}

export interface GenerationResult {
  mode: GenerationMode;
  answer: string;
  structured_output?: Record<string, any> | StructuredComparisonOutput | StructuredStudyGuideOutput | null;
  claims: GenerationClaim[];
  citations: Record<string, ContextSource>;
  overall_grounding_status: GroundingStatus;
  model_metadata: Record<string, any> | null;
}
