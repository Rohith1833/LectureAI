import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ProcessingPage from "../ProcessingPage";
import * as jobService from "@/services/jobService";

vi.mock("@/services/jobService");

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe("ProcessingPage", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.clearAllMocks();
  });

  const renderComponent = (jobId: string = "job-123") => {
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/processing/${jobId}`]}>
          <Routes>
            <Route path="/processing/:jobId" element={<ProcessingPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  it("navigates to the real academic review workspace on completion", async () => {
    (jobService.getJobStatus as Mock).mockResolvedValue({
      success: true,
      data: {
        job_id: "job-123",
        upload_id: "upload-abc-456",
        document_id: "doc-def-789",
        status: "completed",
        progress: 100,
        current_stage: "Export",
        created_at: "2026-09-29T10:00:00Z",
        updated_at: "2026-09-29T10:02:00Z",
        pipeline: [],
        error: null,
      },
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId("review-structure-button")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId("review-structure-button"));

    // CRITICAL: Must navigate to /academic/review/${upload_id}, NEVER /units or /preview
    expect(mockNavigate).toHaveBeenCalledWith("/academic/review/upload-abc-456");
    expect(mockNavigate).not.toHaveBeenCalledWith("/units");
    expect(mockNavigate).not.toHaveBeenCalledWith("/outline");
    expect(mockNavigate).not.toHaveBeenCalledWith("/preview");
  });

  it("displays extraction failure details and provides retry and review options", async () => {
    (jobService.getJobStatus as Mock).mockResolvedValue({
      success: true,
      data: {
        job_id: "job-123",
        upload_id: "upload-abc-456",
        document_id: null,
        status: "failed",
        progress: 30,
        current_stage: "OCR",
        created_at: "2026-09-29T10:00:00Z",
        updated_at: "2026-09-29T10:01:00Z",
        pipeline: [],
        error: "Corrupted PDF stream encountered on page 4",
      },
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Processing Failure Detected")).toBeInTheDocument();
      expect(
        screen.getByText(/Corrupted PDF stream encountered on page 4/)
      ).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /Back to Upload/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Inspect Partial Structure/i })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Inspect Partial Structure/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/academic/review/upload-abc-456");
  });
});
