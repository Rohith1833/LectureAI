export const ArtifactType = {
  PPTX: "PPTX",
  DOCX: "DOCX",
  MD: "MD",
  STUDY_GUIDE_MD: "STUDY_GUIDE_MD",
  FLASHCARDS_CSV: "FLASHCARDS_CSV",
  PRACTICE_EXAM_MD: "PRACTICE_EXAM_MD",
} as const;
export type ArtifactType = typeof ArtifactType[keyof typeof ArtifactType];

export const ArtifactStatus = {
  PENDING: "PENDING",
  PLANNING: "PLANNING",
  RENDERING: "RENDERING",
  COMPLETED: "COMPLETED",
  FAILED: "FAILED",
} as const;
export type ArtifactStatus = typeof ArtifactStatus[keyof typeof ArtifactStatus];

export interface SelectableContainerItem {
  id: string;
  title: string;
  entity_type: string;
  source_page_start: number | null;
  source_page_end: number | null;
  topic_count: number;
  stable_id?: string | null;
}

export type ContainerMode = "UNITS" | "CHAPTERS" | "REVIEW_REQUIRED";

export interface SelectableContainersData {
  knowledge_version_id: string;
  document_id?: string | null;
  upload_id: string;
  approval_version?: string | null;
  container_mode: ContainerMode;
  container_type?: string | null;
  containers: SelectableContainerItem[];
  diagnostics: string[];
}

export interface ArtifactJobCreate {
  upload_id: string;
  knowledge_version_id: string;
  artifact_type: ArtifactType;
  config?: {
    selected_unit_ids?: string[];
    num_units?: number;
    audience_level?: string;
    depth?: string;
    include_examples?: boolean;
    include_questions?: boolean;
    [key: string]: any;
  };
}

export interface SlideModel {
  slide_type?: string;
  title: string;
  content: string[];
  speaker_notes?: string;
  source_node_ids?: string[];
  evidence_ids?: string[];
}

export interface ArtifactPlan {
  slides: SlideModel[];
  metadata?: Record<string, any>;
}

export interface ArtifactJobRead {
  id: string;
  upload_id: string;
  knowledge_version_id: string;
  artifact_type: ArtifactType;
  status: ArtifactStatus;
  config: Record<string, any>;
  plan?: ArtifactPlan | Record<string, any> | null;
  artifact_uri?: string | null;
  error_message?: string | null;
  created_at: string | number;
  updated_at?: string | number;
  completed_at?: string | number | null;
}
