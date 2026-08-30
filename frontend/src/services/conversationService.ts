import apiClient from "./apiClient";
import type {
  Conversation,
  ConversationCreatePayload,
  ConversationMessage,
  ConversationStatus,
  ConversationUpdatePayload,
} from "../types/conversation";

/**
 * Creates a new conversation session for a document.
 */
export async function createConversation(
  documentId: string,
  payload?: ConversationCreatePayload
): Promise<Conversation> {
  const response = await apiClient.post<Conversation>(
    `/documents/${documentId}/conversations`,
    payload || {}
  );
  return response.data;
}

/**
 * Lists all conversations for a specific document.
 */
export async function listConversations(
  documentId: string,
  status?: ConversationStatus
): Promise<Conversation[]> {
  const params: Record<string, string> = {};
  if (status) {
    params.status = status;
  }
  const response = await apiClient.get<Conversation[]>(
    `/documents/${documentId}/conversations`,
    { params }
  );
  return response.data;
}

/**
 * Fetches metadata for a single conversation.
 */
export async function getConversation(conversationId: string): Promise<Conversation> {
  const response = await apiClient.get<Conversation>(`/conversations/${conversationId}`);
  return response.data;
}

/**
 * Updates a conversation's title or status.
 */
export async function updateConversation(
  conversationId: string,
  payload: ConversationUpdatePayload
): Promise<Conversation> {
  const response = await apiClient.patch<Conversation>(
    `/conversations/${conversationId}`,
    payload
  );
  return response.data;
}

/**
 * Archives a conversation session.
 */
export async function archiveConversation(conversationId: string): Promise<Conversation> {
  const response = await apiClient.post<Conversation>(
    `/conversations/${conversationId}/archive`
  );
  return response.data;
}

/**
 * Lists chronologically ordered messages in a conversation.
 */
export async function listConversationMessages(
  conversationId: string,
  limit = 100,
  offset = 0
): Promise<ConversationMessage[]> {
  const response = await apiClient.get<ConversationMessage[]>(
    `/conversations/${conversationId}/messages`,
    { params: { limit, offset } }
  );
  return response.data;
}
