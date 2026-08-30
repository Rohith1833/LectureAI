import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import AcademicReviewPage from "../AcademicReviewPage";
import * as reviewService from "@/services/reviewService";

vi.mock("@/services/reviewService");

const mockSummary = {
  upload_id: "upload-1",
  document_id: "doc-1",
  total_nodes_count: 250,
  unreviewed_count: 250,
  accepted_count: 0,
  modified_count: 0,
  rejected_count: 0,
  academic_quality_score: 0.95,
  academic_coverage_score: 0.9,
  academic_density_score: 0.85,
  academic_orphan_count: 0,
  active_overrides_count: 0,
  stale_overrides_count: 0,
  conflicted_overrides_count: 0,
  document_review_state: "NEEDS_REVIEW",
  current_revision: 0,
  is_approved: false,
};

const mockGraph = {
  nodes: [
    {
      node_id: "node-1",
      anchor_key: "anc-1",
      title: "Definition of Machine Learning",
      category: "DEFINITION",
      review_state: "UNREVIEWED",
      metadata: { provenance: "PIPELINE_INFERRED", original_category: "DEFINITION" },
      page_number: 1,
      target_block_id: "blk-1",
    },
  ],
  edges: [],
  total_count: 1,
  resolved_graph_version: 0,
};

describe("AcademicReviewPage", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.clearAllMocks();

    vi.mocked(reviewService.getReviewSummary).mockResolvedValue(mockSummary as any);
    vi.mocked(reviewService.getAcademicGraph).mockResolvedValue(mockGraph as any);
    vi.mocked(reviewService.getReconciliation).mockResolvedValue([] as any);
    vi.mocked(reviewService.getAuditHistory).mockResolvedValue([] as any);
    vi.mocked(reviewService.getApprovalReadiness).mockResolvedValue({ eligible: false, blocking_reasons: ["250 unreviewed nodes"] } as any);
  });

  const renderComponent = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/academic/review/upload-1"]}>
          <Routes>
            <Route path="/academic/review/:uploadId" element={<AcademicReviewPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  it("renders the summary and Accept All button with correct count", async () => {
    renderComponent();

    expect(await screen.findByText(/Academic Graph Review/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Accept All \(250\)/i })).toBeInTheDocument();
  });

  it("triggers ACCEPT_ALL_NODES on clicking Accept All", async () => {
    vi.mocked(reviewService.applyReviewAction).mockResolvedValue({
      success: true,
      action_type: "ACCEPT_ALL_NODES",
      override_id: "bulk",
      new_version: 1,
      timestamp: 1000,
    } as any);

    renderComponent();

    const acceptAllBtn = await screen.findByRole("button", { name: /Accept All \(250\)/i });
    fireEvent.click(acceptAllBtn);

    await waitFor(() => {
      expect(reviewService.applyReviewAction).toHaveBeenCalledWith("upload-1", {
        action_type: "ACCEPT_ALL_NODES",
        payload: {},
        expected_version: 0,
      });
    });
  });
});
