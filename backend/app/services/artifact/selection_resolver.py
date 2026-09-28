"""
Selection resolver module for artifact generation.

Resolves, validates, and persists the effective container selection (Units or Chapters)
and ensures planning, validation, and retrieval share the exact same permitted scope.
"""

from typing import List, Dict, Set, Optional, Any
from dataclasses import dataclass
from sqlalchemy.orm import Session
from loguru import logger

from app.models.knowledge import (
    KnowledgeVersion,
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeEvidence
)
from app.models.document import Document
from app.services.intelligence.knowledge_ordering import (
    SelectableContainerMode,
    get_selectable_containers,
    get_container_descendants,
    sort_entities_by_source_order
)


@dataclass(frozen=True)
class EffectiveSelection:
    """
    Typed, immutable representation of the effective container selection
    for an artifact generation job.
    """
    knowledge_version_id: str
    document_id: str
    upload_id: str
    container_mode: SelectableContainerMode
    container_type: str  # "UNIT" or "CHAPTER"
    selected_container_ids: List[str]  # In textbook canonical source order
    permitted_entity_ids: Set[str]  # Union of selected containers and all their descendants
    permitted_evidence_ids: Set[str]  # Evidence IDs attached to permitted entities
    container_to_descendants: Dict[str, Set[str]]  # container_id -> set of descendant entity IDs


def resolve_document_id_for_version(db: Session, version: KnowledgeVersion) -> str:
    """
    Resolves the exact Document.id corresponding to a KnowledgeVersion.
    
    Rules:
    1. Checks KnowledgeEvidence for entities in this version.
       If evidence records exist, inspects their distinct document_id values:
       - If evidence references multiple distinct Document.ids, raises ValueError (ambiguous).
       - If evidence references a single Document.id:
         - Verifies the referenced Document exists in the database.
         - Verifies Document.upload_id matches KnowledgeVersion.upload_id.
         - Returns Document.id.
    2. If no evidence records exist in this version:
       Queries Document rows by Document.upload_id == version.upload_id:
       - If exactly one Document row exists, returns its id.
       - If multiple Document rows exist with no evidence to disambiguate, raises ValueError (ambiguous).
       - If no Document rows exist, raises ValueError (missing document association).
         There is NO fallback to version.upload_id.
    """
    doc_ids = (
        db.query(KnowledgeEvidence.document_id)
        .join(KnowledgeEntity, KnowledgeEvidence.entity_id == KnowledgeEntity.id)
        .filter(KnowledgeEntity.knowledge_version_id == version.id)
        .distinct()
        .all()
    )
    distinct_evidence_doc_ids = {d[0] for d in doc_ids if d[0]}

    if len(distinct_evidence_doc_ids) > 1:
        raise ValueError(
            f"Knowledge version '{version.id}' contains evidence referencing multiple distinct documents: {sorted(distinct_evidence_doc_ids)}."
        )

    if len(distinct_evidence_doc_ids) == 1:
        doc_id = distinct_evidence_doc_ids.pop()
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise ValueError(
                f"Document '{doc_id}' referenced by evidence in knowledge version '{version.id}' does not exist in the database."
            )
        if doc.upload_id != version.upload_id:
            raise ValueError(
                f"Document '{doc_id}' referenced by evidence belongs to upload '{doc.upload_id}', which does not match version upload '{version.upload_id}'."
            )
        return doc.id

    # Fallback to Document table by upload_id
    docs = db.query(Document).filter(Document.upload_id == version.upload_id).all()
    if len(docs) == 1:
        return docs[0].id
    elif len(docs) > 1:
        doc_list = [d.id for d in docs]
        raise ValueError(
            f"Ambiguous document association: upload_id '{version.upload_id}' maps to multiple documents {doc_list} and version '{version.id}' has no evidence records."
        )
    else:
        raise ValueError(
            f"No Document found for upload_id '{version.upload_id}' associated with knowledge version '{version.id}'."
        )


def resolve_effective_selection(
    db: Session,
    version_id: str,
    upload_id: str,
    config: Dict[str, Any]
) -> EffectiveSelection:
    """
    Resolves and validates the effective container selection for an artifact request or job.
    
    Validation:
    - KnowledgeVersion exists, belongs to upload_id, and is FINALIZED.
    - Resolves unambiguous Document.id.
    - Retrieves selectable containers (Units vs Chapters vs Review Required).
    - Validates selection:
      - Rejects if both selected_unit_ids and num_units provided.
      - If selected_unit_ids provided:
        - Non-empty list required (empty list is rejected).
        - Non-null string elements required.
        - Every ID must identify a selectable container in this version.
        - Non-container entities or foreign-version IDs are rejected with specific errors.
        - Duplicates are normalized.
        - Final selection is ordered deterministically by canonical source (textbook) order.
      - If num_units provided:
        - Positive integer within available container count required (rejects bool, fractional, <= 0).
        - Resolves top N containers in canonical source order.
      - If neither provided:
        - Defaults to all selectable containers in canonical source order.
    - Computes permitted descendant closures and associated evidence IDs.
    """
    version = db.query(KnowledgeVersion).filter(KnowledgeVersion.id == version_id).first()
    if not version:
        raise ValueError(f"Knowledge version '{version_id}' not found.")

    if version.upload_id != upload_id:
        raise ValueError(f"Knowledge version '{version_id}' does not belong to upload_id '{upload_id}'.")

    if version.status != "FINALIZED":
        raise ValueError(f"Cannot generate artifact from unfinalized knowledge version (status: '{version.status}').")

    document_id = resolve_document_id_for_version(db, version)

    # Check if client supplied an internal document_id: server-resolved identity is always authoritative
    client_supplied_doc_id = config.get("document_id")
    if client_supplied_doc_id and client_supplied_doc_id != document_id:
        logger.warning(
            f"Client-supplied document_id '{client_supplied_doc_id}' does not match authoritative server-resolved document_id '{document_id}' for version '{version.id}'. Overriding with server-resolved identity."
        )

    container_result = get_selectable_containers(db, version.id)
    available_containers = container_result.containers
    available_container_ids = [c.id for c in available_containers]
    available_container_id_set = set(available_container_ids)
    container_type = container_result.container_type or "CONTAINER"

    has_selected_ids = "selected_unit_ids" in config and config["selected_unit_ids"] is not None
    has_num_units = "num_units" in config and config["num_units"] is not None

    if has_selected_ids and has_num_units:
        raise ValueError("Cannot specify both 'selected_unit_ids' and 'num_units'.")

    if has_selected_ids:
        if container_result.mode == SelectableContainerMode.REVIEW_REQUIRED:
            raise ValueError(container_result.message)

        raw_ids = config["selected_unit_ids"]
        if not isinstance(raw_ids, list):
            raise ValueError("'selected_unit_ids' must be a list of container IDs.")
        if len(raw_ids) == 0:
            raise ValueError("Explicit selection cannot be empty.")

        for i, elem in enumerate(raw_ids):
            if elem is None:
                raise ValueError(f"Element at index {i} in 'selected_unit_ids' cannot be null.")
            if not isinstance(elem, str):
                raise ValueError(f"Element at index {i} in 'selected_unit_ids' must be a string, got {type(elem).__name__}.")
            if not elem.strip():
                raise ValueError(f"Element at index {i} in 'selected_unit_ids' cannot be an empty string.")

        # Normalize duplicates while preserving first-seen order
        deduped_ids = []
        seen = set()
        for uid in raw_ids:
            if uid not in seen:
                seen.add(uid)
                deduped_ids.append(uid)

        # Validate each ID
        for uid in deduped_ids:
            if uid not in available_container_id_set:
                # Check if it belongs to this version as a non-container entity
                ent_in_ver = db.query(KnowledgeEntity).filter(
                    KnowledgeEntity.knowledge_version_id == version.id,
                    KnowledgeEntity.id == uid
                ).first()
                if ent_in_ver:
                    etype = ent_in_ver.entity_type.value if hasattr(ent_in_ver.entity_type, "value") else str(ent_in_ver.entity_type)
                    raise ValueError(
                        f"Entity '{uid}' is of type '{etype}' and cannot be selected as a top-level {container_type.lower()} container."
                    )

                # Check if it exists elsewhere in the database
                ent_elsewhere = db.query(KnowledgeEntity).filter(KnowledgeEntity.id == uid).first()
                if ent_elsewhere:
                    raise ValueError(f"Container '{uid}' does not belong to knowledge version '{version.id}'.")

                raise ValueError(f"Container ID '{uid}' not found in knowledge version '{version.id}'.")

        # Re-order according to textbook canonical source order
        selected_set = set(deduped_ids)
        final_ordered_container_ids = [c.id for c in available_containers if c.id in selected_set]

    elif has_num_units:
        if container_result.mode == SelectableContainerMode.REVIEW_REQUIRED:
            raise ValueError(container_result.message)

        n = config["num_units"]
        if type(n) is bool:
            raise ValueError("'num_units' cannot be a boolean.")
        if not (type(n) is int):
            raise ValueError(f"'num_units' must be an integer, got {type(n).__name__}.")
        if n <= 0:
            raise ValueError(f"'num_units' must be a positive integer greater than zero, got {n}.")
        if n > len(available_containers):
            raise ValueError(
                f"Requested num_units ({n}) exceeds available {container_type.lower()} count ({len(available_containers)})."
            )
        final_ordered_container_ids = available_container_ids[:n]

    else:
        # Default when neither field is provided:
        # If containers exist, select all containers in canonical source order.
        # If no containers exist (e.g. empty test fixture version), default to empty list.
        final_ordered_container_ids = list(available_container_ids)

    # Compute permitted descendant entity IDs
    relationships = (
        db.query(KnowledgeRelationship)
        .filter(KnowledgeRelationship.knowledge_version_id == version.id)
        .all()
    )

    container_to_descendants: Dict[str, Set[str]] = {}
    permitted_entity_ids: Set[str] = set(final_ordered_container_ids)

    for cid in final_ordered_container_ids:
        desc_ids = get_container_descendants(cid, relationships)
        container_to_descendants[cid] = desc_ids
        permitted_entity_ids.update(desc_ids)

    # Fetch evidence IDs for all permitted entities
    ev_records = (
        db.query(KnowledgeEvidence.id)
        .filter(KnowledgeEvidence.entity_id.in_(permitted_entity_ids))
        .all()
    )
    permitted_evidence_ids = {e[0] for e in ev_records if e[0]}

    return EffectiveSelection(
        knowledge_version_id=version.id,
        document_id=document_id,
        upload_id=version.upload_id,
        container_mode=container_result.mode,
        container_type=container_type,
        selected_container_ids=final_ordered_container_ids,
        permitted_entity_ids=permitted_entity_ids,
        permitted_evidence_ids=permitted_evidence_ids,
        container_to_descendants=container_to_descendants
    )


def resolve_effective_selection_for_job(
    db: Optional[Session],
    job: Any,
    version_obj: Optional[Any] = None
) -> EffectiveSelection:
    """
    Resolves the effective selection for an ArtifactJob (or ArtifactJobRead).
    
    If db is provided, uses database-backed resolution.
    If db is None (e.g. unit tests with in-memory schema objects), falls back to schema-level resolution.
    """
    config = getattr(job, "config", {}) or {}
    upload_id = getattr(job, "upload_id", "")
    knowledge_version_id = getattr(job, "knowledge_version_id", "")

    if db is not None:
        return resolve_effective_selection(
            db=db,
            version_id=knowledge_version_id,
            upload_id=upload_id,
            config=config
        )

    # In-memory schema fallback for unit tests without a database session
    if version_obj is None:
        raise ValueError("Cannot resolve effective selection without db session or version_obj.")

    entities = getattr(version_obj, "entities", [])
    relationships = getattr(version_obj, "relationships", [])

    def _etype(e):
        t = getattr(e, "entity_type", "")
        return t.value if hasattr(t, "value") else str(t)

    units = [e for e in entities if _etype(e) == "UNIT"]
    if units:
        mode = SelectableContainerMode.UNITS
        container_type = "UNIT"
        containers = units
    else:
        chapters = [e for e in entities if _etype(e) == "CHAPTER"]
        if chapters:
            mode = SelectableContainerMode.CHAPTERS
            container_type = "CHAPTER"
            containers = chapters
        else:
            mode = SelectableContainerMode.REVIEW_REQUIRED
            container_type = "CONTAINER"
            containers = []

    if mode == SelectableContainerMode.REVIEW_REQUIRED:
        raise ValueError("No selectable containers found in version.")

    container_ids = [c.id for c in containers]
    container_id_set = set(container_ids)

    has_selected_ids = "selected_unit_ids" in config and config["selected_unit_ids"] is not None
    has_num_units = "num_units" in config and config["num_units"] is not None

    if has_selected_ids and has_num_units:
        raise ValueError("Cannot specify both 'selected_unit_ids' and 'num_units'.")

    if has_selected_ids:
        raw_ids = config["selected_unit_ids"]
        if not isinstance(raw_ids, list):
            raise ValueError("'selected_unit_ids' must be a list.")
        if len(raw_ids) == 0:
            raise ValueError("Explicit selection cannot be empty.")
        deduped = []
        for x in raw_ids:
            if x not in deduped:
                deduped.append(x)
        for x in deduped:
            if x not in container_id_set:
                raise ValueError(f"Container '{x}' not found in selectable containers.")
        final_ids = [c.id for c in containers if c.id in set(deduped)]
    elif has_num_units:
        n = config["num_units"]
        if not isinstance(n, int) or n <= 0:
            raise ValueError("num_units must be positive int.")
        final_ids = container_ids[:n]
    else:
        final_ids = list(container_ids)

    container_to_descendants = {}
    permitted_entity_ids = set(final_ids)
    for cid in final_ids:
        desc_ids = get_container_descendants(cid, relationships)
        container_to_descendants[cid] = desc_ids
        permitted_entity_ids.update(desc_ids)

    # Document ID from config or upload_id fallback
    doc_id = config.get("document_id") or upload_id

    # Evidence IDs from entities
    permitted_ev_ids = set()
    for e in entities:
        if e.id in permitted_entity_ids:
            for ev in getattr(e, "evidence", []):
                if getattr(ev, "id", None):
                    permitted_ev_ids.add(ev.id)

    return EffectiveSelection(
        knowledge_version_id=knowledge_version_id,
        document_id=doc_id,
        upload_id=upload_id,
        container_mode=mode,
        container_type=container_type,
        selected_container_ids=final_ids,
        permitted_entity_ids=permitted_entity_ids,
        permitted_evidence_ids=permitted_ev_ids,
        container_to_descendants=container_to_descendants
    )
