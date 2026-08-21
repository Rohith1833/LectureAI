import uuid
import time
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.document import Document, DocumentBlock
from app.models.review import AcademicGraphSnapshot
from app.models.knowledge import (
    KnowledgeVersion,
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeEvidence
)
from app.schemas.knowledge import KnowledgeRelationshipType, KnowledgeEvidenceProvenance

# Valid Phase 6A node categories
VALID_KNOWLEDGE_CATEGORIES = {
    "CHAPTER", "SECTION", "TOPIC", "CONCEPT", "DEFINITION", 
    "THEOREM", "PROOF", "FORMULA", "ALGORITHM", "EXAMPLE", 
    "EXERCISE", "SUMMARY"
}

class KnowledgeBuilder:
    def __init__(self, db: Session):
        self.db = db

    def compile_snapshot(self, snapshot_id: str, reviewer_id: str = "system") -> KnowledgeVersion:
        """
        Translates an approved AcademicGraphSnapshot into a finalized KnowledgeVersion.
        Ensures strict isolation, category contracts, stable identity checks, and idempotency.
        """
        # 1. Fetch snapshot
        snapshot = self.db.query(AcademicGraphSnapshot).filter(AcademicGraphSnapshot.id == snapshot_id).first()
        if not snapshot:
            raise ValueError(f"AcademicGraphSnapshot with ID '{snapshot_id}' not found.")

        # 2. Verify Document is APPROVED
        doc = self.db.query(Document).filter(Document.upload_id == snapshot.upload_id).first()
        if not doc:
            raise ValueError(f"Document for upload ID '{snapshot.upload_id}' not found.")
        
        if doc.review_state != "APPROVED":
            raise ValueError(f"Document associated with snapshot '{snapshot_id}' is not APPROVED (currently: '{doc.review_state}').")

        # 3. Check for existing finalized version (Idempotency Invariant)
        existing_finalized = (
            self.db.query(KnowledgeVersion)
            .filter(KnowledgeVersion.snapshot_id == snapshot_id, KnowledgeVersion.status == "FINALIZED")
            .first()
        )
        if existing_finalized:
            return existing_finalized

        # Clean up any partial versions in BUILDING state for this snapshot
        existing_building = (
            self.db.query(KnowledgeVersion)
            .filter(KnowledgeVersion.snapshot_id == snapshot_id, KnowledgeVersion.status == "BUILDING")
            .all()
        )
        for eb in existing_building:
            self.db.delete(eb)
        self.db.flush()

        # 4. Attempt locking snapshot row (Ignored/No-op on SQLite, enforced on Postgres)
        try:
            self.db.query(AcademicGraphSnapshot).filter(AcademicGraphSnapshot.id == snapshot_id).with_for_update(nowait=True).first()
        except Exception:
            pass

        # 5. Initialize BUILDING KnowledgeVersion
        version = KnowledgeVersion(
            id=str(uuid.uuid4()),
            upload_id=snapshot.upload_id,
            snapshot_id=snapshot.id,
            schema_version="1.0.0",
            status="BUILDING",
            metadata_json={"reviewer_id": reviewer_id, "compiled_timestamp": time.time()}
        )
        self.db.add(version)
        self.db.flush()

        try:
            # Fetch all document blocks for fast lookup
            doc_blocks = {
                b.id: b for b in self.db.query(DocumentBlock).filter(DocumentBlock.document_id == doc.id).all()
            }

            node_id_to_entity_id: Dict[str, str] = {}
            compiled_entities: Dict[str, KnowledgeEntity] = {}

            # Compile Entities
            for s_node in snapshot.nodes:
                category = s_node.get("category")
                
                # Category Contract: filter out UNIT, LEARNING_OBJECTIVE, etc.
                if category not in VALID_KNOWLEDGE_CATEGORIES:
                    continue

                # Stable Identity Rule
                anchor_key = s_node.get("anchor_key")
                if not anchor_key:
                    # Fallback policy for manual nodes only
                    if s_node.get("review_state") == "MODIFIED" or "HUMAN_OVERRIDE" in s_node.get("metadata", {}).get("provenance", ""):
                        anchor_key = f"anc_manual_{s_node.get('node_id')}"
                    else:
                        # Reject ordinary node lacking stable anchor key
                        continue

                # Core title and content derived directly from approved snapshot (not mutable DB text)
                title = s_node.get("title") or "Untitled Entity"
                content = title

                entity = KnowledgeEntity(
                    id=str(uuid.uuid4()),
                    knowledge_version_id=version.id,
                    entity_type=category,
                    title=title,
                    content=content,
                    stable_id=anchor_key,
                    metadata_json=s_node.get("metadata")
                )
                self.db.add(entity)
                self.db.flush()

                node_id_to_entity_id[s_node["node_id"]] = entity.id
                compiled_entities[entity.id] = entity

                # Compile Evidence
                target_block_id = s_node.get("target_block_id")
                if target_block_id:
                    block = doc_blocks.get(target_block_id)
                    # Verify block exists and matches approved document
                    if block:
                        page_num = block.page_number
                        x0, y0, x1, y1 = block.x0, block.y0, block.x1, block.y1
                        text_ref = block.text

                        # Walk up parent blocks to find section header
                        section_title = None
                        curr_block = block
                        visited = set()
                        while curr_block and curr_block.parent_block_id and curr_block.id not in visited:
                            visited.add(curr_block.id)
                            parent_b = doc_blocks.get(curr_block.parent_block_id)
                            if parent_b:
                                if parent_b.block_type == "HEADING":
                                    section_title = parent_b.text
                                    break
                                curr_block = parent_b
                            else:
                                break

                        # Authoritative Provenance Mapping
                        raw_prov = s_node.get("metadata", {}).get("provenance")
                        if not raw_prov and block.provenance:
                            raw_prov = block.provenance

                        if raw_prov == "HUMAN_OVERRIDE":
                            prov_enum = KnowledgeEvidenceProvenance.HUMAN_OVERRIDE
                        elif raw_prov and (raw_prov in ["CURRICULUM_CLASSIFICATION_MODULE", "EXPOSITORY_CLASSIFICATION_MODULE", "PEDAGOGICAL_CLASSIFICATION_MODULE", "AUTOMATIC", "NATIVE", "OCR", "MERGED"]):
                            prov_enum = KnowledgeEvidenceProvenance.EXPLICIT_CLASSIFIER
                        elif raw_prov == "DERIVED_HIERARCHY":
                            prov_enum = KnowledgeEvidenceProvenance.DERIVED_HIERARCHY
                        else:
                            prov_enum = KnowledgeEvidenceProvenance.UNKNOWN

                        evidence = KnowledgeEvidence(
                            id=str(uuid.uuid4()),
                            entity_id=entity.id,
                            document_id=doc.id,
                            page_number=page_num,
                            section_title=section_title,
                            source_node_id=s_node["node_id"],
                            source_anchor_key=anchor_key,
                            text_reference=text_ref,
                            provenance=prov_enum.value,
                            x0=x0, y0=y0, x1=x1, y1=y1
                        )
                        self.db.add(evidence)
                    else:
                        # Mismatched/Stale block: Fallback to Page None, null coordinates, UNKNOWN provenance
                        evidence = KnowledgeEvidence(
                            id=str(uuid.uuid4()),
                            entity_id=entity.id,
                            document_id=doc.id,
                            page_number=None,
                            section_title=None,
                            source_node_id=s_node["node_id"],
                            source_anchor_key=anchor_key,
                            text_reference=None,
                            provenance=KnowledgeEvidenceProvenance.UNKNOWN.value,
                            x0=None, y0=None, x1=None, y1=None
                        )
                        self.db.add(evidence)

            # Compile Relationships
            for s_edge in snapshot.edges:
                src_node_id = s_edge.get("source_node_id")
                tgt_node_id = s_edge.get("target_node_id")
                edge_type = s_edge.get("edge_type")

                # Endpoint containment filter
                src_entity_id = node_id_to_entity_id.get(src_node_id)
                tgt_entity_id = node_id_to_entity_id.get(tgt_node_id)
                if not src_entity_id or not tgt_entity_id:
                    continue

                # Relationship Type Validation
                try:
                    rel_type = KnowledgeRelationshipType(edge_type)
                except ValueError:
                    continue

                # Self-loop check
                if src_entity_id == tgt_entity_id:
                    continue

                metadata = s_edge.get("metadata") or {}
                is_inferred = metadata.get("is_inferred", False)
                is_human_confirmed = metadata.get("is_human_confirmed", False)

                rel = KnowledgeRelationship(
                    id=str(uuid.uuid4()),
                    knowledge_version_id=version.id,
                    source_entity_id=src_entity_id,
                    target_entity_id=tgt_entity_id,
                    relationship_type=rel_type.value,
                    confidence=s_edge.get("confidence", 1.0),
                    is_inferred=is_inferred,
                    is_human_confirmed=is_human_confirmed,
                    metadata_json=metadata
                )
                self.db.add(rel)

            # 6. Finalize transaction
            self.db.flush()
            version.status = "FINALIZED"
            self.db.commit()
            return version

        except IntegrityError as ie:
            self.db.rollback()
            # Concurrent identical compiles will trigger unique constraint on snapshot_id
            if "uq_kv_snapshot_id" in str(ie) or "uq_snapshot_id" in str(ie):
                existing = (
                    self.db.query(KnowledgeVersion)
                    .filter(KnowledgeVersion.snapshot_id == snapshot_id, KnowledgeVersion.status == "FINALIZED")
                    .first()
                )
                if existing:
                    return existing
            raise ie
        except Exception as e:
            self.db.rollback()
            raise e
