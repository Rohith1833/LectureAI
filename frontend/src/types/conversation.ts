export type ConversationStatus = "ACTIVE" | "ARCHIVED";

export type MessageRole = "USER" | "ASSISTANT";

export interface Conversation {
  id: string;
  document_id: string;
  knowledge_version_id?: string | null;
  title: string;
  status: ConversationStatus;
  created_at: number;
  updated_at: number;
  message_count: number;
}

export interface ConversationMessage {
  id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  sequence: number;
  created_at: number;
  metadata_json?: Record<string, unknown> | null;
}

export interface ConversationCreatePayload {
  knowledge_version_id?: string | null;
  title?: string | null;
}

export interface ConversationUpdatePayload {
  title?: string | null;
  status?: ConversationStatus | null;
}
