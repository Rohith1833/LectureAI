import apiClient from "./apiClient";
import type { StandardResponse } from "./reviewService";
import type {
  KnowledgeVersion,
  KnowledgeEntity,
  KnowledgeEvidence,
  EntityRelationshipsData,
  PaginatedResult
} from "../types/knowledge";

export async function getLatestFinalizedVersion(documentId: string): Promise<KnowledgeVersion> {
  const response = await apiClient.get<StandardResponse<KnowledgeVersion>>(
    `/knowledge/document/${documentId}`
  );
  return response.data.data;
}

export async function listFinalizedVersions(documentId: string): Promise<KnowledgeVersion[]> {
  const response = await apiClient.get<StandardResponse<KnowledgeVersion[]>>(
    `/knowledge/document/${documentId}/versions`
  );
  return response.data.data;
}

export async function getFinalizedVersion(versionId: string): Promise<KnowledgeVersion> {
  const response = await apiClient.get<StandardResponse<KnowledgeVersion>>(
    `/knowledge/versions/${versionId}`
  );
  return response.data.data;
}

export interface ListEntitiesParams {
  entity_type?: string;
  stable_id?: string;
  limit?: number;
  offset?: number;
}

export async function listEntities(
  versionId: string,
  params: ListEntitiesParams = {}
): Promise<PaginatedResult<KnowledgeEntity>> {
  const response = await apiClient.get<StandardResponse<PaginatedResult<KnowledgeEntity>>>(
    `/knowledge/versions/${versionId}/entities`,
    { params }
  );
  return response.data.data;
}

export async function getEntity(versionId: string, entityId: string): Promise<KnowledgeEntity> {
  const response = await apiClient.get<StandardResponse<KnowledgeEntity>>(
    `/knowledge/versions/${versionId}/entities/${entityId}`
  );
  return response.data.data;
}

export async function getEntityEvidence(
  versionId: string,
  entityId: string
): Promise<KnowledgeEvidence[]> {
  const response = await apiClient.get<StandardResponse<KnowledgeEvidence[]>>(
    `/knowledge/versions/${versionId}/entities/${entityId}/evidence`
  );
  return response.data.data;
}

export async function getEntityRelationships(
  versionId: string,
  entityId: string
): Promise<EntityRelationshipsData> {
  const response = await apiClient.get<StandardResponse<EntityRelationshipsData>>(
    `/knowledge/versions/${versionId}/entities/${entityId}/relationships`
  );
  return response.data.data;
}
