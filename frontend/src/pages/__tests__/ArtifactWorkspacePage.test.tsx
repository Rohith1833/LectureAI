import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import ArtifactWorkspacePage from "../ArtifactWorkspacePage";
import * as knowledgeService from "@/services/knowledgeService";
import { artifactService } from "@/services/artifactService";

vi.mock("@/services/knowledgeService");
vi.mock("@/services/artifactService", () => ({
  artifactService: {
    generateArtifact: vi.fn(),
    getJobStatus: vi.fn(),
    listJobs: vi.fn(),
    getDownloadUrl: vi.fn((id: string) => `/api/v1/artifacts/${id}/download`),
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

const mockPendingJob = {
  id: "job-pending-001",
  upload_id: MOCK_UPLOAD_ID,
  knowledge_version_id: MOCK_VERSION_ID,
  artifact_type: "PPTX",
  status: "PENDING",
  config: {},
  created_at: 1700000100,
};

const mockPlanningJob = {
  ...mockPendingJob,
  status: "PLANNING",
};

const mockRenderingJob = {
  ...mockPendingJob,
  status: "RENDERING",
};

const mockCompletedJob = {
  ...mockPendingJob,
  status: "COMPLETED",
  artifact_uri: "/data/artifacts/artifact_job-pending-001.pptx",
};

const mockFailedJob = {
  ...mockPendingJob,
  status: "FAILED",
  error_message: "Validation failed: STRUCTURE: No slides generated",
};

// --- Helpers ---

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
    // Default: version loads successfully, no existing jobs
    (knowledgeService.listFinalizedVersions as Mock).mockResolvedValue([
      mockVersion,
    ]);
    (artifactService.listJobs as Mock).mockResolvedValue([]);
  });

  // ========================
  // Requirement 1: documentId is NOT sent as upload_id
  // ========================
  describe("upload_id correctness", () => {
    it("does NOT send documentId as upload_id in generateArtifact", async () => {
      (artifactService.generateArtifact as Mock).mockResolvedValue(
        mockPendingJob
      );

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("generate-button")).toBeInTheDocument();
      });

      await userEvent.click(screen.getByTestId("generate-button"));

      await waitFor(() => {
        expect(artifactService.generateArtifact).toHaveBeenCalledTimes(1);
      });

      const callArg = (artifactService.generateArtifact as Mock).mock
        .calls[0][0];

      // CRITICAL: upload_id must be the version's upload_id, NOT the route documentId
      expect(callArg.upload_id).toBe(MOCK_UPLOAD_ID);
      expect(callArg.upload_id).not.toBe(MOCK_DOCUMENT_ID);
    });

    it("uses version.upload_id for listJobs after version loads", async () => {
      renderPage();

      await waitFor(() => {
        expect(artifactService.listJobs).toHaveBeenCalledWith(MOCK_UPLOAD_ID);
      });

      // Must NOT have been called with the document ID
      expect(artifactService.listJobs).not.toHaveBeenCalledWith(
        MOCK_DOCUMENT_ID
      );
    });
  });

  // ========================
  // Requirement 2: Configuration controls render
  // ========================
  describe("configuration controls", () => {
    it("renders audience level selector", async () => {
      renderPage();
      await waitFor(() => {
        expect(
          screen.getByTestId("audience-level-select")
        ).toBeInTheDocument();
      });

      const select = screen.getByTestId(
        "audience-level-select"
      ) as HTMLSelectElement;
      expect(select.value).toBe("general");

      // Check all options exist
      const options = Array.from(select.options).map((o) => o.value);
      expect(options).toEqual([
        "general",
        "undergraduate",
        "graduate",
        "expert",
      ]);
    });

    it("renders depth selector", async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getByTestId("depth-select")).toBeInTheDocument();
      });

      const select = screen.getByTestId("depth-select") as HTMLSelectElement;
      expect(select.value).toBe("standard");

      const options = Array.from(select.options).map((o) => o.value);
      expect(options).toEqual(["overview", "standard", "detailed"]);
    });

    it("renders number of units input", async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getByTestId("num-units-input")).toBeInTheDocument();
      });

      const input = screen.getByTestId("num-units-input") as HTMLInputElement;
      expect(input.value).toBe("3");
    });

    it("renders include examples checkbox", async () => {
      renderPage();
      await waitFor(() => {
        expect(
          screen.getByTestId("include-examples-checkbox")
        ).toBeInTheDocument();
      });

      const checkbox = screen.getByTestId(
        "include-examples-checkbox"
      ) as HTMLInputElement;
      expect(checkbox.checked).toBe(true);
    });

    it("renders include questions checkbox", async () => {
      renderPage();
      await waitFor(() => {
        expect(
          screen.getByTestId("include-questions-checkbox")
        ).toBeInTheDocument();
      });

      const checkbox = screen.getByTestId(
        "include-questions-checkbox"
      ) as HTMLInputElement;
      expect(checkbox.checked).toBe(true);
    });
  });

  // ========================
  // Requirement 3: Configuration values are included in POST payload
  // ========================
  describe("configuration in POST payload", () => {
    it("sends all configuration values in the generate request", async () => {
      (artifactService.generateArtifact as Mock).mockResolvedValue(
        mockPendingJob
      );

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("generate-button")).toBeInTheDocument();
      });

      // Change audience to "graduate"
      await userEvent.selectOptions(
        screen.getByTestId("audience-level-select"),
        "graduate"
      );
      // Change depth to "detailed"
      await userEvent.selectOptions(
        screen.getByTestId("depth-select"),
        "detailed"
      );
      // Uncheck include examples
      await userEvent.click(screen.getByTestId("include-examples-checkbox"));

      await userEvent.click(screen.getByTestId("generate-button"));

      await waitFor(() => {
        expect(artifactService.generateArtifact).toHaveBeenCalledTimes(1);
      });

      const callArg = (artifactService.generateArtifact as Mock).mock
        .calls[0][0];

      expect(callArg.config).toEqual({
        audience_level: "graduate",
        depth: "detailed",
        num_units: 3,
        include_examples: false,
        include_questions: true,
      });
    });
  });

  // ========================
  // Requirement 4: Cannot generate without finalized version
  // ========================
  describe("finalized version guard", () => {
    it("shows error and no generate button when no finalized version exists", async () => {
      (knowledgeService.listFinalizedVersions as Mock).mockResolvedValue([]);

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("version-error")).toBeInTheDocument();
      });

      expect(screen.queryByTestId("generate-button")).not.toBeInTheDocument();
    });

    it("shows error when version loading fails", async () => {
      (knowledgeService.listFinalizedVersions as Mock).mockRejectedValue(
        new Error("Network error")
      );

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("version-error")).toBeInTheDocument();
      });

      expect(screen.queryByTestId("generate-button")).not.toBeInTheDocument();
    });
  });

  // ========================
  // Requirement 5: Polling during active states
  // ========================
  describe("polling behavior", () => {
    it("polls during PENDING/PLANNING/RENDERING and stops on COMPLETED", async () => {
      // First call returns PENDING, second returns PLANNING, third returns COMPLETED
      (artifactService.generateArtifact as Mock).mockResolvedValue(
        mockPendingJob
      );
      (artifactService.getJobStatus as Mock)
        .mockResolvedValueOnce(mockPlanningJob)
        .mockResolvedValueOnce(mockRenderingJob)
        .mockResolvedValueOnce(mockCompletedJob);

      vi.useFakeTimers({ shouldAdvanceTime: true });

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("generate-button")).toBeInTheDocument();
      });

      await userEvent.click(screen.getByTestId("generate-button"));

      // First poll: PLANNING
      await vi.advanceTimersByTimeAsync(2100);
      await waitFor(() => {
        expect(artifactService.getJobStatus).toHaveBeenCalledTimes(1);
      });

      // Second poll: RENDERING
      await vi.advanceTimersByTimeAsync(2100);
      await waitFor(() => {
        expect(artifactService.getJobStatus).toHaveBeenCalledTimes(2);
      });

      // Third poll: COMPLETED — should stop
      await vi.advanceTimersByTimeAsync(2100);
      await waitFor(() => {
        expect(artifactService.getJobStatus).toHaveBeenCalledTimes(3);
      });

      // No more polls after COMPLETED
      await vi.advanceTimersByTimeAsync(5000);
      expect(artifactService.getJobStatus).toHaveBeenCalledTimes(3);

      vi.useRealTimers();
    });

    it("stops polling on FAILED", async () => {
      (artifactService.generateArtifact as Mock).mockResolvedValue(
        mockPendingJob
      );
      (artifactService.getJobStatus as Mock).mockResolvedValueOnce(
        mockFailedJob
      );

      vi.useFakeTimers({ shouldAdvanceTime: true });

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("generate-button")).toBeInTheDocument();
      });

      await userEvent.click(screen.getByTestId("generate-button"));

      await vi.advanceTimersByTimeAsync(2100);
      await waitFor(() => {
        expect(artifactService.getJobStatus).toHaveBeenCalledTimes(1);
      });

      // No more polls after FAILED
      await vi.advanceTimersByTimeAsync(5000);
      expect(artifactService.getJobStatus).toHaveBeenCalledTimes(1);

      vi.useRealTimers();
    });
  });

  // ========================
  // Requirement 6: Download button only on COMPLETED
  // ========================
  describe("download button visibility", () => {
    it("shows download button only for COMPLETED jobs", async () => {
      (artifactService.listJobs as Mock).mockResolvedValue([mockCompletedJob]);

      renderPage();

      await waitFor(() => {
        expect(
          screen.getByTestId(`job-download-${mockCompletedJob.id}`)
        ).toBeInTheDocument();
      });

      const link = screen.getByTestId(
        `job-download-${mockCompletedJob.id}`
      ) as HTMLAnchorElement;
      expect(link.href).toContain(`/artifacts/${mockCompletedJob.id}/download`);
    });

    it("does NOT show download button for FAILED jobs", async () => {
      (artifactService.listJobs as Mock).mockResolvedValue([mockFailedJob]);

      renderPage();

      await waitFor(() => {
        expect(
          screen.getByTestId(`job-row-${mockFailedJob.id}`)
        ).toBeInTheDocument();
      });

      expect(
        screen.queryByTestId(`job-download-${mockFailedJob.id}`)
      ).not.toBeInTheDocument();
    });

    it("does NOT show download button for PENDING jobs", async () => {
      (artifactService.listJobs as Mock).mockResolvedValue([mockPendingJob]);

      renderPage();

      await waitFor(() => {
        expect(
          screen.getByTestId(`job-row-${mockPendingJob.id}`)
        ).toBeInTheDocument();
      });

      expect(
        screen.queryByTestId(`job-download-${mockPendingJob.id}`)
      ).not.toBeInTheDocument();
    });
  });

  // ========================
  // Requirement 7: FAILED error_message is displayed
  // ========================
  describe("FAILED state display", () => {
    it("displays the backend error_message for failed jobs", async () => {
      (artifactService.listJobs as Mock).mockResolvedValue([mockFailedJob]);

      renderPage();

      await waitFor(() => {
        expect(
          screen.getByTestId(`job-error-${mockFailedJob.id}`)
        ).toBeInTheDocument();
      });

      expect(
        screen.getByTestId(`job-error-${mockFailedJob.id}`)
      ).toHaveTextContent(
        "Validation failed: STRUCTURE: No slides generated"
      );
    });

    it("shows FAILED status badge for failed jobs", async () => {
      (artifactService.listJobs as Mock).mockResolvedValue([mockFailedJob]);

      renderPage();

      await waitFor(() => {
        const badge = screen.getByTestId(`job-status-${mockFailedJob.id}`);
        expect(badge).toHaveTextContent("Failed");
      });
    });
  });

  // ========================
  // Requirement 8: API error handling — surfaces backend detail
  // ========================
  describe("API error handling", () => {
    it("surfaces backend error detail instead of generic message", async () => {
      const axiosError = {
        response: {
          status: 400,
          data: {
            detail:
              "Knowledge version does not belong to the requested upload_id.",
          },
        },
        message: "Request failed with status code 400",
      };
      (artifactService.generateArtifact as Mock).mockRejectedValue(axiosError);

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("generate-button")).toBeInTheDocument();
      });

      await userEvent.click(screen.getByTestId("generate-button"));

      await waitFor(() => {
        expect(screen.getByTestId("generate-error")).toBeInTheDocument();
      });

      expect(screen.getByTestId("generate-error")).toHaveTextContent(
        "Knowledge version does not belong to the requested upload_id."
      );
    });
  });

  // ========================
  // Requirement 9: Knowledge version display
  // ========================
  describe("knowledge version display", () => {
    it("displays version ID, status, and upload_id", async () => {
      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId("version-info")).toBeInTheDocument();
      });

      expect(screen.getByTestId("version-id")).toHaveTextContent(
        MOCK_VERSION_ID
      );
      expect(screen.getByTestId("version-status")).toHaveTextContent(
        "FINALIZED"
      );
      expect(screen.getByTestId("version-upload-id")).toHaveTextContent(
        MOCK_UPLOAD_ID
      );
    });
  });
});
