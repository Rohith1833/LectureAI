import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import HomePage from "../HomePage";
import * as uploadService from "@/services/uploadService";
import * as presentationService from "@/services/presentationService";

vi.mock("@/services/uploadService");
vi.mock("@/services/presentationService");

describe("HomePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders upload dropzone, slide-count options with Auto default, and disabled Generate PPT", () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );

    expect(screen.getByText(/Drop your textbook PDF here/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Auto" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "10 slides" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "15 slides" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "20 slides" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "30 slides" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Custom" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Generate PPT/i })).toBeDisabled();
  });

  it("passes selected custom slide count and renders notice & validation summary", async () => {
    vi.mocked(uploadService.uploadTextbookFile).mockResolvedValue({
      success: true,
      message: "Upload successful",
      data: {
        upload_id: "upload-123",
        original_filename: "biology.pdf",
        stored_filename: "biology_123.pdf",
        size_bytes: 2048,
        mime_type: "application/pdf",
        uploaded_at: "2026-11-25T00:00:00Z",
        status: "uploaded",
      },
    });

    vi.mocked(presentationService.startPresentationGeneration).mockResolvedValue({
      job_id: "job-456",
      upload_id: "upload-123",
      filename: "biology.pdf",
      target_slide_count: 14,
      status: "completed",
      stage: "completed",
      stage_label: "Presentation ready",
      progress: 100,
      detail: "Done",
      error: null,
      notice: "Generated 8 validated slides to avoid repeating content.",
      download_url: "/api/v1/presentations/job-456/download",
      created_at: "2026-11-25T00:00:00Z",
      updated_at: "2026-11-25T00:00:05Z",
      deck: {
        title: "Cell Biology Fundamentals",
        subtitle: "Mitosis and Cell Division",
        stats: { total_pages: 4, ocr_pages: 1, slide_count: 2 },
        notice: "Generated 8 validated slides to avoid repeating content.",
        validation_report: {
          status: "passed",
          checks_run: ["Duplicate slide detection"],
          issues_found: [],
          corrections_applied: [],
          summary: "All slides grounded in textbook material.",
        },
        slides: [
          {
            layout: "title",
            title: "Cell Biology Fundamentals",
            subtitle: "Mitosis and Cell Division",
            key_definition: "",
            bullets: [],
            left_title: "",
            left_items: [],
            right_title: "",
            right_items: [],
            steps: [],
            headers: [],
            rows: [],
            scenario: "",
            walkthrough: [],
            takeaway: "",
            speaker_notes: "Intro notes",
            content_origin: "synthesized_summary",
          },
          {
            layout: "concept",
            title: "Phases of Mitosis",
            subtitle: "",
            key_definition: "Mitosis is equal division of duplicated chromosomes.",
            bullets: [
              {
                heading: "Prophase",
                detail: "Chromatin condenses into visible chromosomes and the nuclear envelope breaks down.",
              },
            ],
            left_title: "",
            left_items: [],
            right_title: "",
            right_items: [],
            steps: [],
            headers: [],
            rows: [],
            scenario: "",
            walkthrough: [],
            takeaway: "",
            speaker_notes: "Explain prophase clearly.",
            content_origin: "textbook",
          },
        ],
      },
    });

    vi.mocked(presentationService.getPresentationDownloadUrl).mockReturnValue(
      "/api/v1/presentations/job-456/download"
    );

    const { container } = render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    );

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const pdfFile = new File(["%PDF-1.4 sample"], "biology.pdf", { type: "application/pdf" });
    fireEvent.change(fileInput, { target: { files: [pdfFile] } });

    fireEvent.click(screen.getByRole("button", { name: "Custom" }));
    const customInput = screen.getByLabelText("Custom slide count");
    fireEvent.change(customInput, { target: { value: "14" } });

    fireEvent.click(screen.getByRole("button", { name: /Generate PPT/i }));

    await waitFor(() => {
      expect(screen.getByText("Presentation Ready")).toBeInTheDocument();
    });

    expect(presentationService.startPresentationGeneration).toHaveBeenCalledWith("upload-123", 14);
    expect(screen.getByText(/Generated 8 validated slides/i)).toBeInTheDocument();
    expect(screen.getByText(/All slides grounded in textbook material/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Download PPTX/i })).toBeInTheDocument();
    expect(screen.getByText("Slide 1 of 2")).toBeInTheDocument();
  });
});
