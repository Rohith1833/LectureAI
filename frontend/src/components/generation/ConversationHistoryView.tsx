import { useQuery } from "@tanstack/react-query";
import { listConversationMessages } from "@/services/conversationService";
import type { Conversation } from "@/types/conversation";
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

export default function ConversationHistoryView({
  conversation,
}: ConversationHistoryViewProps) {
  const { data: messages = [], isLoading } = useQuery({
    queryKey: ["conversationMessages", conversation.id],
    queryFn: () => listConversationMessages(conversation.id),
    enabled: !!conversation.id,
  });

  if (isLoading) {
    return (
      <div className="border border-border bg-card rounded-xl p-6 flex flex-col gap-3 animate-pulse">
        <div className="h-4 bg-muted rounded-md w-1/4" />
        <div className="h-16 bg-muted/60 rounded-xl w-3/4 self-end" />
        <div className="h-24 bg-muted/60 rounded-xl w-4/5" />
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
        <div className="flex flex-col gap-4 max-h-[500px] overflow-y-auto pr-1">
          {messages.map((msg) => (
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
                <span>•</span>
                <Clock className="size-2.5" />
                <span>
                  {new Date(msg.created_at * 1000).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>

              <div
                className={`p-3.5 rounded-2xl text-xs sm:text-sm leading-relaxed max-w-[90%] sm:max-w-[85%] whitespace-pre-wrap ${
                  msg.role === "USER"
                    ? "bg-violet-600 text-white rounded-tr-xs"
                    : "bg-muted/70 dark:bg-muted/30 border border-border text-foreground rounded-tl-xs"
                }`}
              >
                {msg.content}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
