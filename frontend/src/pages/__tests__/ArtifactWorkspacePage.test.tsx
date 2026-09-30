import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import ArtifactWorkspacePage from "../ArtifactWorkspacePage";
import * as knowledgeService from "@/services/knowledgeService";
import { artifactService } from "@/services/artifactService";
import type { SelectableContainersData } from "@/types/artifact";

vi.mock("@/services/knowledgeService");
vi.mock("@/services/artifactService", () => ({
  artifactService: {
    generateArtifact: vi.fn(),
    getJobStatus: vi.fn(),
    listJobs: vi.fn(),
    getDownloadUrl: vi.fn((id: string) => `http://localhost:8000/api/v1/artifacts/${id}/download`),
  },
}));

// --- Test Data ---

const MOCK_DOCUMENT_ID = "doc-abc-123";
const MOCK_UPLOAD_ID = "upload-xyz-789";
const MOCK_VERSION_ID = "ver-111-222";

const mockVersion = {
  id: MOCK_VERSION_ID,
  document_id: MOCK_DOCUMENT_ID,
  upload_id: MOCK_UPLOAD_ID,
  snapshot_id: "snap-001",
  schema_version: "1.0.0",
  created_at: 1700000000,
  status: "FINALIZED" as const,
  metadata: null,
  entity_count: 10,
  relationship_count: 5,
  evidence_count: 15,
  approval_version: 1,
};

const mockUnitsContainersData: SelectableContainersData = {
  knowledge_version_id: MOCK_VERSION_ID,
  document_id: MOCK_DOCUMENT_ID,
  upload_id: MOCK_UPLOAD_ID,
  approval_version: "v1",
  container_mode: "UNITS",
  container_type: "UNIT",
  containers: [
    {
      id: "unit-1",
      title: "Unit 1: Introduction to Computer Architecture",
      entity_type: "UNIT",
      source_page_start: 1,
      source_page_end: 25,
      topic_count: 4,
      stable_id: "anc_unit_1",
    },
    {
      id: "unit-2",
      title: "Unit 2: Memory Hierarchy and Caches",
      entity_type: "UNIT",
      source_page_start: 26,
      source_page_end: 55,
      topic_count: 6,
      stable_id: "anc_unit_2",
    },
    {
      id: "unit-3",
      title: "Unit 3: Pipelining and Superscalar Execution",
      entity_type: "UNIT",
      source_page_start: 56,
      source_page_end: 90,
      topic_count: 5,
      stable_id: "anc_unit_3",
    },
  ],
  diagnostics: ["Found 3 academic units."],
};

const mockChaptersContainersData: SelectableContainersData = {
  knowledge_version_id: MOCK_VERSION_ID,
  document_id: MOCK_DOCUMENT_ID,
  upload_id: MOCK_UPLOAD_ID,
  approval_version: "v1",
  container_mode: "CHAPTERS",
  container_type: "CHAPTER",
  containers: [
    {
      id: "chap-1",
      title: "Chapter 1: Foundations of Microprocessors",
      entity_type: "CHAPTER",
      source_page_start: 5,
      source_page_end: 30,
      topic_count: 3,
      stable_id: "anc_chap_1",
    },
    {
      id: "chap-2",
      title: "Chapter 2: Instruction Set Architectures",
      entity_type: "CHAPTER",
      source_page_start: 31,
      source_page_end: 60,
      topic_count: 4,
      stable_id: "anc_chap_2",
    },
  ],
  diagnostics: ["Chapters mode: No syllabus units detected in this textbook. Selection is by chapter."],
};

const mockReviewRequiredContainersData: SelectableContainersData = {
  knowledge_version_id: MOCK_VERSION_ID,
  document_id: MOCK_DOCUMENT_ID,
  upload_id: MOCK_UPLOAD_ID,
  approval_version: "v1",
  container_mode: "REVIEW_REQUIRED",
  container_type: null,
  containers: [],
  diagnostics: [
    "No selectable academic containers (units or chapters) found in knowledge version. Academic review required.",
  ],
};

const mockPendingJob = {
  id: "job-pending-001",
  upload_id: MOCK_UPLOAD_ID,
  knowledge_version_id: MOCK_VERSION_ID,
  artifact_type: "PPTX" as const,
  status: "PENDING" as const,
  config: { selected_unit_ids: ["unit-1"] },
  created_at: 1700000100,
};

const mockPlanningJob = {
  ...mockPendingJob,
  status: "PLANNING" as const,
};

const mockRenderingJob = {
  ...mockPendingJob,
  status: "RENDERING" as const,
};

const mockCompletedJob = {
  ...mockPendingJob,
  id: "job-completed-001",
  status: "COMPLETED" as const,
  artifact_uri: "/data/artifacts/artifact_job-completed-001.pptx",
};

const mockFailedJob = {
  ...mockPendingJob,
  id: "job-failed-002",
  status: "FAILED" as const,
  error_message: "Validation failed: STRUCTURE: Workload limit exceeded",
};

// --- Helper ---

function renderPage(documentId: string = MOCK_DOCUMENT_ID) {
  return render(
    <MemoryRouter initialEntries={[`/documents/${documentId}/artifact`]}>
      <Routes>
        <Route
          path="/documents/:id/artifact"
          element={<ArtifactWorkspacePage />}
        />
      </Routes>
    </MemoryRouter>
  );
}

// --- Tests ---

describe("ArtifactWorkspacePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (knowledgeService.listFinalizedVersions as Mock).mockResolvedValue([
      mockVersion,
    ]);
    (knowledgeService.getDocumentSelectableContainers as Mock).mockResolvedValue(
      mockUnitsContainersData
    );
    (artifactService.listJobs as Mock).mockResolvedValue([]);
  });

  // ========================================================
  // 1. Finalized Version & Upload ID Correctness
  // ========================================================
  describe("Finalized Version & Upload ID", () => {
    it("renders finalized knowledge version identity", async () => {
      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("version-id")).toHaveTextContent(MOCK_VERSION_ID);
        expect(screen.getByTestId("version-upload-id")).toHaveTextContent(MOCK_UPLOAD_ID);
        expect(screen.getByTestId("version-status")).toHaveTextContent("FINALIZED");
      });
    });

    it("sends version.upload_id (NOT documentId) to generateArtifact", async () => {
      (artifactService.generateArtifact as Mock).mockResolvedValue(mockPendingJob);

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("container-checkbox-unit-1")).toBeInTheDocument();
      });

      // Select Unit 1
      await userEvent.click(screen.getByTestId("container-checkbox-unit-1"));
      await userEvent.click(screen.getByTestId("generate-button"));

      await waitFor(() => {
        expect(artifactService.generateArtifact).toHaveBeenCalledTimes(1);
      });

      const callArg = (artifactService.generateArtifact as Mock).mock.calls[0][0];
      expect(callArg.upload_id).toBe(MOCK_UPLOAD_ID);
      expect(callArg.upload_id).not.toBe(MOCK_DOCUMENT_ID);
      expect(callArg.knowledge_version_id).toBe(MOCK_VERSION_ID);
    });

    it("shows error and prevents generation when no finalized version exists", async () => {
      (knowledgeService.listFinalizedVersions as Mock).mockResolvedValue([]);

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("version-error")).toBeInTheDocument();
      });

      expect(screen.queryByTestId("generate-button")).not.toBeInTheDocument();
    });
  });

  // ========================================================
  // 2. Selectable Containers & Mode Handling
  // ========================================================
  describe("Selectable Containers & Container Modes", () => {
    it("renders all units with exact titles, page ranges, and topic counts", async () => {
      renderPage();

      await waitFor(() => {
        expect(
          screen.getByText("Unit 1: Introduction to Computer Architecture")
        ).toBeInTheDocument();
        expect(
          screen.getByText("Unit 2: Memory Hierarchy and Caches")
        ).toBeInTheDocument();
        expect(
          screen.getByText("Unit 3: Pipelining and Superscalar Execution")
        ).toBeInTheDocument();
      });

      expect(screen.getByTestId("container-pages-unit-1")).toHaveTextContent("Pages 1–25");
      expect(screen.getByTestId("container-pages-unit-2")).toHaveTextContent("Pages 26–55");
      expect(screen.getByTestId("container-mode-badge")).toHaveTextContent("UNITS");
    });

    it("handles Chapters mode: labels choices as chapters and renders informational banner", async () => {
      (knowledgeService.getDocumentSelectableContainers as Mock).mockResolvedValue(
        mockChaptersContainersData
      );

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("chapters-mode-banner")).toBeInTheDocument();
        expect(screen.getByText("Select Chapters")).toBeInTheDocument();
        expect(
          screen.getByText("Chapter 1: Foundations of Microprocessors")
        ).toBeInTheDocument();
      });

      expect(screen.getByTestId("container-mode-badge")).toHaveTextContent("CHAPTERS");
    });

    it("handles REVIEW_REQUIRED mode: shows explanation, review link, and disables generation", async () => {
      (knowledgeService.getDocumentSelectableContainers as Mock).mockResolvedValue(
        mockReviewRequiredContainersData
      );

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("review-required-banner")).toBeInTheDocument();
        expect(screen.getByTestId("container-mode-badge")).toHaveTextContent("REVIEW_REQUIRED");
      });

      // Generation button must be disabled
      const genBtn = screen.getByTestId("generate-button");
      expect(genBtn).toBeDisabled();
      expect(screen.queryByTestId("containers-list")).not.toBeInTheDocument();
    });
  });

  // ========================================================
  // 3. Selection Behavior: Single, Multiple, All, and Mutual Exclusion
  // ========================================================
  describe("Selection Controls and Payload Verification", () => {
    it("initializes with clear and intentional empty selection, disabling Generate", async () => {
      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("selected-count-badge")).toHaveTextContent("0 of 3 selected");
      });

      const genBtn = screen.getByTestId("generate-button");
      expect(genBtn).toBeDisabled();
    });

    it("enables Generate upon selecting any single unit and sends exact selected_unit_ids", async () => {
      (artifactService.generateArtifact as Mock).mockResolvedValue(mockPendingJob);

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("container-checkbox-unit-2")).toBeInTheDocument();
      });

      // Select Unit 2
      await userEvent.click(screen.getByTestId("container-checkbox-unit-2"));

      expect(screen.getByTestId("selected-count-badge")).toHaveTextContent("1 of 3 selected");
      expect(screen.getByTestId("generate-button")).not.toBeDisabled();

      await userEvent.click(screen.getByTestId("generate-button"));

      await waitFor(() => {
        expect(artifactService.generateArtifact).toHaveBeenCalledTimes(1);
      });

      const callConfig = (artifactService.generateArtifact as Mock).mock.calls[0][0].config;
      expect(callConfig.selected_unit_ids).toEqual(["unit-2"]);
      // MUST NOT send num_units
      expect(callConfig.num_units).toBeUndefined();
    });

    it("supports selecting multiple arbitrary units", async () => {
      (artifactService.generateArtifact as Mock).mockResolvedValue(mockPendingJob);

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("container-checkbox-unit-1")).toBeInTheDocument();
      });

      // Select Unit 1 and Unit 3
      await userEvent.click(screen.getByTestId("container-checkbox-unit-1"));
      await userEvent.click(screen.getByTestId("container-checkbox-unit-3"));

      expect(screen.getByTestId("selected-count-badge")).toHaveTextContent("2 of 3 selected");

      await userEvent.click(screen.getByTestId("generate-button"));

      await waitFor(() => {
        expect(artifactService.generateArtifact).toHaveBeenCalledTimes(1);
      });

      const callConfig = (artifactService.generateArtifact as Mock).mock.calls[0][0].config;
      expect(callConfig.selected_unit_ids).toEqual(["unit-1", "unit-3"]);
      expect(callConfig.num_units).toBeUndefined();
    });

    it("supports Select All and Clear Selection buttons", async () => {
      (artifactService.generateArtifact as Mock).mockResolvedValue(mockPendingJob);

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("select-all-button")).toBeInTheDocument();
      });

      // Click Select All
      await userEvent.click(screen.getByTestId("select-all-button"));
      expect(screen.getByTestId("selected-count-badge")).toHaveTextContent("3 of 3 selected");

      // Click Clear Selection
      await userEvent.click(screen.getByTestId("clear-selection-button"));
      expect(screen.getByTestId("selected-count-badge")).toHaveTextContent("0 of 3 selected");
      expect(screen.getByTestId("generate-button")).toBeDisabled();

      // Click Select All again and generate
      await userEvent.click(screen.getByTestId("select-all-button"));
      await userEvent.click(screen.getByTestId("generate-button"));

      await waitFor(() => {
        expect(artifactService.generateArtifact).toHaveBeenCalledTimes(1);
      });

      const callConfig = (artifactService.generateArtifact as Mock).mock.calls[0][0].config;
      expect(callConfig.selected_unit_ids).toEqual(["unit-1", "unit-2", "unit-3"]);
    });

    it("sends audience, depth, examples, and questions controls without num_units", async () => {
      (artifactService.generateArtifact as Mock).mockResolvedValue(mockPendingJob);

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("container-checkbox-unit-1")).toBeInTheDocument();
      });

      await userEvent.click(screen.getByTestId("container-checkbox-unit-1"));
      await userEvent.selectOptions(screen.getByTestId("audience-level-select"), "expert");
      await userEvent.selectOptions(screen.getByTestId("depth-select"), "detailed");
      await userEvent.click(screen.getByTestId("include-examples-checkbox"));

      await userEvent.click(screen.getByTestId("generate-button"));

      await waitFor(() => {
        expect(artifactService.generateArtifact).toHaveBeenCalledTimes(1);
      });

      const config = (artifactService.generateArtifact as Mock).mock.calls[0][0].config;
      expect(config).toEqual({
        audience_level: "expert",
        depth: "detailed",
        selected_unit_ids: ["unit-1"],
        include_examples: false,
        include_questions: true,
      });
      expect(config.num_units).toBeUndefined();
    });
  });

  // ========================================================
  // 4. Immediate Duplicate-Submit Prevention
  // ========================================================
  describe("Duplicate Submission Prevention", () => {
    it("disables Generate immediately while create request is in-flight", async () => {
      let resolveGenerate: (val: any) => void;
      const generatePromise = new Promise((resolve) => {
        resolveGenerate = resolve;
      });
      (artifactService.generateArtifact as Mock).mockReturnValue(generatePromise);

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("container-checkbox-unit-1")).toBeInTheDocument();
      });

      await userEvent.click(screen.getByTestId("container-checkbox-unit-1"));
      const genBtn = screen.getByTestId("generate-button");

      // First click initiates submission
      await userEvent.click(genBtn);

      // Button should now be disabled and show loading state
      expect(genBtn).toBeDisabled();
      expect(screen.getByText(/Starting Generation/i)).toBeInTheDocument();

      // Subsequent click while in flight should be a no-op
      await userEvent.click(genBtn);
      expect(artifactService.generateArtifact).toHaveBeenCalledTimes(1);

      // Resolve generation
      resolveGenerate!(mockPendingJob);

      await waitFor(() => {
        expect(screen.getByText(/Processing/i)).toBeInTheDocument();
      });
    });
  });

  // ========================================================
  // 5. Polling & History Behavior
  // ========================================================
  describe("Polling and Terminal States", () => {
    it("polls through PLANNING -> RENDERING -> COMPLETED and stops polling", async () => {
      (artifactService.generateArtifact as Mock).mockResolvedValue(mockPendingJob);
      (artifactService.getJobStatus as Mock)
        .mockResolvedValueOnce(mockPlanningJob)
        .mockResolvedValueOnce(mockRenderingJob)
        .mockResolvedValueOnce(mockCompletedJob);

      vi.useFakeTimers({ shouldAdvanceTime: true });

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("container-checkbox-unit-1")).toBeInTheDocument();
      });

      await userEvent.click(screen.getByTestId("container-checkbox-unit-1"));
      await userEvent.click(screen.getByTestId("generate-button"));

      // 1st poll: PLANNING
      await vi.advanceTimersByTimeAsync(2100);
      await waitFor(() => {
        expect(artifactService.getJobStatus).toHaveBeenCalledTimes(1);
      });

      // 2nd poll: RENDERING
      await vi.advanceTimersByTimeAsync(2100);
      await waitFor(() => {
        expect(artifactService.getJobStatus).toHaveBeenCalledTimes(2);
      });

      // 3rd poll: COMPLETED
      await vi.advanceTimersByTimeAsync(2100);
      await waitFor(() => {
        expect(artifactService.getJobStatus).toHaveBeenCalledTimes(3);
      });

      // Polling must stop after COMPLETED
      await vi.advanceTimersByTimeAsync(5000);
      expect(artifactService.getJobStatus).toHaveBeenCalledTimes(3);

      vi.useRealTimers();
    });

    it("resumes polling after page refresh using active job from job history", async () => {
      // Simulate existing active job in listJobs
      (artifactService.listJobs as Mock).mockResolvedValue([mockPlanningJob]);
      (artifactService.getJobStatus as Mock).mockResolvedValue(mockCompletedJob);

      vi.useFakeTimers({ shouldAdvanceTime: true });

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId(`job-row-${mockPlanningJob.id}`)).toBeInTheDocument();
      });

      // Should automatically poll the active job
      await vi.advanceTimersByTimeAsync(2100);
      await waitFor(() => {
        expect(artifactService.getJobStatus).toHaveBeenCalledWith(mockPlanningJob.id);
      });

      vi.useRealTimers();
    });

    it("handles transient network error during polling without marking job as failed", async () => {
      (artifactService.generateArtifact as Mock).mockResolvedValue(mockPendingJob);
      (artifactService.getJobStatus as Mock)
        .mockRejectedValueOnce(new Error("Network Error")) // Transient network blip
        .mockResolvedValueOnce(mockPlanningJob)
        .mockResolvedValueOnce(mockCompletedJob);

      vi.useFakeTimers({ shouldAdvanceTime: true });

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("container-checkbox-unit-1")).toBeInTheDocument();
      });

      await userEvent.click(screen.getByTestId("container-checkbox-unit-1"));
      await userEvent.click(screen.getByTestId("generate-button"));

      // 1st poll errors out with transient error
      await vi.advanceTimersByTimeAsync(2100);
      expect(artifactService.getJobStatus).toHaveBeenCalledTimes(1);

      // Job should NOT be marked failed in UI
      expect(screen.queryByTestId(`job-error-${mockPendingJob.id}`)).not.toBeInTheDocument();

      // 2nd poll succeeds with PLANNING
      await vi.advanceTimersByTimeAsync(2100);
      expect(artifactService.getJobStatus).toHaveBeenCalledTimes(2);

      // 3rd poll completes
      await vi.advanceTimersByTimeAsync(2100);
      expect(artifactService.getJobStatus).toHaveBeenCalledTimes(3);

      vi.useRealTimers();
    });
  });

  // ========================================================
  // 6. Download & Error Handling
  // ========================================================
  describe("Download and Backend Error Parsing", () => {
    it("enables download ONLY for COMPLETED jobs", async () => {
      (artifactService.listJobs as Mock).mockResolvedValue([
        mockCompletedJob,
        mockFailedJob,
      ]);

      renderPage();

      await waitFor(() => {
        expect(
          screen.getByTestId(`job-download-${mockCompletedJob.id}`)
        ).toBeInTheDocument();
      });

      // Check download link URL
      const dlLink = screen.getByTestId(
        `job-download-${mockCompletedJob.id}`
      ) as HTMLAnchorElement;
      expect(dlLink.href).toContain(`/api/v1/artifacts/${mockCompletedJob.id}/download`);

      // Failed job should NOT have a download link
      expect(
        screen.queryByTestId(`job-download-${mockFailedJob.id}`)
      ).not.toBeInTheDocument();

      // Failed job displays error message
      expect(
        screen.getByTestId(`job-error-${mockFailedJob.id}`)
      ).toHaveTextContent("Workload limit exceeded");
    });

    it("displays parsed backend workload limit error cleanly", async () => {
      (artifactService.generateArtifact as Mock).mockRejectedValue({
        response: {
          data: {
            detail: "Workload limit exceeded: Maximum 10 topics permitted per job.",
          },
        },
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("container-checkbox-unit-1")).toBeInTheDocument();
      });

      await userEvent.click(screen.getByTestId("container-checkbox-unit-1"));
      await userEvent.click(screen.getByTestId("generate-button"));

      await waitFor(() => {
        expect(screen.getByTestId("generate-error")).toBeInTheDocument();
      });

      expect(screen.getByTestId("generate-error")).toHaveTextContent(
        "Workload limit exceeded: Maximum 10 topics permitted per job."
      );
    });
  });
});
