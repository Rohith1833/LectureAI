from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any
from loguru import logger

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
    diagnostics: List[str] = field(default_factory=list)

def check_text_references_overlap(ref1: str, ref2: str, block_text: Optional[str] = None) -> bool:
    """
    Check if two text references overlap completely, via block span, or via partial substring boundary.
    """
    r1 = (ref1 or "").strip()
    r2 = (ref2 or "").strip()
    if not r1 or not r2:
        return False
    # 1. Complete containment
    if r1 in r2 or r2 in r1:
        return True
    # 2. Block text occurrence span overlap
    if block_text and r1 in block_text and r2 in block_text:
        r1_spans = []
        pos = 0
        while True:
            idx = block_text.find(r1, pos)
            if idx == -1:
                break
            r1_spans.append((idx, idx + len(r1)))
            pos = idx + 1
        r2_spans = []
        pos = 0
        while True:
            idx = block_text.find(r2, pos)
            if idx == -1:
                break
            r2_spans.append((idx, idx + len(r2)))
            pos = idx + 1
        for s1, e1 in r1_spans:
            for s2, e2 in r2_spans:
                if max(s1, s2) < min(e1, e2):
                    return True
    # 3. Partial overlap (prefix / suffix overlap >= 10 chars or 2 words)
    min_len = min(len(r1), len(r2))
    thresh = min(10, min_len)
    for l in range(thresh, min_len + 1):
        if r1.endswith(r2[:l]) or r2.endswith(r1[:l]):
            return True
    return False


class PassageRetriever:
    """
    Resolves non-stale EvidenceCandidates to precise DocumentBlocks or verified text spans.
    Uses verified provenance to isolate permitted text from mixed blocks and disambiguate cross-scope candidates.
    Tracks surrounding text context and aggregates mapped entity references.
    Emits explicit diagnostics when safe layout boundaries cannot be established.
    """

    def __init__(self, doc_repo: DocumentRepository, knowledge_repo: Optional[Any] = None):
        self.doc_repo = doc_repo
        self.knowledge_repo = knowledge_repo
        if self.knowledge_repo is None and hasattr(self.doc_repo, "db") and self.doc_repo.db:
            from app.repositories.knowledge_repository import KnowledgeRepository
            self.knowledge_repo = KnowledgeRepository(self.doc_repo.db)
        self.diagnostics: List[str] = []
        self.excluded_evidence_ids: set = set()

    def retrieve_passages(
        self,
        evidence_candidates: List[EvidenceCandidate],
        resolved_scope: ResolvedScope
    ) -> List[PassageCandidate]:
        """
        Orchestrates bounding box coordinate checks on DocumentBlocks for non-stale evidence.
        Groups multiple entity references backing the same block.
        Returns a list of PassageCandidates and records diagnostic details for unresolvable boundaries.
        """
        self.diagnostics.clear()
        self.excluded_evidence_ids.clear()
        # Map passage_key -> PassageCandidate to deduplicate and group entity_ids
        passages_map: Dict[str, PassageCandidate] = {}

        is_scoped = resolved_scope.allowed_entity_ids is not None
        allowed_entity_ids = set(resolved_scope.allowed_entity_ids) if is_scoped else None

        for cand in evidence_candidates:
            # Case C: stale evidence skips passage lookup
            if cand.is_stale:
                continue

            ev = cand.evidence
            page_num = ev.page_number
            if page_num is None:
                diag = f"MISSING_PAGE_NUMBER: Evidence '{ev.id}' lacks page number. Excluded."
                self.diagnostics.append(diag)
                self.excluded_evidence_ids.add(ev.id)
                continue

            # Fetch page blocks ensuring Document Isolation (scope to ev.document_id)
            blocks = self.doc_repo.get_blocks_for_page(ev.document_id, page_num)
            if not blocks:
                diag = f"NO_PAGE_BLOCKS: No document blocks found for document '{ev.document_id}' on page {page_num}."
                self.diagnostics.append(diag)
                logger.debug(diag)
                self.excluded_evidence_ids.add(ev.id)
                continue

            # Query page evidences to discover cross-scope boundaries
            page_evidences = []
            if self.knowledge_repo:
                page_evidences = self.knowledge_repo.get_all_evidence_for_page(
                    ev.document_id, page_num, resolved_scope.version_id
                )

            # Unselected evidences on this page (if scoped)
            unselected_page_evs = [
                e for e in page_evidences
                if is_scoped and allowed_entity_ids is not None and e.entity_id not in allowed_entity_ids
            ]

            # Coordinate check (coordinates must be all-or-nothing)
            has_coords = (
                ev.x0 is not None and
                ev.y0 is not None and
                ev.x1 is not None and
                ev.y1 is not None
            )

            matched_block = None
            is_exact_span_resolution = False
            resolved_text = None

            if not has_coords:
                # Rule B: Missing coordinates
                # A missing bounding box does not require rejection if another trustworthy source reference establishes the exact allowed text.
                trustworthy_ref = (ev.text_reference or "").strip()
                candidate_blocks = [b for b in blocks if trustworthy_ref and trustworthy_ref in b.text] if trustworthy_ref else []
                if candidate_blocks:
                    if len(candidate_blocks) > 1:
                        # Check exact block provenance if available
                        ev_meta = ev.metadata if isinstance(getattr(ev, 'metadata', None), dict) else (getattr(ev, 'metadata_json', None) or {})
                        exact_block_id = ev_meta.get("block_id") or ev_meta.get("source_block_id") or (ev.source_anchor_key if any(b.id == ev.source_anchor_key for b in candidate_blocks) else None)
                        exact_blocks = [b for b in candidate_blocks if b.id == exact_block_id] if exact_block_id else []
                        if len(exact_blocks) == 1:
                            matched_block = exact_blocks[0]
                        else:
                            diag = f"CROSS_SCOPE_AMBIGUITY: Multiple candidate blocks on page {page_num} match text reference for evidence '{ev.id}' lacking coordinates without exact block provenance. Excluded."
                            self.diagnostics.append(diag)
                            self.excluded_evidence_ids.add(ev.id)
                            continue
                    else:
                        matched_block = candidate_blocks[0]
                    is_exact_span_resolution = True
                    resolved_text = trustworthy_ref
                    diag = f"EXACT_SPAN_RESOLVED: Evidence '{ev.id}' lacking coordinates was resolved via trustworthy text reference on page {page_num}."
                    self.diagnostics.append(diag)
                else:
                    diag = f"MISSING_BOUNDING_BOX: Evidence '{ev.id}' on page {page_num} lacks bounding box coordinates and has no trustworthy text reference. Whole-page fallback suppressed to preserve passage isolation."
                    self.diagnostics.append(diag)
                    logger.debug(diag)
                    self.excluded_evidence_ids.add(ev.id)
                    continue
            else:
                # Coordinate-based lookup:
                # Treat geometric overlap as candidate matching, not proof of semantic ownership.
                intersecting_candidates = []
                for block in blocks:
                    x_left = max(ev.x0, block.x0)
                    y_top = max(ev.y0, block.y0)
                    x_right = min(ev.x1, block.x1)
                    y_bottom = min(ev.y1, block.y1)

                    if x_right > x_left and y_bottom > y_top:
                        overlap_area = (x_right - x_left) * (y_bottom - y_top)
                        intersecting_candidates.append((block, overlap_area))

                if not intersecting_candidates:
                    diag = f"NO_BLOCK_MATCH: Evidence '{ev.id}' bounding box ({ev.x0}, {ev.y0}, {ev.x1}, {ev.y1}) on page {page_num} did not intersect any document block."
                    self.diagnostics.append(diag)
                    logger.debug(diag)
                    self.excluded_evidence_ids.add(ev.id)
                    continue

                # Disambiguate cross-scope candidates:
                # Do not resolve ambiguous cross-scope candidates solely by largest intersection area.
                # Use validated provenance to disambiguate.
                ev_ref = (ev.text_reference or "").strip()
                if is_scoped and len(intersecting_candidates) > 1:
                    ev_meta = ev.metadata if isinstance(getattr(ev, 'metadata', None), dict) else (getattr(ev, 'metadata_json', None) or {})
                    exact_block_id = ev_meta.get("block_id") or ev_meta.get("source_block_id") or (ev.source_anchor_key if any(b.id == ev.source_anchor_key for b, _ in intersecting_candidates) else None)
                    if exact_block_id:
                        exact_matches = [b for b, _ in intersecting_candidates if b.id == exact_block_id]
                        if len(exact_matches) == 1:
                            matched_block = exact_matches[0]
                        else:
                            matched_block = None
                    else:
                        matched_block = None

                    if not matched_block:
                        provenance_matches = [b for b, _ in intersecting_candidates if ev_ref and ev_ref in b.text]
                        if len(provenance_matches) == 1:
                            matched_block = provenance_matches[0]
                        elif len(provenance_matches) > 1:
                            # Indistinguishable multiple cross-scope matches: exclude! Do not choose largest area.
                            diag = f"CROSS_SCOPE_AMBIGUITY: Multiple candidate blocks on page {page_num} match evidence '{ev.id}' text reference and cannot be disambiguated by provenance without exact block reference. Excluded."
                            self.diagnostics.append(diag)
                            self.excluded_evidence_ids.add(ev.id)
                            continue
                        else:
                            cross_scope_detected = False
                            for b, _ in intersecting_candidates:
                                if any(
                                    ue.x0 is not None and ue.x1 is not None and ue.y0 is not None and ue.y1 is not None and
                                    max(ue.x0, b.x0) < min(ue.x1, b.x1) and max(ue.y0, b.y0) < min(ue.y1, b.y1)
                                    for ue in unselected_page_evs
                                ):
                                    cross_scope_detected = True
                                    break
                                if any(
                                    ue.text_reference and ue.text_reference.strip() and ue.text_reference.strip() in b.text
                                    for ue in unselected_page_evs
                                ):
                                    cross_scope_detected = True
                                    break

                            if cross_scope_detected or is_scoped:
                                diag = f"CROSS_SCOPE_AMBIGUITY: Evidence '{ev.id}' overlaps cross-scope candidate blocks without validated provenance disambiguation on page {page_num}. Excluded."
                                self.diagnostics.append(diag)
                                self.excluded_evidence_ids.add(ev.id)
                                continue
                            else:
                                intersecting_candidates.sort(key=lambda item: (-item[1], item[0].reading_order, item[0].id))
                                matched_block = intersecting_candidates[0][0]
                else:
                    intersecting_candidates.sort(key=lambda item: (-item[1], item[0].reading_order, item[0].id))
                    matched_block = intersecting_candidates[0][0]

            if not matched_block:
                continue

            # Check if matched_block is a mixed block containing exclusively unselected content
            is_mixed_block = False
            if is_scoped and unselected_page_evs:
                for ue in unselected_page_evs:
                    if ue.x0 is not None and ue.x1 is not None and ue.y0 is not None and ue.y1 is not None:
                        if max(ue.x0, matched_block.x0) < min(ue.x1, matched_block.x1) and max(ue.y0, matched_block.y0) < min(ue.y1, matched_block.y1):
                            is_mixed_block = True
                            break
                    if ue.text_reference and ue.text_reference.strip() and ue.text_reference.strip() in matched_block.text:
                        is_mixed_block = True
                        break

            if is_mixed_block:
                # For mixed blocks:
                # Extract a selected portion only when persisted source spans or equivalent verified boundaries support it.
                # Otherwise exclude the block.
                # Do not use an LLM, invented offsets, or guessed heading splits to manufacture isolation.
                ev_ref = (ev.text_reference or "").strip()
                if ev_ref and ev_ref in matched_block.text:
                    # Check that ev_ref does NOT overlap unselected text (complete or partial)
                    has_unselected = False
                    for ue in unselected_page_evs:
                        if ue.text_reference and check_text_references_overlap(ev_ref, ue.text_reference, matched_block.text):
                            has_unselected = True
                            break
                    if not has_unselected:
                        resolved_text = ev_ref
                        is_exact_span_resolution = True
                        ev_meta = ev.metadata if isinstance(getattr(ev, 'metadata', None), dict) else (getattr(ev, 'metadata_json', None) or {})
                        has_persisted_offsets = any(k in ev_meta for k in ("start_offset", "char_start", "char_offset_start", "source_span"))
                        if has_persisted_offsets:
                            diag = f"MIXED_BLOCK_ISOLATED: Extracted persisted source span for evidence '{ev.id}' from mixed block '{matched_block.id}' on page {page_num}."
                        else:
                            diag = f"MIXED_BLOCK_ISOLATED: Extracted verified text reference for evidence '{ev.id}' from mixed block '{matched_block.id}' on page {page_num}."
                        self.diagnostics.append(diag)
                    else:
                        diag = f"MIXED_BLOCK_EXCLUDED: Block '{matched_block.id}' on page {page_num} contains unselected content overlapping evidence text_reference. Excluded."
                        self.diagnostics.append(diag)
                        self.excluded_evidence_ids.add(ev.id)
                        continue
                else:
                    diag = f"MIXED_BLOCK_EXCLUDED: Block '{matched_block.id}' on page {page_num} contains mixed selected and unselected content without a verified span boundary. Excluded."
                    self.diagnostics.append(diag)
                    self.excluded_evidence_ids.add(ev.id)
                    continue
            else:
                if not is_exact_span_resolution:
                    resolved_text = matched_block.text

            # Surrounding context: Only resolve if block is not mixed and not exact span
            previous_text = None
            next_text = None
            if not is_mixed_block and not is_exact_span_resolution:
                if matched_block.previous_block_id:
                    prev_block = self.doc_repo.get_block(matched_block.previous_block_id)
                    if prev_block and prev_block.document_id == ev.document_id and prev_block.page_number == page_num:
                        prev_is_unselected = False
                        if is_scoped and unselected_page_evs:
                            for ue in unselected_page_evs:
                                if ue.text_reference and ue.text_reference.strip() in prev_block.text:
                                    prev_is_unselected = True
                                    break
                        if not prev_is_unselected:
                            previous_text = prev_block.text

                if matched_block.next_block_id:
                    next_block = self.doc_repo.get_block(matched_block.next_block_id)
                    if next_block and next_block.document_id == ev.document_id and next_block.page_number == page_num:
                        next_is_unselected = False
                        if is_scoped and unselected_page_evs:
                            for ue in unselected_page_evs:
                                if ue.text_reference and ue.text_reference.strip() in next_block.text:
                                    next_is_unselected = True
                                    break
                        if not next_is_unselected:
                            next_text = next_block.text

            block_id = matched_block.id
            passage_key = f"{block_id}_{ev.id}" if is_exact_span_resolution else block_id

            if passage_key in passages_map:
                if cand.entity_id not in passages_map[passage_key].entity_ids:
                    passages_map[passage_key].entity_ids.append(cand.entity_id)
            else:
                passages_map[passage_key] = PassageCandidate(
                    document_id=ev.document_id,
                    block_id=block_id,
                    page_number=page_num,
                    text=resolved_text,
                    block_type=matched_block.block_type,
                    x0=matched_block.x0,
                    y0=matched_block.y0,
                    x1=matched_block.x1,
                    y1=matched_block.y1,
                    section_title=ev.section_title,
                    entity_ids=[cand.entity_id],
                    previous_text=previous_text,
                    next_text=next_text,
                    diagnostics=[]
                )

        return list(passages_map.values())

