from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.repositories.knowledge_repository import KnowledgeRepository
from app.models.document import Document
from app.models.review import AcademicGraphSnapshot
from app.schemas.knowledge import (
    KnowledgeVersionSchema,
    KnowledgeEntitySchema,
    KnowledgeRelationshipSchema,
    KnowledgeEvidenceSchema
)

router = APIRouter(prefix="/knowledge")


# Public Metadata schema for KnowledgeVersion
class KnowledgeVersionMetadataSchema(BaseModel):
    id: str
    document_id: Optional[str] = None
    upload_id: str
    snapshot_id: str
    schema_version: str = "1.0.0"
    created_at: float
    status: str
    metadata: Optional[Dict[str, Any]] = None
    entity_count: int = 0
    relationship_count: int = 0
    evidence_count: int = 0
    approval_version: int = 1

    model_config = {
        "populate_by_name": True,
        "from_attributes": True
    }


# Response Envelope Schemas
class VersionResponse(BaseModel):
    success: bool = True
    data: KnowledgeVersionMetadataSchema


class VersionListResponse(BaseModel):
    success: bool = True
    data: List[KnowledgeVersionMetadataSchema]


class EntityResponse(BaseModel):
    success: bool = True
    data: KnowledgeEntitySchema


class EntityListResponseData(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[KnowledgeEntitySchema]


class EntityListResponse(BaseModel):
    success: bool = True
    data: EntityListResponseData


class RelationshipListResponseData(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[KnowledgeRelationshipSchema]


class RelationshipListResponse(BaseModel):
    success: bool = True
    data: RelationshipListResponseData


class EntityRelationshipsResponseData(BaseModel):
    incoming: List[KnowledgeRelationshipSchema]
    outgoing: List[KnowledgeRelationshipSchema]


class EntityRelationshipsResponse(BaseModel):
    success: bool = True
    data: EntityRelationshipsResponseData


class EvidenceListResponse(BaseModel):
    success: bool = True
    data: List[KnowledgeEvidenceSchema]


# Helper function to map a KnowledgeVersion model + database query to metadata schema
def build_version_metadata(version: Any, repo: KnowledgeRepository) -> KnowledgeVersionMetadataSchema:
    doc = repo.db.query(Document).filter(Document.upload_id == version.upload_id).first()
    doc_id = doc.id if doc else None
    counts = repo.get_version_counts(version.id)
    
    # Map metadata from metadata_json on ORM model
    meta = version.metadata_json

    snapshot = repo.db.query(AcademicGraphSnapshot).filter(AcademicGraphSnapshot.id == version.snapshot_id).first()
    approval_version = snapshot.approval_version if snapshot else 1

    return KnowledgeVersionMetadataSchema(
        id=version.id,
        document_id=doc_id,
        upload_id=version.upload_id,
        snapshot_id=version.snapshot_id,
        schema_version=version.schema_version,
        created_at=version.created_at,
        status=version.status,
        metadata=meta,
        entity_count=counts["entity_count"],
        relationship_count=counts["relationship_count"],
        evidence_count=counts["evidence_count"],
        approval_version=approval_version
    )


@router.get("/document/{document_id}", response_model=VersionResponse)
def get_latest_finalized_version(document_id: str, db: Session = Depends(get_db)):
    """Fetch metadata of the latest finalized version for the given document ID."""
    repo = KnowledgeRepository(db)
    version = repo.get_latest_finalized_version(document_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No finalized knowledge version found for document ID '{document_id}'"
        )
    return {"success": True, "data": build_version_metadata(version, repo)}


@router.get("/document/{document_id}/versions", response_model=VersionListResponse)
def list_finalized_versions(document_id: str, db: Session = Depends(get_db)):
    """List all finalized knowledge versions for the given document ID."""
    repo = KnowledgeRepository(db)
    versions = repo.list_finalized_versions(document_id)
    meta_list = [build_version_metadata(v, repo) for v in versions]
    return {"success": True, "data": meta_list}


@router.get("/versions/{version_id}", response_model=VersionResponse)
def get_finalized_version(version_id: str, db: Session = Depends(get_db)):
    """Fetch metadata of a specific finalized version."""
    repo = KnowledgeRepository(db)
    version = repo.get_finalized_version(version_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finalized knowledge version '{version_id}' not found."
        )
    return {"success": True, "data": build_version_metadata(version, repo)}


@router.get("/versions/{version_id}/entities", response_model=EntityListResponse)
def list_entities(
    version_id: str,
    entity_type: Optional[str] = Query(None, description="Filter by entity type (e.g. CONCEPT, DEFINITION)"),
    stable_id: Optional[str] = Query(None, description="Filter by stable semantic ID"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """List paginated entities within a specific finalized knowledge version."""
    repo = KnowledgeRepository(db)
    version = repo.get_finalized_version(version_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finalized knowledge version '{version_id}' not found."
        )

    total = repo.count_entities(version_id, entity_type, stable_id)
    items = repo.list_entities(version_id, entity_type, stable_id, limit, offset)
    return {
        "success": True,
        "data": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": items
        }
    }


@router.get("/versions/{version_id}/entities/{entity_id}", response_model=EntityResponse)
def get_entity(version_id: str, entity_id: str, db: Session = Depends(get_db)):
    """Retrieve details of a single finalized entity by its ID."""
    repo = KnowledgeRepository(db)
    version = repo.get_finalized_version(version_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finalized knowledge version '{version_id}' not found."
        )

    entity = repo.get_entity(version_id, entity_id)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity '{entity_id}' not found in version '{version_id}'."
        )
    return {"success": True, "data": entity}


@router.get("/versions/{version_id}/entities/{entity_id}/evidence", response_model=EvidenceListResponse)
def list_evidence_for_entity(version_id: str, entity_id: str, db: Session = Depends(get_db)):
    """Retrieve all evidence coordinates and references linked to a specific entity."""
    repo = KnowledgeRepository(db)
    version = repo.get_finalized_version(version_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finalized knowledge version '{version_id}' not found."
        )

    entity = repo.get_entity(version_id, entity_id)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity '{entity_id}' not found in version '{version_id}'."
        )

    evidence = repo.list_evidence_by_entity(entity_id)
    return {"success": True, "data": evidence}


@router.get("/versions/{version_id}/relationships", response_model=RelationshipListResponse)
def list_relationships(
    version_id: str,
    source_entity_id: Optional[str] = Query(None, description="Filter by source entity ID"),
    target_entity_id: Optional[str] = Query(None, description="Filter by target entity ID"),
    relationship_type: Optional[str] = Query(None, description="Filter by relationship type (e.g. CONTAINS, PREREQUISITE_OF)"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """List paginated relationships within a specific finalized knowledge version."""
    repo = KnowledgeRepository(db)
    version = repo.get_finalized_version(version_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finalized knowledge version '{version_id}' not found."
        )

    total = repo.count_relationships(version_id, source_entity_id, target_entity_id, relationship_type)
    items = repo.list_relationships(version_id, source_entity_id, target_entity_id, relationship_type, limit, offset)
    return {
        "success": True,
        "data": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": items
        }
    }


@router.get("/versions/{version_id}/entities/{entity_id}/relationships", response_model=EntityRelationshipsResponse)
def get_entity_relationships(version_id: str, entity_id: str, db: Session = Depends(get_db)):
    """Retrieve incoming and outgoing relationships for a specific entity separately."""
    repo = KnowledgeRepository(db)
    version = repo.get_finalized_version(version_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finalized knowledge version '{version_id}' not found."
        )

    entity = repo.get_entity(version_id, entity_id)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity '{entity_id}' not found in version '{version_id}'."
        )

    rels = repo.get_entity_relationships(version_id, entity_id)
    return {
        "success": True,
        "data": {
            "incoming": rels["incoming"],
            "outgoing": rels["outgoing"]
        }
    }
