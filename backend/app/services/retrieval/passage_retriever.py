from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.repositories.document_repository import DocumentRepository
from app.services.retrieval.evidence_retriever import EvidenceCandidate
from app.services.retrieval.scope_resolver import ResolvedScope


@dataclass
class PassageCandidate:
    """Represents a resolved source passage containing verbatim DocumentBlock text and layout boundaries."""
    document_id: str
    block_id: str
    page_number: int
    text: str
    block_type: str
    x0: float
    y0: float
    x1: float
    y1: float
    section_title: Optional[str]
    entity_ids: List[str] = field(default_factory=list)
    previous_text: Optional[str] = None
    next_text: Optional[str] = None


class PassageRetriever:
    """
    Resolves non-stale EvidenceCandidates to precise DocumentBlocks via bounding-box overlap.
    Tracks surrounding text context and aggregates mapped entity references.
    """

    def __init__(self, doc_repo: DocumentRepository):
        self.doc_repo = doc_repo

    def retrieve_passages(
        self,
        evidence_candidates: List[EvidenceCandidate],
        resolved_scope: ResolvedScope
    ) -> List[PassageCandidate]:
        """
        Orchestrates bounding box coordinate checks on DocumentBlocks for non-stale evidence.
        Groups multiple entity references backing the same block.
        Returns a list of PassageCandidates.
        """
        # Map block_id -> PassageCandidate to deduplicate and group entity_ids
        passages_map: Dict[str, PassageCandidate] = {}

        for cand in evidence_candidates:
            # Case C: stale evidence skips passage lookup
            if cand.is_stale:
                continue

            ev = cand.evidence
            page_num = ev.page_number

            # Coordinate check (coordinates must be all-or-nothing)
            has_coords = (
                ev.x0 is not None and
                ev.y0 is not None and
                ev.x1 is not None and
                ev.y1 is not None
            )

            # Case B: page exists but coordinates are missing -> skip passage resolution
            if not has_coords:
                continue

            # Fetch page blocks ensuring Document Isolation (scope to ev.document_id)
            blocks = self.doc_repo.get_blocks_for_page(ev.document_id, page_num)
            if not blocks:
                continue

            # Find matching block with largest bounding box overlap area (Case A)
            matched_block = None
            max_overlap_area = 0.0

            # Selection rule:
            # 1. Largest intersection area.
            # 2. Tie break: lower reading_order first, then block_id alphabetically.
            for block in blocks:
                # Calculate intersection bounding box coordinates
                x_left = max(ev.x0, block.x0)
                y_top = max(ev.y0, block.y0)
                x_right = min(ev.x1, block.x1)
                y_bottom = min(ev.y1, block.y1)

                if x_right > x_left and y_bottom > y_top:
                    overlap_area = (x_right - x_left) * (y_bottom - y_top)
                else:
                    overlap_area = 0.0

                if overlap_area > 0.0:
                    if overlap_area > max_overlap_area:
                        max_overlap_area = overlap_area
                        matched_block = block
                    elif abs(overlap_area - max_overlap_area) < 1e-6:
                        # Tie break logic
                        if matched_block is None:
                            matched_block = block
                        else:
                            if block.reading_order < matched_block.reading_order:
                                matched_block = block
                            elif block.reading_order == matched_block.reading_order:
                                if block.id < matched_block.id:
                                    matched_block = block

            if not matched_block:
                # Case 16: non-stale but no matching block resolved -> skip passage (no crash)
                continue

            # Verify block ID is a real DocumentBlock.id
            block_id = matched_block.id

            if block_id in passages_map:
                # Aggregate entity reference to the existing passage candidate
                if cand.entity_id not in passages_map[block_id].entity_ids:
                    passages_map[block_id].entity_ids.append(cand.entity_id)
            else:
                # Resolve surrounding context (previous/next blocks on the same page)
                previous_text = None
                if matched_block.previous_block_id:
                    prev_block = self.doc_repo.get_block(matched_block.previous_block_id)
                    if prev_block and prev_block.document_id == ev.document_id:
                        previous_text = prev_block.text

                next_text = None
                if matched_block.next_block_id:
                    next_block = self.doc_repo.get_block(matched_block.next_block_id)
                    if next_block and next_block.document_id == ev.document_id:
                        next_text = next_block.text

                # Build passage candidate
                passages_map[block_id] = PassageCandidate(
                    document_id=ev.document_id,
                    block_id=block_id,  # Real DocumentBlock ID
                    page_number=page_num,
                    text=matched_block.text,  # Verbatim live text
                    block_type=matched_block.block_type,
                    x0=matched_block.x0,
                    y0=matched_block.y0,
                    x1=matched_block.x1,
                    y1=matched_block.y1,
                    section_title=ev.section_title,  # Static compiled section title
                    entity_ids=[cand.entity_id],
                    previous_text=previous_text,
                    next_text=next_text
                )

        return list(passages_map.values())
