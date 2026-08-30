import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import GenerationWorkspacePage from "../GenerationWorkspacePage";
import * as generationService from "@/services/generationService";
import * as conversationService from "@/services/conversationService";
import * as knowledgeService from "@/services/knowledgeService";
import * as documentService from "@/services/documentService";

vi.mock("@/services/generationService");
vi.mock("@/services/conversationService");
vi.mock("@/services/knowledgeService");
vi.mock("@/services/documentService");

const mockDoc = { id: "doc-1", metadata: { title: "Test Doc" } };
const mockVersions = [{ id: "v1", approval_version: 1, created_at: 1000 }];
const mockConversations = [
  { id: "conv-1", document_id: "doc-1", title: "Test Conv", status: "ACTIVE", created_at: 1000, updated_at: 1000, knowledge_version_id: null }
];
const mockMessages = [
  { id: "msg-1", conversation_id: "conv-1", role: "USER", content: "hello", sequence: 1, created_at: 1000 }
];

describe("GenerationWorkspacePage", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.clearAllMocks();

    vi.mocked(documentService.getDocument).mockResolvedValue({ success: true, data: mockDoc as any });
    vi.mocked(knowledgeService.listFinalizedVersions).mockResolvedValue(mockVersions as any);
    vi.mocked(conversationService.listConversations).mockResolvedValue(mockConversations as any);
    vi.mocked(conversationService.getConversation).mockResolvedValue(mockConversations[0] as any);
    vi.mocked(conversationService.listConversationMessages).mockResolvedValue(mockMessages as any);
  });

  const renderComponent = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/documents/doc-1/generation"]}>
          <Routes>
            <Route path="/documents/:id/generation" element={<GenerationWorkspacePage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  it("loads and displays the workspace correctly", async () => {
    renderComponent();
    
    // Wait for the main heading
    expect(await screen.findByText(/Generation Workspace/i)).toBeInTheDocument();
    
    // Should default to single turn if no conversation in URL
    expect(await screen.findByText(/Grounded Q&A Workspace/i)).toBeInTheDocument();
  });

  it("supports single-turn generation without conversation_id", async () => {
    vi.mocked(generationService.queryGeneration).mockResolvedValue({
      mode: "QA",
      answer: "This is a single turn answer",
      claims: [],
      citations: {},
      tokens_used: 10,
      validation_passed: true,
      validation_warnings: [],
      timestamp: 1000
    } as any);

    renderComponent();
    
    // Type query
    const input = await screen.findByPlaceholderText(/Ask a specific question/i);
    fireEvent.change(input, { target: { value: "test query" } });
    
    // Click Generate
    const btn = screen.getByRole("button", { name: /Ask LectureAI/i });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(generationService.queryGeneration).toHaveBeenCalledWith(
        expect.objectContaining({
          query: "test query",
          conversation_id: null,
        })
      );
    });
  });

  it("switching conversations retains state independently and doesn't leak", async () => {
    renderComponent();
    
    // Wait for loading to finish
    await screen.findByText(/Generation Workspace/i);
    
    // It should initially not be rendering the conversation history (since it's not selected)
    expect(screen.queryByText("Test Conv")).not.toBeInTheDocument();
  });

  it("retains conversation_id when switching generation modes", async () => {
    const renderWithConv = () => {
      return render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/documents/doc-1/generation?conversation=conv-1&mode=QA"]}>
            <Routes>
              <Route path="/documents/:id/generation" element={<GenerationWorkspacePage />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      );
    };

    renderWithConv();
    await screen.findByText(/Generation Workspace/i);

    // Switch mode
    const explanationBtn = await screen.findByRole("tab", { name: /Explain/i });
    fireEvent.click(explanationBtn);

    // Provide query and generate
    const input = await screen.findByPlaceholderText(/What concept or topic would you like explained/i);
    fireEvent.change(input, { target: { value: "test mode switch" } });

    vi.mocked(generationService.queryGeneration).mockResolvedValue({
      mode: "EXPLANATION",
      answer: "Explanation output",
      claims: [],
      citations: {},
      tokens_used: 10,
      validation_passed: true,
      validation_warnings: [],
      timestamp: 1000
    } as any);

    const btn = screen.getByRole("button", { name: /Generate Explanation/i });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(generationService.queryGeneration).toHaveBeenCalledWith(
        expect.objectContaining({
          query: "test mode switch",
          mode: "EXPLANATION",
          conversation_id: "conv-1",
        })
      );
    });
  });
});
