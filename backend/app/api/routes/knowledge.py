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


class SelectableContainerItem(BaseModel):
    id: str
    title: str
    entity_type: str
    source_page_start: Optional[int] = None
    source_page_end: Optional[int] = None
    topic_count: int = 0
    stable_id: Optional[str] = None


class SelectableContainersResponseData(BaseModel):
    knowledge_version_id: str
    document_id: Optional[str] = None
    upload_id: str
    approval_version: Optional[str] = None
    container_mode: str
    container_type: Optional[str] = None
    containers: List[SelectableContainerItem]
    diagnostics: List[str]


class SelectableContainersResponse(BaseModel):
    success: bool = True
    data: SelectableContainersResponseData


def resolve_selectable_containers_for_version(version: Any, db: Session) -> Dict[str, Any]:
    from app.services.intelligence.knowledge_ordering import (
        get_selectable_containers,
        get_container_descendants,
        SelectableContainerMode
    )
    from app.models.knowledge import KnowledgeEntity, KnowledgeRelationship, KnowledgeEvidence

    result = get_selectable_containers(db, version.id)

    doc = db.query(Document).filter(Document.upload_id == version.upload_id).first()
    doc_id = doc.id if doc else None

    snapshot = db.query(AcademicGraphSnapshot).filter(AcademicGraphSnapshot.id == version.snapshot_id).first()
    approval_version = snapshot.approval_version if snapshot else 1

    diagnostics = [result.message] if result.message else []
    if result.mode == SelectableContainerMode.CHAPTERS:
        diagnostics.append("Chapters mode: No syllabus units detected in this textbook. Selection is by chapter.")

    relationships = (
        db.query(KnowledgeRelationship)
        .filter(KnowledgeRelationship.knowledge_version_id == version.id)
        .all()
    )

    containers_data = []
    for c in result.containers:
        descendant_ids = get_container_descendants(c.id, relationships)
        all_ids = {c.id} | descendant_ids

        topic_count = (
            db.query(KnowledgeEntity)
            .filter(
                KnowledgeEntity.knowledge_version_id == version.id,
                KnowledgeEntity.id.in_(all_ids),
                KnowledgeEntity.entity_type == "TOPIC"
            )
            .count()
        )

        ev_pages = (
            db.query(KnowledgeEvidence.page_number)
            .filter(KnowledgeEvidence.entity_id.in_(all_ids))
            .all()
        )
        valid_pages = [p[0] for p in ev_pages if p[0] is not None and 0 <= p[0] < 99999]

        meta = getattr(c, "metadata_json", {}) or {}
        pos = meta.get("canonical_source_position")
        if pos and isinstance(pos, (list, tuple)) and len(pos) >= 1:
            p_val = pos[0]
            if p_val is not None and isinstance(p_val, int) and 0 <= p_val < 99999:
                valid_pages.append(p_val)

        if valid_pages:
            source_page_start = min(valid_pages)
            source_page_end = max(valid_pages)
        else:
            source_page_start = None
            source_page_end = None

        containers_data.append({
            "id": c.id,
            "title": c.title,
            "entity_type": c.entity_type.value if hasattr(c.entity_type, "value") else str(c.entity_type),
            "source_page_start": source_page_start,
            "source_page_end": source_page_end,
            "topic_count": topic_count,
            "stable_id": c.stable_id,
        })

    return {
        "knowledge_version_id": version.id,
        "document_id": doc_id,
        "upload_id": version.upload_id,
        "approval_version": f"v{approval_version}" if approval_version else None,
        "container_mode": result.mode.value if hasattr(result.mode, "value") else str(result.mode),
        "container_type": result.container_type,
        "containers": containers_data,
        "diagnostics": diagnostics,
    }


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


@router.get("/document/{document_id}/selectable-containers", response_model=SelectableContainersResponse)
def get_document_selectable_containers(document_id: str, db: Session = Depends(get_db)):
    """Fetch ordered selectable containers for the latest finalized version of a document."""
    repo = KnowledgeRepository(db)
    version = repo.get_latest_finalized_version(document_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No finalized knowledge version found for document ID '{document_id}'"
        )
    data = resolve_selectable_containers_for_version(version, db)
    return {"success": True, "data": data}


@router.get("/document/{document_id}/versions", response_model=VersionListResponse)
def list_finalized_versions(document_id: str, db: Session = Depends(get_db)):
    """List all finalized knowledge versions for the given document ID."""
    repo = KnowledgeRepository(db)
    versions = repo.list_finalized_versions(document_id)
    meta_list = [build_version_metadata(v, repo) for v in versions]
    return {"success": True, "data": meta_list}


@router.get("/versions/{version_id}/selectable-containers", response_model=SelectableContainersResponse)
def get_version_selectable_containers(version_id: str, db: Session = Depends(get_db)):
    """Fetch ordered selectable containers for a specific finalized knowledge version."""
    repo = KnowledgeRepository(db)
    version = repo.get_finalized_version(version_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finalized knowledge version '{version_id}' not found."
        )
    data = resolve_selectable_containers_for_version(version, db)
    return {"success": True, "data": data}


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
