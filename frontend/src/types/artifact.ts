export const ArtifactType = {
  PPTX: "PPTX",
  DOCX: "DOCX",
  MD: "MD",
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

export interface ArtifactJobCreate {
  upload_id: string;
  knowledge_version_id: string;
  artifact_type: ArtifactType;
  config?: Record<string, any>;
}

export interface ArtifactJobRead {
  id: string;
  upload_id: string;
  knowledge_version_id: string;
  artifact_type: ArtifactType;
  status: ArtifactStatus;
  config: Record<string, any>;
  artifact_uri?: string;
  error_message?: string;
  created_at: number;
  completed_at?: number;
}
