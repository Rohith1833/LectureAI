import asyncio
import json
import os
import re
import threading
import uuid
from typing import Any, Dict, Optional

import pptx
from fastapi import BackgroundTasks, HTTPException, status
from loguru import logger

from app.agents.ocr_agent import OCRAgent
from app.core.config import settings
from app.core.storage import METADATA_DIR, STORAGE_ROOT, UPLOADS_DIR
from app.schemas.presentation import (
    PresentationDeck,
    PresentationJobStage,
    PresentationJobStatus,
)
from app.services import pdf_extractor
from app.services.generation.groq_provider import GroqProvider
from app.services.generation.mock_provider import MockLLMProvider
from app.services.normalization.base import ImmutableMetadata, NormalizationContext
from app.services.normalization.pipeline import NormalizationPipeline
from app.services.ocr.page_detector import OCRStrategy
from app.services.pptx_designer import PPTXDesigner
from app.services.presentation_engine import PresentationEngine
from app.utils.timestamps import utc_now

PRESENTATION_JOBS_DIR = os.path.join(STORAGE_ROOT, "presentations")
PRESENTATION_FILES_DIR = os.path.join(STORAGE_ROOT, "pptx_outputs")
os.makedirs(PRESENTATION_JOBS_DIR, exist_ok=True)
os.makedirs(PRESENTATION_FILES_DIR, exist_ok=True)

_JOB_FILE_LOCK = threading.Lock()

STAGE_LABELS = {
    PresentationJobStage.UPLOADING: "Uploading document",
    PresentationJobStage.ANALYZING_PDF: "Analysing PDF",
    PresentationJobStage.EXTRACTING_CONTENT: "Extracting textbook content",
    PresentationJobStage.UNDERSTANDING_MATERIAL: "Understanding educational material",
    PresentationJobStage.PLANNING_PRESENTATION: "Planning presentation",
    PresentationJobStage.VALIDATING_CONTENT: "Validating content accuracy",
    PresentationJobStage.DESIGNING_SLIDES: "Designing slides",
    PresentationJobStage.GENERATING_PPTX: "Generating PowerPoint",
    PresentationJobStage.COMPLETED: "Presentation ready",
    PresentationJobStage.FAILED: "Generation failed",
}


def _job_path(job_id: str) -> str:
    return os.path.join(PRESENTATION_JOBS_DIR, f"{job_id}.json")


def _read_job(job_id: str) -> Dict[str, Any]:
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid presentation job ID.")
    path = _job_path(job_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Presentation job not found.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_job(job_id: str, data: Dict[str, Any]) -> None:
    path = _job_path(job_id)
    tmp = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _update_stage(
    job_id: str,
    stage: PresentationJobStage,
    progress: int,
    detail: str = "",
    status_val: str = "processing",
    error: Optional[str] = None,
    notice: Optional[str] = None,
    deck: Optional[PresentationDeck] = None,
    pptx_path: Optional[str] = None,
) -> Dict[str, Any]:
    with _JOB_FILE_LOCK:
        data = _read_job(job_id)
        data["status"] = status_val
        data["stage"] = stage.value
        data["stage_label"] = STAGE_LABELS.get(stage, stage.value)
        data["progress"] = progress
        data["detail"] = detail
        data["updated_at"] = utc_now()
        if error is not None:
            data["error"] = error
        if notice is not None:
            data["notice"] = notice
        if deck is not None:
            data["deck"] = deck.model_dump()
        if pptx_path is not None:
            data["pptx_path"] = pptx_path
            data["download_url"] = f"/api/{settings.API_VERSION}/presentations/{job_id}/download"
        _write_job(job_id, data)
        return data


def _get_llm_provider():
    provider_name = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if provider_name in ("mock", "test"):
        return MockLLMProvider(scenario="success")
    if not settings.GROQ_API_KEY or not settings.GROQ_API_KEY.strip():
        raise ValueError(
            "AI service is not configured. Please set GROQ_API_KEY in the backend environment."
        )
    return GroqProvider(api_key=settings.GROQ_API_KEY, timeout=90.0)


def create_presentation_job(
    upload_id: str,
    background_tasks: BackgroundTasks,
    target_slide_count: Optional[int] = None,
) -> PresentationJobStatus:
    metadata_file = os.path.join(METADATA_DIR, f"{upload_id}.json")
    if not os.path.exists(metadata_file):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Uploaded PDF not found. Please upload your textbook again.",
        )

    with open(metadata_file, "r", encoding="utf-8") as f:
        meta = json.load(f)

    job_id = str(uuid.uuid4())
    now = utc_now()
    filename = meta.get("original_filename", "textbook.pdf")

    job_data: Dict[str, Any] = {
        "job_id": job_id,
        "upload_id": upload_id,
        "filename": filename,
        "target_slide_count": target_slide_count,
        "status": "queued",
        "stage": PresentationJobStage.ANALYZING_PDF.value,
        "stage_label": STAGE_LABELS[PresentationJobStage.ANALYZING_PDF],
        "progress": 5,
        "detail": "Queued for processing...",
        "error": None,
        "notice": None,
        "deck": None,
        "pptx_path": None,
        "download_url": None,
        "created_at": now,
        "updated_at": now,
    }
    _write_job(job_id, job_data)
    background_tasks.add_task(run_presentation_pipeline, job_id, upload_id, target_slide_count)
    return PresentationJobStatus.model_validate(job_data)


def get_presentation_job(job_id: str) -> PresentationJobStatus:
    with _JOB_FILE_LOCK:
        data = _read_job(job_id)
    return PresentationJobStatus.model_validate(data)


def get_presentation_file_info(job_id: str) -> tuple[str, str]:
    with _JOB_FILE_LOCK:
        data = _read_job(job_id)
    if data.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Presentation is not ready for download yet.")
    pptx_path = data.get("pptx_path")
    if not pptx_path or not os.path.exists(pptx_path):
        raise HTTPException(status_code=404, detail="Generated PowerPoint file not found.")

    base = re.sub(r"\.pdf$", "", data.get("filename", "presentation"), flags=re.IGNORECASE)
    safe_base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("_") or "presentation"
    return pptx_path, f"{safe_base}_slides.pptx"


async def run_presentation_pipeline(
    job_id: str,
    upload_id: str,
    target_slide_count: Optional[int] = None,
) -> None:
    """End-to-end textbook PDF -> parallel OCR/extraction -> AI planning -> validation -> PPTX."""
    logger.info(
        "Starting presentation pipeline for job {} (upload {}, target_slides={})",
        job_id,
        upload_id,
        target_slide_count,
    )
    out_pptx_path = os.path.join(PRESENTATION_FILES_DIR, f"{job_id}.pptx")

    try:
        metadata_file = os.path.join(METADATA_DIR, f"{upload_id}.json")
        with open(metadata_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
        file_path = os.path.join(UPLOADS_DIR, meta["stored_filename"])
        original_filename = meta.get("original_filename", "textbook.pdf")

        # 1. Analysing PDF
        _update_stage(
            job_id,
            PresentationJobStage.ANALYZING_PDF,
            10,
            "Inspecting PDF pages and detecting selectable text vs. scanned pages...",
        )
        extraction_result = await asyncio.to_thread(
            pdf_extractor.extract_pdf_document, upload_id, file_path
        )
        total_pages = extraction_result.metadata.page_count

        # 2. Extracting Textbook Content (Digital + parallel OCR where needed)
        _update_stage(
            job_id,
            PresentationJobStage.EXTRACTING_CONTENT,
            18,
            f"Extracting text and tables across {total_pages} page(s)...",
        )

        def on_ocr_page(completed_pages: int, total: int, mode: str):
            pct = 18 + int((completed_pages / max(1, total)) * 34)
            label = "Processed scanned page" if mode == "ocr" else "Extracted digital page"
            _update_stage(
                job_id,
                PresentationJobStage.EXTRACTING_CONTENT,
                pct,
                f"{label} ({completed_pages} of {total} pages complete)...",
            )

        ocr_agent = OCRAgent()
        extraction_result = await asyncio.to_thread(
            ocr_agent.process_document,
            extraction_result,
            file_path,
            OCRStrategy.AUTO,
            on_ocr_page,
        )

        # Deterministic normalization (whitespace, hyphenation, reading order, headers/footers)
        norm_pipeline = NormalizationPipeline.create_default_pipeline()
        norm_meta = ImmutableMetadata(upload_id=upload_id)
        norm_context = NormalizationContext(norm_meta, debug_mode=settings.DEBUG)
        extraction_result, _ = await asyncio.to_thread(
            norm_pipeline.execute, extraction_result, norm_context
        )

        # 3-6. AI Content Reconstruction, Planning, Validation & Slide Design
        def on_ai_progress(stage_str: str, pct: int, detail: str):
            stage_enum = PresentationJobStage(stage_str)
            _update_stage(job_id, stage_enum, pct, detail)

        llm_provider = _get_llm_provider()
        engine = PresentationEngine(llm_provider)
        deck = await engine.generate_deck(
            extraction_result,
            source_filename=original_filename,
            target_slide_count=target_slide_count,
            on_progress=on_ai_progress,
        )

        # 7. Generating PowerPoint (.pptx)
        _update_stage(
            job_id,
            PresentationJobStage.GENERATING_PPTX,
            93,
            f"Building {len(deck.slides)} editable PowerPoint slides...",
        )
        designer = PPTXDesigner()
        await asyncio.to_thread(designer.render, deck, out_pptx_path)

        # Verify PPTX integrity
        if not os.path.exists(out_pptx_path) or os.path.getsize(out_pptx_path) == 0:
            raise ValueError("Generated PowerPoint file is empty.")
        prs_check = await asyncio.to_thread(pptx.Presentation, out_pptx_path)
        if len(prs_check.slides) == 0:
            raise ValueError("Generated PowerPoint contains zero slides.")

        # 8. Completed
        _update_stage(
            job_id,
            PresentationJobStage.COMPLETED,
            100,
            f"Generated {len(deck.slides)} slides from {total_pages} textbook page(s).",
            status_val="completed",
            notice=deck.notice,
            deck=deck,
            pptx_path=out_pptx_path,
        )
        logger.info("Presentation pipeline completed for job {} ({} slides)", job_id, len(deck.slides))

    except Exception as e:
        logger.error("Presentation pipeline failed for job {}: {}", job_id, str(e))
        if os.path.exists(out_pptx_path):
            try:
                os.remove(out_pptx_path)
            except Exception:
                pass
        try:
            _update_stage(
                job_id,
                PresentationJobStage.FAILED,
                0,
                "Processing failed.",
                status_val="failed",
                error=str(e),
            )
        except Exception as inner:
            logger.error("Failed to persist failure state for {}: {}", job_id, str(inner))
