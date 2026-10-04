import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { listConversationMessages } from "@/services/conversationService";
import type { Conversation } from "@/types/conversation";
import type { GenerationResult } from "@/types/generation";
import GenerationResultRenderer from "./GenerationResultRenderer";
import {
  MessageSquare,
  User,
  Sparkles,
  Archive,
  Clock,
} from "lucide-react";

interface ConversationHistoryViewProps {
  conversation: Conversation;
}

function isGenerationResult(meta: unknown): meta is GenerationResult {
  if (!meta || typeof meta !== "object") return false;
  const m = meta as Record<string, unknown>;
  return (
    typeof m.answer === "string" &&
    Array.isArray(m.claims) &&
    typeof m.overall_grounding_status === "string"
  );
}

function formatMessageTime(timestamp: number | string | undefined): string {
  if (!timestamp) return "";
  const date =
    typeof timestamp === "number"
      ? new Date(timestamp > 1e11 ? timestamp : timestamp * 1000)
      : new Date(timestamp);
  if (isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function ConversationHistoryView({
  conversation,
}: ConversationHistoryViewProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const { data: messages = [], isLoading, isError } = useQuery({
    queryKey: ["conversationMessages", conversation.id],
    queryFn: () => listConversationMessages(conversation.id),
    enabled: !!conversation.id,
  });

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  if (isLoading) {
    return (
      <div className="border border-border bg-card rounded-xl p-6 flex flex-col gap-3 animate-pulse">
        <div className="h-4 bg-muted rounded-md w-1/4" />
        <div className="h-16 bg-muted/60 rounded-xl w-3/4 self-end" />
        <div className="h-24 bg-muted/60 rounded-xl w-4/5" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="border border-destructive/20 bg-destructive/10 rounded-xl p-5 text-destructive text-xs sm:text-sm">
        Failed to load conversation messages. Please refresh or select another session.
      </div>
    );
  }

  return (
    <div className="border border-border bg-card rounded-xl p-4 sm:p-5 flex flex-col gap-4 shadow-xs">
      {/* Session Title Header */}
      <div className="flex items-center justify-between border-b border-border pb-3">
        <div className="flex items-center gap-2">
          <MessageSquare className="size-4 text-violet-600 shrink-0" />
          <h3 className="font-bold text-sm text-foreground truncate max-w-sm">
            {conversation.title}
          </h3>
          <span className="text-[10px] text-muted-foreground bg-muted px-2 py-0.5 rounded-full font-mono">
            {messages.length} messages
          </span>
        </div>

        {conversation.status === "ARCHIVED" && (
          <div className="flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 px-2.5 py-1 rounded-md">
            <Archive className="size-3.5 shrink-0" />
            <span>Archived (Read-Only)</span>
          </div>
        )}
      </div>

      {/* Message List Stream */}
      {messages.length === 0 ? (
        <div className="text-center py-8 flex flex-col items-center justify-center gap-2 text-muted-foreground">
          <MessageSquare className="size-8 text-muted-foreground/40" />
          <p className="text-xs sm:text-sm font-medium text-foreground">
            No messages yet in this session
          </p>
          <p className="text-xs max-w-xs text-muted-foreground">
            Ask a question using the generation controls on the left to start grounded dialogue.
          </p>
        </div>
      ) : (
        <div ref={scrollRef} className="flex flex-col gap-4 max-h-[600px] overflow-y-auto pr-2 scroll-smooth">
          {messages.map((msg) => {
            const timeLabel = formatMessageTime(msg.created_at);
            const genResult = isGenerationResult(msg.metadata_json)
              ? (msg.metadata_json as unknown as GenerationResult)
              : null;

            return (
              <div
                key={msg.id}
                className={`flex flex-col gap-1.5 ${
                  msg.role === "USER" ? "items-end" : "items-start"
                }`}
              >
                <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground px-1">
                  {msg.role === "USER" ? (
                    <>
                      <span>You</span>
                      <User className="size-3 text-violet-500" />
                    </>
                  ) : (
                    <>
                      <Sparkles className="size-3 text-emerald-500" />
                      <span>LectureAI Assistant</span>
                    </>
                  )}
                  {timeLabel && (
                    <>
                      <span>•</span>
                      <Clock className="size-2.5" />
                      <span>{timeLabel}</span>
                    </>
                  )}
                </div>

                {msg.role === "USER" ? (
                  <div className="p-3.5 rounded-2xl bg-violet-600 text-white rounded-tr-xs text-xs sm:text-sm leading-relaxed max-w-[90%] sm:max-w-[85%] whitespace-pre-wrap shadow-xs">
                    {msg.content}
                  </div>
                ) : (
                  <div className="w-full">
                    {genResult ? (
                      <GenerationResultRenderer
                        result={genResult}
                        mode={genResult.mode || "QA"}
                      />
                    ) : (
                      <div className="p-3.5 rounded-2xl bg-muted/70 dark:bg-muted/30 border border-border text-foreground rounded-tl-xs text-xs sm:text-sm leading-relaxed max-w-[90%] sm:max-w-[85%] whitespace-pre-wrap shadow-xs">
                        {msg.content}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
