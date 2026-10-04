import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import InteractiveStudyModal from "../InteractiveStudyModal";
import type { ArtifactJobRead } from "@/types/artifact";

const mockJob: ArtifactJobRead = {
  id: "job-123",
  upload_id: "upload-abc",
  knowledge_version_id: "kv-1",
  artifact_type: "FLASHCARDS_CSV",
  status: "COMPLETED",
  config: {},
  created_at: Date.now(),
  plan: {
    slides: [
      {
        slide_type: "CONCEPT",
        title: "Photosynthesis",
        content: ["Process used by plants to convert light into chemical energy", "Produces glucose and oxygen"],
        speaker_notes: "Occurs in chloroplasts",
      },
      {
        slide_type: "QUESTION",
        title: "What is the powerhouse of the cell?",
        content: ["Mitochondria"],
        speaker_notes: "Generates ATP",
      },
    ],
  },
};

describe("InteractiveStudyModal", () => {
  it("renders modal with card content when open", () => {
    render(<InteractiveStudyModal job={mockJob} isOpen={true} onClose={vi.fn()} />);

    expect(screen.getByText("Interactive Study Deck")).toBeInTheDocument();
    expect(screen.getByText("Photosynthesis")).toBeInTheDocument();
    expect(screen.getByText("Card 1 of 2")).toBeInTheDocument();
  });

  it("flips card to reveal explanation when clicked", () => {
    render(<InteractiveStudyModal job={mockJob} isOpen={true} onClose={vi.fn()} />);

    // Initially back content is hidden / flipped
    const flipButton = screen.getByText("Flip Card");
    fireEvent.click(flipButton);

    expect(
      screen.getByText("Process used by plants to convert light into chemical energy")
    ).toBeInTheDocument();
    expect(screen.getByText("Occurs in chloroplasts")).toBeInTheDocument();
  });

  it("tracks mastery when clicking Mastered button", () => {
    render(<InteractiveStudyModal job={mockJob} isOpen={true} onClose={vi.fn()} />);

    const masteredBtn = screen.getByRole("button", { name: /Mastered/i });
    fireEvent.click(masteredBtn);

    // Navigates to Card 2 and shows 1 Mastered
    expect(screen.getByText("Card 2 of 2")).toBeInTheDocument();
    expect(screen.getByText(/1 Mastered/i)).toBeInTheDocument();
  });

  it("switches to Quiz mode", () => {
    render(<InteractiveStudyModal job={mockJob} isOpen={true} onClose={vi.fn()} />);

    const quizTab = screen.getByRole("button", { name: /Practice Quiz/i });
    fireEvent.click(quizTab);

    expect(screen.getByText("Question 1 of 2")).toBeInTheDocument();
    expect(screen.getByText("Click to Reveal Answer & Verification")).toBeInTheDocument();
  });

  it("switches to All Cards list mode", () => {
    render(<InteractiveStudyModal job={mockJob} isOpen={true} onClose={vi.fn()} />);

    const listTab = screen.getByRole("button", { name: /All Cards/i });
    fireEvent.click(listTab);

    expect(screen.getByText("2 cards found")).toBeInTheDocument();
    expect(screen.getByText("What is the powerhouse of the cell?")).toBeInTheDocument();
  });

  it("calls onClose when close button is clicked", () => {
    const handleClose = vi.fn();
    render(<InteractiveStudyModal job={mockJob} isOpen={true} onClose={handleClose} />);

    const closeBtn = screen.getByTitle("Close (Esc)");
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
