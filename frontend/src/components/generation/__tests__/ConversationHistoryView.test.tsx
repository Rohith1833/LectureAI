import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ConversationHistoryView from "../ConversationHistoryView";
import * as conversationService from "@/services/conversationService";
import type { Conversation, ConversationMessage } from "@/types/conversation";

vi.mock("@/services/conversationService");

const mockConversation: Conversation = {
  id: "conv-1",
  document_id: "doc-1",
  title: "Test Session",
  status: "ACTIVE",
  created_at: 1000,
  updated_at: 2000,
  knowledge_version_id: null, message_count: 0,
};

const mockMessages: ConversationMessage[] = [
  {
    id: "msg-1",
    conversation_id: "conv-1",
    role: "USER",
    content: "What is quantum mechanics?",
    sequence: 1,
    created_at: 1000,
  },
  {
    id: "msg-2",
    conversation_id: "conv-1",
    role: "ASSISTANT",
    content: "Quantum mechanics is a fundamental theory in physics...",
    sequence: 2,
    created_at: 1005,
  }
];

describe("ConversationHistoryView", () => {
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
        <ConversationHistoryView
          conversation={mockConversation}
          {...props}
        />
      </QueryClientProvider>
    );
  };

  it("renders chronological messages sequentially", async () => {
    vi.mocked(conversationService.listConversationMessages).mockResolvedValue(mockMessages);
    renderComponent();

    expect(await screen.findByText("What is quantum mechanics?")).toBeInTheDocument();
    expect(await screen.findByText("Quantum mechanics is a fundamental theory in physics...")).toBeInTheDocument();
    
    // Ensure both roles are rendered
    expect(screen.getByText("You")).toBeInTheDocument();
    expect(screen.getByText("LectureAI Assistant")).toBeInTheDocument();
  });

  it("displays archived status if conversation is archived", async () => {
    vi.mocked(conversationService.listConversationMessages).mockResolvedValue([]);
    renderComponent({
      conversation: { ...mockConversation, status: "ARCHIVED" }
    });

    expect(await screen.findByText("Archived (Read-Only)")).toBeInTheDocument();
  });

  it("displays empty state when there are no messages", async () => {
    vi.mocked(conversationService.listConversationMessages).mockResolvedValue([]);
    renderComponent();

    expect(await screen.findByText("No messages yet in this session")).toBeInTheDocument();
  });
});
