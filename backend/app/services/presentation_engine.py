import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from loguru import logger

from app.schemas.document import BlockType, DocumentExtractionResult
from app.schemas.presentation import (
    BulletItem,
    PresentationDeck,
    ProcessStep,
    SlideLayoutType,
    SlideSpec,
    ValidationReport,
)
from app.services.generation.base import LLMGenerationRequest, LLMProvider


MAX_CHUNK_CHARS = 15500
MIN_ALNUM_CHARS_REQUIRED = 30
MAX_CONCURRENT_LLM_CALLS = 2


@dataclass
class ReconstructedSection:
    title: str
    page_start: int
    page_end: int
    paragraphs: List[str] = field(default_factory=list)
    tables: List[str] = field(default_factory=list)

    def to_context_text(self) -> str:
        parts = [f"### {self.title} (Pages {self.page_start}-{self.page_end})"]
        for p in self.paragraphs:
            parts.append(p)
        for t in self.tables:
            parts.append(f"[Table]\n{t}")
        return "\n\n".join(parts)

    @property
    def char_count(self) -> int:
        return sum(len(p) for p in self.paragraphs) + sum(len(t) for t in self.tables) + len(self.title)


SLIDE_PLAN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "deck_title": {"type": "string"},
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "layout": {
                        "type": "string",
                        "enum": [
                            "section",
                            "concept",
                            "two_column",
                            "process",
                            "table",
                            "example",
                            "summary",
                        ],
                    },
                    "title": {"type": "string"},
                    "subtitle": {"type": "string"},
                    "key_definition": {"type": "string"},
                    "bullets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "heading": {"type": "string"},
                                "detail": {"type": "string"},
                            },
                            "required": ["heading", "detail"],
                            "additionalProperties": False,
                        },
                    },
                    "left_title": {"type": "string"},
                    "left_items": {"type": "array", "items": {"type": "string"}},
                    "right_title": {"type": "string"},
                    "right_items": {"type": "array", "items": {"type": "string"}},
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step_title": {"type": "string"},
                                "description": {"type": "string"},
                            },
                            "required": ["step_title", "description"],
                            "additionalProperties": False,
                        },
                    },
                    "headers": {"type": "array", "items": {"type": "string"}},
                    "rows": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                    "scenario": {"type": "string"},
                    "walkthrough": {"type": "array", "items": {"type": "string"}},
                    "takeaway": {"type": "string"},
                    "speaker_notes": {"type": "string"},
                    "content_origin": {
                        "type": "string",
                        "enum": ["textbook", "textbook_with_explanation"],
                    },
                },
                "required": ["layout", "title", "speaker_notes", "content_origin"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["deck_title", "slides"],
    "additionalProperties": False,
}


DISTILL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "section_summary": {"type": "string"},
    },
    "required": ["section_summary"],
    "additionalProperties": False,
}


VALIDATION_AUDIT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "overall_status": {"type": "string", "enum": ["passed", "corrected"]},
        "issues_found": {"type": "array", "items": {"type": "string"}},
        "missing_concepts": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
        "slide_reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slide_index": {"type": "integer"},
                    "action": {"type": "string", "enum": ["keep", "fix", "remove"]},
                    "content_origin": {
                        "type": "string",
                        "enum": ["textbook", "textbook_with_explanation", "synthesized_summary"],
                    },
                    "reason": {"type": "string"},
                    "fixed_title": {"type": "string"},
                    "fixed_key_definition": {"type": "string"},
                    "fixed_bullets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "heading": {"type": "string"},
                                "detail": {"type": "string"},
                            },
                            "required": ["heading", "detail"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["slide_index", "action", "content_origin"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["overall_status", "issues_found", "missing_concepts", "summary", "slide_reviews"],
    "additionalProperties": False,
}


def reconstruct_educational_sections(
    extraction: DocumentExtractionResult,
) -> Tuple[List[ReconstructedSection], Dict[str, Any]]:
    """Convert extracted blocks and tables into clean, ordered educational sections."""
    ordered_blocks = sorted(
        extraction.blocks,
        key=lambda b: (b.page_number, b.reading_order),
    )

    total_alnum = 0
    digital_pages = set()
    ocr_pages = set()
    table_count = 0

    for b in ordered_blocks:
        if b.block_type in (BlockType.HEADER, BlockType.FOOTER):
            continue
        text = (b.text or "").strip()
        if not text:
            continue
        total_alnum += sum(1 for c in text if c.isalnum())
        if b.provenance == "OCR":
            ocr_pages.add(b.page_number)
        else:
            digital_pages.add(b.page_number)

    if total_alnum < MIN_ALNUM_CHARS_REQUIRED:
        raise ValueError(
            "No readable educational text could be extracted from this PDF. "
            "If this is a scanned document, please check that the pages are legible and not blank."
        )

    sections: List[ReconstructedSection] = []
    current_section: Optional[ReconstructedSection] = None

    chapter_pattern = re.compile(
        r"^(chapter|unit|module|section|part|lesson)\s+[\divx]+", re.IGNORECASE
    )

    for b in ordered_blocks:
        if b.block_type in (BlockType.HEADER, BlockType.FOOTER):
            continue

        text = (b.text or "").strip()
        if not text:
            continue

        is_major_heading = False
        if b.block_type == BlockType.HEADING:
            if (b.heading_level is not None and b.heading_level <= 2) or chapter_pattern.match(text):
                is_major_heading = True
        elif chapter_pattern.match(text) and len(text) < 120:
            is_major_heading = True

        if is_major_heading:
            if current_section and (current_section.paragraphs or current_section.tables):
                sections.append(current_section)
            current_section = ReconstructedSection(
                title=re.sub(r"\s+", " ", text)[:140],
                page_start=b.page_number,
                page_end=b.page_number,
            )
            continue

        if current_section is None:
            current_section = ReconstructedSection(
                title=f"Pages {b.page_number}",
                page_start=b.page_number,
                page_end=b.page_number,
            )

        current_section.page_end = max(current_section.page_end, b.page_number)

        if b.block_type == BlockType.TABLE:
            table_count += 1
            current_section.tables.append(text)
        elif b.block_type == BlockType.HEADING:
            current_section.paragraphs.append(f"**{re.sub(r'\\s+', ' ', text)}**")
        else:
            current_section.paragraphs.append(text)

    if current_section and (current_section.paragraphs or current_section.tables):
        sections.append(current_section)

    balanced_sections: List[ReconstructedSection] = []
    for sec in sections:
        if sec.char_count <= MAX_CHUNK_CHARS:
            balanced_sections.append(sec)
        else:
            part_idx = 1
            curr_paras: List[str] = []
            curr_len = 0
            for p in sec.paragraphs:
                if curr_len + len(p) > MAX_CHUNK_CHARS and curr_paras:
                    balanced_sections.append(
                        ReconstructedSection(
                            title=f"{sec.title} (Part {part_idx})",
                            page_start=sec.page_start,
                            page_end=sec.page_end,
                            paragraphs=curr_paras,
                            tables=sec.tables if part_idx == 1 else [],
                        )
                    )
                    part_idx += 1
                    curr_paras = []
                    curr_len = 0
                curr_paras.append(p)
                curr_len += len(p)
            if curr_paras or (part_idx == 1 and sec.tables):
                balanced_sections.append(
                    ReconstructedSection(
                        title=f"{sec.title} (Part {part_idx})" if part_idx > 1 else sec.title,
                        page_start=sec.page_start,
                        page_end=sec.page_end,
                        paragraphs=curr_paras,
                        tables=sec.tables if part_idx == 1 else [],
                    )
                )

    total_words = sum(
        len(p.split()) for s in balanced_sections for p in s.paragraphs
    )
    stats = {
        "total_pages": extraction.metadata.page_count,
        "digital_pages": len(digital_pages - ocr_pages),
        "ocr_pages": len(ocr_pages),
        "total_words": total_words,
        "section_count": len(balanced_sections),
        "table_count": table_count,
    }
    return balanced_sections, stats


def _pack_sections_into_chunks(sections: List[ReconstructedSection]) -> List[str]:
    """Pack reconstructed sections into LLM-sized context chunks."""
    chunks: List[str] = []
    current_parts: List[str] = []
    current_len = 0

    for sec in sections:
        sec_text = sec.to_context_text()
        if current_len + len(sec_text) > MAX_CHUNK_CHARS and current_parts:
            chunks.append("\n\n---\n\n".join(current_parts))
            current_parts = []
            current_len = 0
        current_parts.append(sec_text)
        current_len += len(sec_text)

    if current_parts:
        chunks.append("\n\n---\n\n".join(current_parts))
    return chunks


def _allocate_chunk_budgets(chunks: List[str], body_target: int) -> List[int]:
    """Allocate integer slide budgets across chunks proportionally to text length without truncation."""
    n = len(chunks)
    if n == 0:
        return []
    lengths = [max(1, len(c)) for c in chunks]
    total_len = sum(lengths)
    raw = [max(1, round(body_target * (ln / total_len))) for ln in lengths]

    # Adjust proportionally so sum(raw) == body_target
    while sum(raw) > body_target:
        # Reduce from the chunk with largest budget > 1
        candidates = [(i, raw[i]) for i in range(n) if raw[i] > 1]
        if not candidates:
            break
        idx_max = max(candidates, key=lambda x: x[1])[0]
        raw[idx_max] -= 1

    while sum(raw) < body_target:
        idx_max = max(range(n), key=lambda i: lengths[i] / raw[i])
        raw[idx_max] += 1

    return raw


def _slide_text_tokens(slide: SlideSpec) -> set[str]:
    parts = [slide.title, slide.subtitle, slide.key_definition, slide.scenario, slide.takeaway]
    parts.extend(f"{b.heading} {b.detail}" for b in slide.bullets)
    parts.extend(slide.left_items)
    parts.extend(slide.right_items)
    parts.extend(f"{s.step_title} {s.description}" for s in slide.steps)
    parts.extend(slide.walkthrough)
    text = " ".join(parts).lower()
    return set(re.findall(r"[a-z0-9]{3,}", text))


def _deduplicate_slides(slides: List[SlideSpec]) -> Tuple[List[SlideSpec], List[str]]:
    """Deterministically remove repeated or near-duplicate slides."""
    kept: List[SlideSpec] = []
    removed_notes: List[str] = []
    seen_titles: set[str] = set()
    kept_tokens: List[set[str]] = []

    for s in slides:
        norm_title = re.sub(r"\s+", " ", s.title.strip().lower())
        tokens = _slide_text_tokens(s)

        if s.layout != SlideLayoutType.SECTION and norm_title in seen_titles:
            removed_notes.append(f"Removed duplicate slide '{s.title}'.")
            continue

        is_dup = False
        if s.layout != SlideLayoutType.SECTION and len(tokens) >= 6:
            for prev_toks in kept_tokens:
                union = len(tokens | prev_toks)
                if union > 0 and (len(tokens & prev_toks) / union) >= 0.85:
                    is_dup = True
                    break
        if is_dup:
            removed_notes.append(f"Removed near-duplicate slide '{s.title}'.")
            continue

        seen_titles.add(norm_title)
        kept_tokens.append(tokens)
        kept.append(s)

    return kept, removed_notes


def _validate_and_refine_slides(
    raw_slides: List[Dict[str, Any]],
    allow_split: bool = True,
) -> List[SlideSpec]:
    """Validate AI-generated slides, split dense slides if allowed, and drop empty/trivial ones."""
    refined: List[SlideSpec] = []

    for item in raw_slides:
        try:
            spec = SlideSpec.model_validate(item)
        except Exception as e:
            logger.warning("Skipping malformed slide spec: {}", str(e))
            continue

        title = (spec.title or "").strip()
        if not title:
            continue

        if spec.layout == SlideLayoutType.SECTION:
            refined.append(spec)
            continue

        if spec.layout == SlideLayoutType.CONCEPT:
            valid_bullets = [
                b for b in spec.bullets
                if b.heading.strip() and b.detail.strip() and len(b.detail.strip()) >= 8
            ]
            if not valid_bullets and not spec.key_definition.strip():
                continue
            if allow_split and len(valid_bullets) > 5:
                for idx in range(0, len(valid_bullets), 4):
                    chunk_b = valid_bullets[idx : idx + 4]
                    part_num = (idx // 4) + 1
                    refined.append(
                        SlideSpec(
                            layout=SlideLayoutType.CONCEPT,
                            title=f"{title}" if part_num == 1 else f"{title} (Continued)",
                            subtitle=spec.subtitle,
                            key_definition=spec.key_definition if part_num == 1 else "",
                            bullets=chunk_b,
                            speaker_notes=spec.speaker_notes,
                            content_origin=spec.content_origin,
                        )
                    )
            else:
                spec.bullets = valid_bullets[:5]
                refined.append(spec)

        elif spec.layout == SlideLayoutType.TWO_COLUMN:
            left = [x.strip() for x in spec.left_items if x and x.strip()]
            right = [x.strip() for x in spec.right_items if x and x.strip()]
            if not left and not right:
                continue
            spec.left_items = left[:6]
            spec.right_items = right[:6]
            refined.append(spec)

        elif spec.layout == SlideLayoutType.PROCESS:
            valid_steps = [
                s for s in spec.steps if s.step_title.strip() and s.description.strip()
            ]
            if len(valid_steps) < 2:
                continue
            spec.steps = valid_steps[:6]
            refined.append(spec)

        elif spec.layout == SlideLayoutType.TABLE:
            if not spec.headers or not spec.rows:
                continue
            num_cols = len(spec.headers)
            norm_rows = []
            for r in spec.rows[:8]:
                padded = (list(r) + [""] * num_cols)[:num_cols]
                if any(c.strip() for c in padded):
                    norm_rows.append(padded)
            if not norm_rows:
                continue
            spec.rows = norm_rows
            refined.append(spec)

        elif spec.layout == SlideLayoutType.EXAMPLE:
            walk = [w.strip() for w in spec.walkthrough if w and w.strip()]
            if not spec.scenario.strip() and not walk:
                continue
            spec.walkthrough = walk[:6]
            refined.append(spec)

        elif spec.layout == SlideLayoutType.SUMMARY:
            valid_bullets = [
                b for b in spec.bullets if b.heading.strip() and b.detail.strip()
            ]
            if not valid_bullets:
                continue
            spec.bullets = valid_bullets[:6]
            refined.append(spec)

    return refined


def _consolidate_to_target(slides: List[SlideSpec], body_target: int) -> List[SlideSpec]:
    """Reduce excess body slides to meet body_target without dropping major concepts or chapters."""
    result = list(slides)

    # 1. Drop redundant standalone section divider slides first if over budget
    while len(result) > body_target:
        sec_indices = [i for i, s in enumerate(result) if s.layout == SlideLayoutType.SECTION]
        if not sec_indices:
            break
        result.pop(sec_indices[-1])

    # 2. Merge adjacent short concept slides if still over budget
    while len(result) > body_target and len(result) >= 2:
        merged = False
        for i in range(len(result) - 1):
            a, b = result[i], result[i + 1]
            if (
                a.layout == SlideLayoutType.CONCEPT
                and b.layout == SlideLayoutType.CONCEPT
                and len(a.bullets) + len(b.bullets) <= 5
            ):
                a.bullets.extend(b.bullets)
                if b.key_definition and not a.key_definition:
                    a.key_definition = b.key_definition
                if b.speaker_notes:
                    a.speaker_notes = f"{a.speaker_notes} {b.speaker_notes}".strip()
                result.pop(i + 1)
                merged = True
                break
        if not merged:
            break

    # 3. If still over budget, fold the shortest non-section slide's notes into its neighbor
    while len(result) > body_target and len(result) > 1:
        candidates = [
            (i, len(_slide_text_tokens(s)))
            for i, s in enumerate(result)
            if s.layout != SlideLayoutType.SUMMARY
        ]
        if not candidates:
            break
        drop_idx = min(candidates, key=lambda x: x[1])[0]
        dropped = result.pop(drop_idx)
        neighbor_idx = max(0, drop_idx - 1)
        if result[neighbor_idx].speaker_notes:
            result[neighbor_idx].speaker_notes += f" Also note ({dropped.title}): {dropped.speaker_notes}"

    return result


class PresentationEngine:
    """AI Educational Content Reconstruction, Slide Planning & Validation Engine."""

    def __init__(self, llm_provider: LLMProvider):
        self.llm_provider = llm_provider

    async def _distill_chunks_concurrently(
        self,
        chunks: List[str],
        semaphore: asyncio.Semaphore,
    ) -> List[str]:
        """Distill each chunk into a dense educational summary when compressing large books into small decks."""
        system_msg = (
            "You are an academic summarizer. Condense the provided textbook excerpt into a crisp, "
            "fact-preserving digest (150-250 words) capturing all chapter/section titles, key definitions, "
            "core concepts, important names/locations/dates, worked examples, and table takeaways."
        )

        async def _distill_one(idx: int, text: str) -> Tuple[int, str]:
            async with semaphore:
                req = LLMGenerationRequest(
                    prompt=f"Distill excerpt {idx + 1} without inventing facts:\n\n{text}",
                    system_instruction=system_msg,
                    temperature=0.1,
                    json_schema=DISTILL_SCHEMA,
                )
                res = await self.llm_provider.generate(req)
                summary = (res.structured_output or {}).get("section_summary", "").strip()
                return idx, summary or text[:1500]

        results = await asyncio.gather(*[_distill_one(i, c) for i, c in enumerate(chunks)])
        results.sort(key=lambda x: x[0])
        return [r[1] for r in results]

    async def _validate_deck_content(
        self,
        slides: List[SlideSpec],
        sections: List[ReconstructedSection],
    ) -> Tuple[List[SlideSpec], ValidationReport]:
        """Run deterministic + AI content validation before PPTX generation."""
        checks_run = [
            "Duplicate slide detection",
            "Chapter order & coverage check",
            "Factual grounding, names & locations audit",
            "Heading accuracy & unsupported claim check",
            "Textbook vs. explanatory addition tagging",
        ]

        # 1. Deterministic deduplication
        deduped_slides, dup_notes = _deduplicate_slides(slides)
        issues_found: List[str] = list(dup_notes)
        corrections_applied: List[str] = list(dup_notes)

        # Build compact source digest (bounded to fit safely within TPM limits)
        source_digest_parts = []
        budget_chars = 6500
        per_sec_budget = max(250, budget_chars // max(1, len(sections)))
        for sec in sections:
            body_preview = " ".join(sec.paragraphs)[:per_sec_budget]
            tbl_preview = (" | Tables: " + " ; ".join(sec.tables)[:200]) if sec.tables else ""
            source_digest_parts.append(
                f"## {sec.title} (pp.{sec.page_start}-{sec.page_end})\n{body_preview}{tbl_preview}"
            )
        source_digest = "\n\n".join(source_digest_parts)[:7000]

        # Compact representation of generated slides (excluding TITLE slide 0)
        compact_slides = []
        for idx, s in enumerate(deduped_slides):
            compact_slides.append(
                {
                    "slide_index": idx,
                    "layout": s.layout.value,
                    "title": s.title,
                    "key_definition": s.key_definition,
                    "bullets": [b.model_dump() for b in s.bullets],
                    "scenario": s.scenario,
                    "takeaway": s.takeaway,
                    "steps": [st.model_dump() for st in s.steps],
                    "left_title": s.left_title,
                    "left_items": s.left_items,
                    "right_title": s.right_title,
                    "right_items": s.right_items,
                    "content_origin": s.content_origin,
                }
            )

        audit_system = (
            "You are a strict academic fact-checker and curriculum auditor.\n"
            "Compare the generated presentation slides against the textbook source digest.\n"
            "Verify every slide for:\n"
            "1. Contradictory facts against the textbook.\n"
            "2. Incorrect locations, dates, formulas, numbers, or character/person names.\n"
            "3. Repeated or redundant slides.\n"
            "4. Unsupported claims presented as textbook facts (do NOT allow invented information).\n"
            "5. Missing important concepts or inconsistent chapter organization.\n"
            "6. Incorrect or misleading slide headings.\n"
            "7. Distinguish pure textbook content ('textbook') from slides that include clarifying pedagogical "
            "explanations consistent with the textbook ('textbook_with_explanation').\n\n"
            "For any slide with errors, set action='fix' and provide corrected fields (fixed_title, "
            "fixed_key_definition, fixed_bullets). For completely redundant/unsupported slides, set action='remove'. "
            "If accurate, set action='keep'."
        )
        audit_prompt = (
            f"<textbook_digest>\n{source_digest}\n</textbook_digest>\n\n"
            f"<generated_slides>\n{json.dumps(compact_slides, ensure_ascii=False)}\n</generated_slides>"
        )

        try:
            req = LLMGenerationRequest(
                prompt=audit_prompt,
                system_instruction=audit_system,
                temperature=0.0,
                json_schema=VALIDATION_AUDIT_SCHEMA,
            )
            res = await self.llm_provider.generate(req)
            audit = res.structured_output or {}

            for iss in audit.get("issues_found", []):
                if iss and iss not in issues_found:
                    issues_found.append(iss)
            for mc in audit.get("missing_concepts", []):
                if mc:
                    issues_found.append(f"Coverage note: {mc}")

            reviews_by_idx = {
                r["slide_index"]: r
                for r in audit.get("slide_reviews", [])
                if isinstance(r, dict) and "slide_index" in r
            }

            validated_slides: List[SlideSpec] = []
            for idx, slide in enumerate(deduped_slides):
                rev = reviews_by_idx.get(idx)
                if not rev:
                    validated_slides.append(slide)
                    continue

                origin = rev.get("content_origin")
                if origin in ("textbook", "textbook_with_explanation", "synthesized_summary"):
                    slide.content_origin = origin

                action = rev.get("action", "keep")
                if action == "remove" and slide.layout != SlideLayoutType.TITLE:
                    reason = rev.get("reason") or "Flagged as redundant or unsupported during validation."
                    corrections_applied.append(f"Removed slide '{slide.title}': {reason}")
                    continue

                if action == "fix":
                    if rev.get("fixed_title"):
                        slide.title = rev["fixed_title"].strip()
                    if rev.get("fixed_key_definition") is not None and rev.get("fixed_key_definition"):
                        slide.key_definition = rev["fixed_key_definition"].strip()
                    if rev.get("fixed_bullets"):
                        fixed_b = [
                            BulletItem(heading=b["heading"], detail=b["detail"])
                            for b in rev["fixed_bullets"]
                            if b.get("heading") and b.get("detail")
                        ]
                        if fixed_b:
                            slide.bullets = fixed_b[:5]
                    reason = rev.get("reason") or "Corrected heading or factual grounding."
                    corrections_applied.append(f"Updated slide '{slide.title}': {reason}")

                validated_slides.append(slide)

            summary = audit.get("summary") or (
                f"Validated {len(validated_slides)} slides against textbook content."
            )
            report = ValidationReport(
                status="corrected" if corrections_applied else "passed",
                checks_run=checks_run,
                issues_found=issues_found,
                corrections_applied=corrections_applied,
                summary=summary,
            )
            return validated_slides or deduped_slides, report

        except Exception as val_err:
            logger.warning("AI validation audit failed ({}), using deterministic validation only.", str(val_err))
            report = ValidationReport(
                status="corrected" if corrections_applied else "passed",
                checks_run=checks_run[:2],
                issues_found=issues_found,
                corrections_applied=corrections_applied,
                summary=f"Completed structural & duplicate validation across {len(deduped_slides)} slides.",
            )
            return deduped_slides, report

    async def generate_deck(
        self,
        extraction: DocumentExtractionResult,
        source_filename: str,
        target_slide_count: Optional[int] = None,
        on_progress: Optional[Callable[[str, int, str], None]] = None,
    ) -> PresentationDeck:
        """Reconstruct textbook content, plan slides (Auto or target count), validate, and return deck."""
        if on_progress:
            on_progress("understanding_material", 56, "Organizing textbook chapters, concepts, and tables...")

        sections, stats = reconstruct_educational_sections(extraction)
        chunks = _pack_sections_into_chunks(sections)
        total_words = stats["total_words"]
        notice: Optional[str] = None

        # Evaluate content capacity when user requests an explicit slide count
        effective_target: Optional[int] = target_slide_count
        if target_slide_count is not None:
            max_supportable = max(4, 2 + (total_words // 16) + (stats["section_count"] * 2))
            if target_slide_count > max_supportable:
                effective_target = max_supportable
                notice = (
                    f"You requested {target_slide_count} slides, but the source document contains "
                    f"~{total_words} words across {stats['section_count']} section(s), which supports "
                    f"up to {effective_target} meaningful slides without inventing facts or repeating content."
                )

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)

        # Compress multi-chunk textbook via parallel distillation if requested total is smaller than chunk count,
        # OR expand into section-level chunks if a single chunk has a large slide budget (> 7 body slides)
        planning_chunks = chunks
        if effective_target is not None:
            reserve = 2 if effective_target >= 4 else 1
            body_target = max(1, effective_target - reserve)
            if body_target < len(chunks):
                if on_progress:
                    on_progress(
                        "planning_presentation",
                        60,
                        f"Distilling {len(chunks)} textbook sections to fit {effective_target} slides cleanly...",
                    )
                distilled = await self._distill_chunks_concurrently(chunks, semaphore)
                combined = "\n\n---\n\n".join(
                    f"## Section {i + 1}\n{txt}" for i, txt in enumerate(distilled)
                )
                if len(combined) <= MAX_CHUNK_CHARS * 1.4:
                    planning_chunks = [combined]
                else:
                    mid = len(distilled) // 2
                    planning_chunks = [
                        "\n\n---\n\n".join(distilled[:mid]),
                        "\n\n---\n\n".join(distilled[mid:]),
                    ]
            elif body_target > 7 and len(chunks) < len(sections) and len(sections) >= 2:
                # Split into section-level chunks so each LLM call targets <= ~5-6 slides reliably
                desired_chunks = min(len(sections), max(2, (body_target + 4) // 5))
                if desired_chunks > len(chunks):
                    sec_texts = [s.to_context_text() for s in sections]
                    group_size = max(1, (len(sec_texts) + desired_chunks - 1) // desired_chunks)
                    planning_chunks = [
                        "\n\n---\n\n".join(sec_texts[i : i + group_size])
                        for i in range(0, len(sec_texts), group_size)
                    ]
            chunk_budgets: Optional[List[int]] = _allocate_chunk_budgets(planning_chunks, body_target)
        else:
            chunk_budgets = None

        total_chunks = len(planning_chunks)
        logger.info(
            "Planning deck: {} sections -> {} planning chunks ({} words, target_slides={})",
            len(sections),
            total_chunks,
            total_words,
            effective_target,
        )

        system_instruction = (
            "You are an expert university educator and instructional designer creating a clear, "
            "engaging PowerPoint lecture deck from textbook material.\n\n"
            "STRICT PEDAGOGICAL & GROUNDING RULES:\n"
            "1. Identify core concepts, definitions, mechanisms, examples, names, locations, and tables.\n"
            "2. Every slide MUST teach a complete concept with clear, understandable explanations. "
            "NEVER create heading-only slides, keyword-only slides, or two-word bullet points.\n"
            "3. For 'concept' slides: include a concise 'key_definition' when applicable and 3-5 'bullets', "
            "each with a short 'heading' (2-5 words) and substantive 'detail' (1-2 clear sentences).\n"
            "4. Choose the BEST layout per topic: 'section' (only for major new chapters), 'concept', "
            "'two_column', 'process' (3-6 steps), 'table', 'example', or 'summary'.\n"
            "5. Grounding: stay strictly faithful to the textbook's facts, names, dates, and locations. "
            "NEVER invent information or present unsupported claims as textbook facts. "
            "Tag 'content_origin' as 'textbook' when strictly summarizing textbook facts, or "
            "'textbook_with_explanation' when adding helpful pedagogical clarifications consistent with the source.\n"
            "6. Always include helpful 'speaker_notes' (2-3 sentences) and output ONLY valid JSON."
        )

        completed_chunks = 0

        async def _plan_chunk(idx: int, chunk_text: str) -> Tuple[int, str, List[SlideSpec]]:
            nonlocal completed_chunks
            budget_instruction = ""
            if chunk_budgets is not None:
                b_cnt = chunk_budgets[idx]
                budget_instruction = (
                    f"SLIDE COUNT TARGET FOR THIS CHUNK: Generate EXACTLY {b_cnt} slide(s). "
                    "Distribute all major topics in this excerpt evenly across those slides—do NOT truncate "
                    "later topics and do NOT pad with filler.\n"
                )
            else:
                budget_instruction = (
                    "Generate as many slides as the depth and volume of this excerpt warrant "
                    "(typically 3-6 substantive slides). Do not pad or omit important concepts.\n"
                )

            prompt = (
                f"Textbook filename: {source_filename}\n"
                f"Section chunk {idx + 1} of {total_chunks}.\n"
                f"{budget_instruction}"
                "Transform the following textbook content into structured educational slides:\n\n"
                f"<textbook_content>\n{chunk_text}\n</textbook_content>"
            )

            async with semaphore:
                req = LLMGenerationRequest(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    temperature=0.15,
                    json_schema=SLIDE_PLAN_SCHEMA,
                )
                res = await self.llm_provider.generate(req)

            data = res.structured_output
            if not data or not isinstance(data.get("slides"), list):
                raise ValueError(f"AI returned invalid slide structure for section {idx + 1}.")

            completed_chunks += 1
            if on_progress:
                pct = 62 + int((completed_chunks / max(1, total_chunks)) * 18)
                on_progress(
                    "planning_presentation",
                    pct,
                    f"Planned section {completed_chunks} of {total_chunks}...",
                )

            refined = _validate_and_refine_slides(
                data["slides"],
                allow_split=(effective_target is None),
            )
            title_cand = str(data.get("deck_title") or "").strip()
            return idx, title_cand, refined

        chunk_results = await asyncio.gather(
            *[_plan_chunk(i, txt) for i, txt in enumerate(planning_chunks)]
        )
        chunk_results.sort(key=lambda r: r[0])

        all_slides: List[SlideSpec] = []
        inferred_deck_title = ""
        for _idx, t_cand, c_slides in chunk_results:
            if not inferred_deck_title and t_cand:
                inferred_deck_title = t_cand
            all_slides.extend(c_slides)

        if not all_slides:
            raise ValueError("AI could not generate meaningful educational slides from the extracted text.")

        # Apply target count consolidation before validation if over budget
        if effective_target is not None:
            reserve = 2 if effective_target >= 4 else 1
            body_target = max(1, effective_target - reserve)
            if len(all_slides) > body_target:
                all_slides = _consolidate_to_target(all_slides, body_target)

        # Validation stage (before PPTX generation)
        if on_progress:
            on_progress(
                "validating_content",
                83,
                "Auditing factual accuracy, chapter flow, duplicates, and grounding...",
            )

        validated_body_slides, validation_report = await self._validate_deck_content(
            all_slides, sections
        )

        if on_progress:
            on_progress("designing_slides", 89, "Finalizing slide hierarchy, layouts, and visual flow...")

        clean_filename_title = re.sub(
            r"[_\-]+", " ", re.sub(r"\.pdf$", "", source_filename, flags=re.IGNORECASE)
        ).strip()
        deck_title = inferred_deck_title or clean_filename_title or "Educational Presentation"

        topic_preview = [
            s.title
            for s in validated_body_slides
            if s.layout in (SlideLayoutType.SECTION, SlideLayoutType.CONCEPT)
        ][:4]
        subtitle = " • ".join(topic_preview) if topic_preview else f"Generated from {source_filename}"

        title_slide = SlideSpec(
            layout=SlideLayoutType.TITLE,
            title=deck_title,
            subtitle=subtitle,
            speaker_notes=f"Welcome to this presentation on {deck_title}, covering {len(validated_body_slides)} structured slides.",
            content_origin="synthesized_summary",
        )

        final_slides = [title_slide] + validated_body_slides

        # Include concluding summary slide when Auto or when target >= 4 and room remains
        need_summary = (
            final_slides[-1].layout != SlideLayoutType.SUMMARY
            and len(validated_body_slides) >= 2
            and (effective_target is None or effective_target >= 4)
        )
        if need_summary:
            key_points = [
                BulletItem(
                    heading=s.title[:48],
                    detail=(
                        s.key_definition
                        or (s.bullets[0].detail if s.bullets else "")
                        or s.takeaway
                        or s.subtitle
                        or "Core concept covered in this presentation."
                    ),
                )
                for s in validated_body_slides
                if s.layout in (SlideLayoutType.CONCEPT, SlideLayoutType.PROCESS, SlideLayoutType.EXAMPLE)
            ][:5]
            if key_points:
                summary_slide = SlideSpec(
                    layout=SlideLayoutType.SUMMARY,
                    title="Key Takeaways & Summary",
                    bullets=key_points,
                    speaker_notes="Review these core takeaways to reinforce the main concepts from the textbook.",
                    content_origin="synthesized_summary",
                )
                if effective_target is not None and len(final_slides) >= effective_target:
                    # Ensure adding summary does not exceed effective_target
                    trimmed_body = _consolidate_to_target(
                        validated_body_slides, max(1, effective_target - 2)
                    )
                    final_slides = [title_slide] + trimmed_body + [summary_slide]
                else:
                    final_slides.append(summary_slide)

        if target_slide_count is not None and len(final_slides) < target_slide_count and not notice:
            notice = (
                f"Generated {len(final_slides)} validated slides (target was {target_slide_count}) "
                "to avoid repeating content or inventing facts beyond the source textbook."
            )

        return PresentationDeck(
            title=deck_title,
            subtitle=subtitle,
            slides=final_slides,
            stats={
                **stats,
                "slide_count": len(final_slides),
                "target_slide_count": target_slide_count,
            },
            notice=notice,
            validation_report=validation_report,
        )
