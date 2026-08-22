from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.document import Document
from app.models.review import AcademicGraphSnapshot
from app.models.knowledge import (
    KnowledgeVersion,
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeEvidence
)


class KnowledgeRepository:
    """Repository managing ORM mapping queries for versioned, finalized knowledge."""

    def __init__(self, db: Session):
        self.db = db

    def get_finalized_version(self, version_id: str) -> Optional[KnowledgeVersion]:
        """Fetch a specific KnowledgeVersion only if it is FINALIZED."""
        return (
            self.db.query(KnowledgeVersion)
            .filter(KnowledgeVersion.id == version_id, KnowledgeVersion.status == "FINALIZED")
            .first()
        )

    def get_latest_finalized_version(self, document_id: str) -> Optional[KnowledgeVersion]:
        """
        Resolves the latest finalized version of knowledge for the document.
        Orders authoritatively by AcademicGraphSnapshot.approval_version descending.
        """
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return None
        return (
            self.db.query(KnowledgeVersion)
            .join(AcademicGraphSnapshot, KnowledgeVersion.snapshot_id == AcademicGraphSnapshot.id)
            .filter(
                AcademicGraphSnapshot.upload_id == doc.upload_id,
                KnowledgeVersion.status == "FINALIZED"
            )
            .order_by(AcademicGraphSnapshot.approval_version.desc())
            .first()
        )

    def list_finalized_versions(self, document_id: str) -> List[KnowledgeVersion]:
        """List all finalized KnowledgeVersions for the document, ordered version descending."""
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return []
        return (
            self.db.query(KnowledgeVersion)
            .join(AcademicGraphSnapshot, KnowledgeVersion.snapshot_id == AcademicGraphSnapshot.id)
            .filter(
                AcademicGraphSnapshot.upload_id == doc.upload_id,
                KnowledgeVersion.status == "FINALIZED"
            )
            .order_by(AcademicGraphSnapshot.approval_version.desc())
            .all()
        )

    def get_version_counts(self, version_id: str) -> Dict[str, int]:
        """Get entity, relationship, and evidence counts for a specific version."""
        entity_count = self.db.query(func.count(KnowledgeEntity.id)).filter(KnowledgeEntity.knowledge_version_id == version_id).scalar() or 0
        relationship_count = self.db.query(func.count(KnowledgeRelationship.id)).filter(KnowledgeRelationship.knowledge_version_id == version_id).scalar() or 0
        evidence_count = (
            self.db.query(func.count(KnowledgeEvidence.id))
            .join(KnowledgeEntity)
            .filter(KnowledgeEntity.knowledge_version_id == version_id)
            .scalar() or 0
        )
        return {
            "entity_count": entity_count,
            "relationship_count": relationship_count,
            "evidence_count": evidence_count
        }

    def list_entities(
        self,
        version_id: str,
        entity_type: Optional[str] = None,
        stable_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[KnowledgeEntity]:
        """List entities in a finalized version with type/stable filters and pagination."""
        query = self.db.query(KnowledgeEntity).filter(KnowledgeEntity.knowledge_version_id == version_id)
        if entity_type:
            query = query.filter(KnowledgeEntity.entity_type == entity_type)
        if stable_id:
            query = query.filter(KnowledgeEntity.stable_id == stable_id)
        return query.order_by(KnowledgeEntity.title.asc(), KnowledgeEntity.id.asc()).limit(limit).offset(offset).all()

    def count_entities(
        self,
        version_id: str,
        entity_type: Optional[str] = None,
        stable_id: Optional[str] = None
    ) -> int:
        """Count entities in a finalized version matching filter parameters."""
        query = self.db.query(func.count(KnowledgeEntity.id)).filter(KnowledgeEntity.knowledge_version_id == version_id)
        if entity_type:
            query = query.filter(KnowledgeEntity.entity_type == entity_type)
        if stable_id:
            query = query.filter(KnowledgeEntity.stable_id == stable_id)
        return query.scalar() or 0

    def get_entity(self, version_id: str, entity_id: str) -> Optional[KnowledgeEntity]:
        """Fetch a specific KnowledgeEntity belonging to the specified version."""
        return (
            self.db.query(KnowledgeEntity)
            .filter(KnowledgeEntity.id == entity_id, KnowledgeEntity.knowledge_version_id == version_id)
            .first()
        )

    def list_relationships(
        self,
        version_id: str,
        source_entity_id: Optional[str] = None,
        target_entity_id: Optional[str] = None,
        relationship_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[KnowledgeRelationship]:
        """List relationships with source/target/type filters and pagination."""
        query = self.db.query(KnowledgeRelationship).filter(KnowledgeRelationship.knowledge_version_id == version_id)
        if source_entity_id:
            query = query.filter(KnowledgeRelationship.source_entity_id == source_entity_id)
        if target_entity_id:
            query = query.filter(KnowledgeRelationship.target_entity_id == target_entity_id)
        if relationship_type:
            query = query.filter(KnowledgeRelationship.relationship_type == relationship_type)
        return query.order_by(KnowledgeRelationship.id.asc()).limit(limit).offset(offset).all()

    def count_relationships(
        self,
        version_id: str,
        source_entity_id: Optional[str] = None,
        target_entity_id: Optional[str] = None,
        relationship_type: Optional[str] = None
    ) -> int:
        """Count relationships matching filter parameters."""
        query = self.db.query(func.count(KnowledgeRelationship.id)).filter(KnowledgeRelationship.knowledge_version_id == version_id)
        if source_entity_id:
            query = query.filter(KnowledgeRelationship.source_entity_id == source_entity_id)
        if target_entity_id:
            query = query.filter(KnowledgeRelationship.target_entity_id == target_entity_id)
        if relationship_type:
            query = query.filter(KnowledgeRelationship.relationship_type == relationship_type)
        return query.scalar() or 0

    def list_evidence_by_entity(self, entity_id: str) -> List[KnowledgeEvidence]:
        """Fetch all evidence records linked to a specific entity."""
        return (
            self.db.query(KnowledgeEvidence)
            .filter(KnowledgeEvidence.entity_id == entity_id)
            .order_by(KnowledgeEvidence.page_number.asc(), KnowledgeEvidence.id.asc())
            .all()
        )

    def get_entity_relationships(self, version_id: str, entity_id: str) -> Dict[str, List[KnowledgeRelationship]]:
        """Retrieve incoming and outgoing relationships for a specific entity separately."""
        incoming = (
            self.db.query(KnowledgeRelationship)
            .filter(
                KnowledgeRelationship.knowledge_version_id == version_id,
                KnowledgeRelationship.target_entity_id == entity_id
            )
            .order_by(KnowledgeRelationship.id.asc())
            .all()
        )
        outgoing = (
            self.db.query(KnowledgeRelationship)
            .filter(
                KnowledgeRelationship.knowledge_version_id == version_id,
                KnowledgeRelationship.source_entity_id == entity_id
            )
            .order_by(KnowledgeRelationship.id.asc())
            .all()
        )
        return {"incoming": incoming, "outgoing": outgoing}

    def search_entities(
        self,
        knowledge_version_id: str,
        terms: List[str],
        entity_types: Optional[List[str]] = None
    ) -> List[KnowledgeEntity]:
        """
        Retrieves entities within a finalized KnowledgeVersion matching search terms.
        Limits retrieval to the specified version and optional entity type filters.
        """
        if not terms:
            return []

        query = self.db.query(KnowledgeEntity).filter(
            KnowledgeEntity.knowledge_version_id == knowledge_version_id
        )
        if entity_types:
            query = query.filter(KnowledgeEntity.entity_type.in_(entity_types))

        entities = query.all()

        matched = []
        for entity in entities:
            title_lower = entity.title.lower()
            content_lower = (entity.content or "").lower()
            # Match if any term is in title or content
            if any(term.lower() in title_lower or term.lower() in content_lower for term in terms):
                matched.append(entity)
        return matched
