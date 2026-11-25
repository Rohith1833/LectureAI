from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SlideLayoutType(str, Enum):
    TITLE = "title"
    SECTION = "section"
    CONCEPT = "concept"
    TWO_COLUMN = "two_column"
    PROCESS = "process"
    TABLE = "table"
    EXAMPLE = "example"
    SUMMARY = "summary"


class BulletItem(BaseModel):
    heading: str
    detail: str


class ProcessStep(BaseModel):
    step_title: str
    description: str


class SlideSpec(BaseModel):
    layout: SlideLayoutType
    title: str
    subtitle: str = ""
    key_definition: str = ""
    bullets: List[BulletItem] = Field(default_factory=list)
    left_title: str = ""
    left_items: List[str] = Field(default_factory=list)
    right_title: str = ""
    right_items: List[str] = Field(default_factory=list)
    steps: List[ProcessStep] = Field(default_factory=list)
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    scenario: str = ""
    walkthrough: List[str] = Field(default_factory=list)
    takeaway: str = ""
    speaker_notes: str = ""
    content_origin: str = "textbook"  # "textbook" | "textbook_with_explanation" | "synthesized_summary"


class ValidationReport(BaseModel):
    status: str = "passed"  # "passed" | "corrected"
    checks_run: List[str] = Field(default_factory=list)
    issues_found: List[str] = Field(default_factory=list)
    corrections_applied: List[str] = Field(default_factory=list)
    summary: str = ""


class PresentationDeck(BaseModel):
    title: str
    subtitle: str = ""
    slides: List[SlideSpec] = Field(default_factory=list)
    stats: Dict[str, Any] = Field(default_factory=dict)
    notice: Optional[str] = None
    validation_report: Optional[ValidationReport] = None


class PresentationJobStage(str, Enum):
    UPLOADING = "uploading"
    ANALYZING_PDF = "analyzing_pdf"
    EXTRACTING_CONTENT = "extracting_content"
    UNDERSTANDING_MATERIAL = "understanding_material"
    PLANNING_PRESENTATION = "planning_presentation"
    VALIDATING_CONTENT = "validating_content"
    DESIGNING_SLIDES = "designing_slides"
    GENERATING_PPTX = "generating_pptx"
    COMPLETED = "completed"
    FAILED = "failed"


class PresentationJobStatus(BaseModel):
    job_id: str
    upload_id: str
    filename: str
    target_slide_count: Optional[int] = None
    status: str  # "queued" | "processing" | "completed" | "failed"
    stage: PresentationJobStage
    stage_label: str
    progress: int
    detail: str = ""
    error: Optional[str] = None
    notice: Optional[str] = None
    deck: Optional[PresentationDeck] = None
    download_url: Optional[str] = None
    created_at: str
    updated_at: str
