import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ConversationSelector from "../ConversationSelector";
import * as conversationService from "@/services/conversationService";
import type { Conversation } from "@/types/conversation";

vi.mock("@/services/conversationService");

const mockConversations: Conversation[] = [
  {
    id: "conv-1",
    document_id: "doc-1",
    title: "First Session",
    status: "ACTIVE",
    created_at: 1000,
    updated_at: 2000,
    knowledge_version_id: null, message_count: 0,
  },
  {
    id: "conv-2",
    document_id: "doc-1",
    title: "Archived Session",
    status: "ARCHIVED",
    created_at: 1000,
    updated_at: 1500,
    knowledge_version_id: null, message_count: 0,
  },
];

describe("ConversationSelector", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.clearAllMocks();
  });

  const renderComponent = (props: any = {}) => {
    return render(
      <QueryClientProvider client={queryClient}>
        <ConversationSelector
          documentId="doc-1"
          selectedConversationId={null}
          selectedVersionId={null}
          onSelectConversation={vi.fn()}
          disabled={false}
          {...props}
        />
      </QueryClientProvider>
    );
  };

  it("renders a list of conversations", async () => {
    vi.mocked(conversationService.listConversations).mockResolvedValue(mockConversations);
    
    renderComponent();

    const dropdownBtn = await screen.findByRole("button", { name: /Single-Turn Generation/i });
    await waitFor(() => { expect(dropdownBtn).not.toBeDisabled(); });
    fireEvent.click(dropdownBtn);

    expect(await screen.findByText("First Session")).toBeInTheDocument();
    expect(await screen.findByText("Archived Session")).toBeInTheDocument();
  });

  it("handles creating a new conversation", async () => {
    vi.mocked(conversationService.listConversations).mockResolvedValue(mockConversations);
    const mockNewConv: Conversation = {
      id: "conv-3",
      document_id: "doc-1",
      title: "New Conversation",
      status: "ACTIVE",
      created_at: 3000,
      updated_at: 3000,
      knowledge_version_id: null, message_count: 0,
    };
    vi.mocked(conversationService.createConversation).mockResolvedValue(mockNewConv);
    
    const onSelectConversation = vi.fn();
    renderComponent({ onSelectConversation });

    const newSessionBtn = await screen.findByRole("button", { name: /New Session/i });
    await waitFor(() => {
      expect(newSessionBtn).not.toBeDisabled();
    });
    fireEvent.click(newSessionBtn);

    const createBtn = await screen.findByRole("button", { name: /^Create$/i });
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(conversationService.createConversation).toHaveBeenCalledWith("doc-1", {
        knowledge_version_id: null, title: undefined,
      });
      expect(onSelectConversation).toHaveBeenCalledWith(mockNewConv);
    });
  });

  it("shows active and archived statuses correctly", async () => {
    vi.mocked(conversationService.listConversations).mockResolvedValue(mockConversations);
    const { rerender } = renderComponent({ selectedConversationId: "conv-1" });
    
    // Check active
    const firstSession = await screen.findByText("First Session");
    expect(firstSession.closest("div")).toBeInTheDocument();
    
    // Rerender with archived selected
    rerender(
      <QueryClientProvider client={queryClient}>
        <ConversationSelector
          documentId="doc-1"
          selectedConversationId="conv-2"
          selectedVersionId={null}
          onSelectConversation={vi.fn()}
          disabled={false}
        />
      </QueryClientProvider>
    );
    
    const archivedSession = await screen.findByText("Archived Session");
    expect(archivedSession.closest("button")).toHaveTextContent("Archived");
  });

  it("allows switching conversations without leaking state", async () => {
    vi.mocked(conversationService.listConversations).mockResolvedValue(mockConversations);
    const onSelectConversation = vi.fn();
    
    renderComponent({ onSelectConversation });
    
    const dropdownBtn = await screen.findByRole("button", { name: /Single-Turn Generation/i });
    await waitFor(() => { expect(dropdownBtn).not.toBeDisabled(); });
    fireEvent.click(dropdownBtn);

    const firstSessionBtn = await screen.findByText("First Session");
    fireEvent.click(firstSessionBtn);
    
    expect(onSelectConversation).toHaveBeenCalledWith(mockConversations[0]);
  });
});
