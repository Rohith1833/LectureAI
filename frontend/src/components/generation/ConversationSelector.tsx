import { useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listConversations,
  createConversation,
  archiveConversation,
} from "@/services/conversationService";
import type { Conversation } from "@/types/conversation";
import { Button } from "@/components/ui/button";
import {
  MessageSquare,
  Plus,
  Archive,
  CheckCircle2,
  Clock,
  Sparkles,
  ChevronDown,
  X,
} from "lucide-react";

interface ConversationSelectorProps {
  documentId: string;
  selectedConversationId: string | null;
  selectedVersionId: string | null;
  onSelectConversation: (conversation: Conversation | null) => void;
  disabled?: boolean;
}

export default function ConversationSelector({
  documentId,
  selectedConversationId,
  selectedVersionId,
  onSelectConversation,
  disabled = false,
}: ConversationSelectorProps) {
  const queryClient = useQueryClient();
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  // Fetch conversations for document
  const { data: conversations = [], isLoading } = useQuery({
    queryKey: ["conversations", documentId],
    queryFn: () => listConversations(documentId),
    enabled: !!documentId,
  });

  const selectedConv = conversations.find((c) => c.id === selectedConversationId) || null;

  // Create mutation
  const createMutation = useMutation({
    mutationFn: (title?: string) =>
      createConversation(documentId, {
        knowledge_version_id: selectedVersionId,
        title: title || undefined,
      }),
    onSuccess: (newConv) => {
      queryClient.invalidateQueries({ queryKey: ["conversations", documentId] });
      onSelectConversation(newConv);
      setIsCreating(false);
      setNewTitle("");
      setIsDropdownOpen(false);
    },
  });

  // Archive mutation
  const archiveMutation = useMutation({
    mutationFn: (convId: string) => archiveConversation(convId),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["conversations", documentId] });
      if (selectedConversationId === updated.id) {
        onSelectConversation(updated);
      }
    },
  });

  const handleCreate = (e: FormEvent) => {
    e.preventDefault();
    createMutation.mutate(newTitle.trim() || undefined);
  };

  return (
    <div className="bg-card border border-border rounded-xl p-3 sm:p-4 shadow-xs flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-foreground font-semibold text-xs sm:text-sm">
          <MessageSquare className="size-4 text-violet-600 shrink-0" />
          <span>Conversation Session:</span>
        </div>

        <div className="flex items-center gap-2">
          {selectedConv && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onSelectConversation(null)}
              disabled={disabled}
              className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground cursor-pointer"
              title="Switch to single-turn standalone generation"
            >
              <X className="size-3 mr-1" /> Single-Turn Mode
            </Button>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsCreating((prev) => !prev)}
            disabled={disabled || createMutation.isPending}
            className="h-7 px-2.5 text-xs font-medium border-violet-200 dark:border-violet-800 text-violet-700 dark:text-violet-300 hover:bg-violet-50 dark:hover:bg-violet-950/40 cursor-pointer"
          >
            <Plus className="size-3.5 mr-1" /> New Session
          </Button>
        </div>
      </div>

      {/* Quick Create Input Form */}
      {isCreating && (
        <form
          onSubmit={handleCreate}
          className="flex items-center gap-2 bg-muted/40 p-2 rounded-lg border border-border animate-in fade-in duration-150"
        >
          <input
            type="text"
            placeholder="Conversation title (optional)..."
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            disabled={createMutation.isPending}
            className="flex-1 bg-background text-foreground text-xs px-2.5 py-1.5 rounded-md border border-input focus:outline-none focus:ring-1 focus:ring-violet-500"
            autoFocus
          />
          <Button
            type="submit"
            size="sm"
            disabled={createMutation.isPending}
            className="h-7 text-xs bg-violet-600 hover:bg-violet-700 text-white cursor-pointer"
          >
            {createMutation.isPending ? "Creating..." : "Create"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setIsCreating(false)}
            className="h-7 px-2 text-xs text-muted-foreground cursor-pointer"
          >
            Cancel
          </Button>
        </form>
      )}

      {/* Conversation Selector Bar */}
      <div className="relative">
        <button
          type="button"
          onClick={() => setIsDropdownOpen((prev) => !prev)}
          disabled={disabled || isLoading}
          className="w-full flex items-center justify-between gap-2 bg-muted/50 dark:bg-muted/20 hover:bg-muted/80 border border-input rounded-lg px-3 py-2 text-left transition-colors cursor-pointer disabled:opacity-50"
        >
          <div className="flex items-center gap-2 truncate">
            {selectedConv ? (
              <>
                <span
                  className={`size-2 rounded-full shrink-0 ${
                    selectedConv.status === "ACTIVE" ? "bg-emerald-500" : "bg-zinc-400"
                  }`}
                />
                <span className="text-xs font-semibold text-foreground truncate">
                  {selectedConv.title}
                </span>
                <span className="text-[10px] text-muted-foreground bg-background/80 border border-border px-1.5 py-0.5 rounded-sm shrink-0">
                  {selectedConv.message_count} msgs
                </span>
                {selectedConv.status === "ARCHIVED" && (
                  <span className="text-[10px] text-amber-700 dark:text-amber-300 bg-amber-100 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-800 px-1.5 py-0.5 rounded-sm shrink-0">
                    Archived
                  </span>
                )}
              </>
            ) : (
              <span className="text-xs text-muted-foreground flex items-center gap-1.5">
                <Sparkles className="size-3.5 text-violet-500" />
                Single-Turn Generation (No Conversation Selected)
              </span>
            )}
          </div>

          <ChevronDown
            className={`size-4 text-muted-foreground transition-transform shrink-0 ${
              isDropdownOpen ? "rotate-180" : ""
            }`}
          />
        </button>

        {/* Dropdown Options List */}
        {isDropdownOpen && (
          <div className="absolute z-20 top-full left-0 right-0 mt-1 bg-card border border-border rounded-xl shadow-lg p-1.5 flex flex-col gap-1 max-h-60 overflow-y-auto">
            <button
              type="button"
              onClick={() => {
                onSelectConversation(null);
                setIsDropdownOpen(false);
              }}
              className={`w-full flex items-center justify-between p-2 rounded-lg text-left text-xs transition-colors cursor-pointer ${
                !selectedConversationId
                  ? "bg-violet-50 dark:bg-violet-950/40 text-violet-700 dark:text-violet-300 font-medium"
                  : "hover:bg-muted text-muted-foreground"
              }`}
            >
              <span>Single-Turn Mode (Standalone)</span>
              {!selectedConversationId && <CheckCircle2 className="size-3.5" />}
            </button>

            {conversations.length > 0 && (
              <div className="border-t border-border my-1" />
            )}

            {conversations.map((conv) => (
              <div
                key={conv.id}
                className={`w-full flex items-center justify-between p-2 rounded-lg text-left text-xs transition-colors group ${
                  selectedConversationId === conv.id
                    ? "bg-violet-50 dark:bg-violet-950/40 text-violet-700 dark:text-violet-300 font-medium"
                    : "hover:bg-muted text-foreground"
                }`}
              >
                <button
                  type="button"
                  onClick={() => {
                    onSelectConversation(conv);
                    setIsDropdownOpen(false);
                  }}
                  className="flex-1 flex items-center gap-2 truncate cursor-pointer text-left"
                >
                  <span
                    className={`size-2 rounded-full shrink-0 ${
                      conv.status === "ACTIVE" ? "bg-emerald-500" : "bg-zinc-400"
                    }`}
                  />
                  <span className="truncate">{conv.title}</span>
                  <span className="text-[10px] text-muted-foreground shrink-0">
                    ({conv.message_count})
                  </span>
                </button>

                <div className="flex items-center gap-1 shrink-0 ml-2">
                  {conv.status === "ACTIVE" && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        archiveMutation.mutate(conv.id);
                      }}
                      disabled={archiveMutation.isPending}
                      className="p-1 text-muted-foreground hover:text-amber-600 rounded-sm hover:bg-background/80 transition-colors opacity-0 group-hover:opacity-100"
                      title="Archive conversation"
                    >
                      <Archive className="size-3" />
                    </button>
                  )}
                  {selectedConversationId === conv.id && (
                    <CheckCircle2 className="size-3.5 text-violet-600" />
                  )}
                </div>
              </div>
            ))}

            {conversations.length === 0 && (
              <div className="p-3 text-center text-xs text-muted-foreground">
                No conversations yet. Click "New Session" to start.
              </div>
            )}
          </div>
        )}
      </div>

      {/* Selected Conversation Status Details */}
      {selectedConv && (
        <div className="flex items-center justify-between text-[11px] text-muted-foreground px-1">
          <div className="flex items-center gap-1.5">
            <Clock className="size-3" />
            <span>
              Updated {new Date(selectedConv.updated_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>

          {selectedConv.status === "ACTIVE" ? (
            <button
              type="button"
              onClick={() => archiveMutation.mutate(selectedConv.id)}
              disabled={archiveMutation.isPending}
              className="hover:text-amber-600 transition-colors cursor-pointer flex items-center gap-1"
            >
              <Archive className="size-3" /> Archive Session
            </button>
          ) : (
            <span className="text-amber-600 dark:text-amber-400 font-medium">
              Read-Only Session
            </span>
          )}
        </div>
      )}
    </div>
  );
}
