export type SlideLayoutType =
  | "title"
  | "section"
  | "concept"
  | "two_column"
  | "process"
  | "table"
  | "example"
  | "summary";

export interface BulletItem {
  heading: string;
  detail: string;
}

export interface ProcessStep {
  step_title: string;
  description: string;
}

export interface SlideSpec {
  layout: SlideLayoutType;
  title: string;
  subtitle: string;
  key_definition: string;
  bullets: BulletItem[];
  left_title: string;
  left_items: string[];
  right_title: string;
  right_items: string[];
  steps: ProcessStep[];
  headers: string[];
  rows: string[][];
  scenario: string;
  walkthrough: string[];
  takeaway: string;
  speaker_notes: string;
  content_origin?: "textbook" | "textbook_with_explanation" | "synthesized_summary";
}

export interface ValidationReport {
  status: "passed" | "corrected";
  checks_run: string[];
  issues_found: string[];
  corrections_applied: string[];
  summary: string;
}

export interface PresentationDeck {
  title: string;
  subtitle: string;
  slides: SlideSpec[];
  stats: {
    total_pages?: number;
    digital_pages?: number;
    ocr_pages?: number;
    total_words?: number;
    section_count?: number;
    table_count?: number;
    slide_count?: number;
    target_slide_count?: number | null;
  };
  notice?: string | null;
  validation_report?: ValidationReport | null;
}

export type PresentationJobStage =
  | "uploading"
  | "analyzing_pdf"
  | "extracting_content"
  | "understanding_material"
  | "planning_presentation"
  | "validating_content"
  | "designing_slides"
  | "generating_pptx"
  | "completed"
  | "failed";

export interface PresentationJobStatus {
  job_id: string;
  upload_id: string;
  filename: string;
  target_slide_count?: number | null;
  status: "queued" | "processing" | "completed" | "failed";
  stage: PresentationJobStage;
  stage_label: string;
  progress: number;
  detail: string;
  error: string | null;
  notice?: string | null;
  deck: PresentationDeck | null;
  download_url: string | null;
  created_at: string;
  updated_at: string;
}
