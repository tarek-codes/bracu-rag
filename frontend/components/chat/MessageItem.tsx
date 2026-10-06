"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlertCircle, Check, Copy, RefreshCw, Search, ThumbsDown, ThumbsUp } from "lucide-react";
import { api } from "@/lib/api";
import type { UiMessage } from "@/lib/types";
import { CitationChips } from "./CitationChips";
import { FeedbackDialog } from "./FeedbackDialog";

function IconButton({
  label,
  onClick,
  active,
  children,
}: {
  label: string;
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className={`rounded-lg p-1.5 transition hover:bg-surface ${active ? "text-accent" : "text-muted hover:text-text"}`}
    >
      {children}
    </button>
  );
}

export function MessageItem({
  message,
  isLast,
  canRate,
  onRetry,
  onFeedbackSaved,
}: {
  message: UiMessage;
  isLast: boolean;
  canRate: boolean;
  onRetry: () => void;
  onFeedbackSaved: (m: UiMessage) => void;
}) {
  const [copied, setCopied] = useState(false);
  const [pendingRating, setPendingRating] = useState<1 | -1 | null>(null);

  if (message.role === "user") {
    return (
      <div className="fade-up flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md border border-border bg-surface px-4 py-2.5 text-[15.5px] leading-relaxed">
          {message.content}
        </div>
      </div>
    );
  }

  const copy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const saveFeedback = async (comment: string) => {
    if (!message.id || !pendingRating) return;
    try {
      const saved = await api.sendFeedback(message.id, pendingRating, comment);
      onFeedbackSaved({ ...message, feedback: saved.feedback });
    } catch {
      // Feedback is best effort; the dialog simply closes.
    }
  };

  const rating = message.feedback?.rating;
  const isWaiting = message.status === "waiting";
  const isStreaming = message.status === "streaming";

  return (
    <div className="group fade-up">
      {message.rewrittenQuery && (isWaiting || isStreaming) && (
        <p className="font-sub mb-2 inline-flex items-center gap-1.5 text-[13px] text-muted">
          <Search className="size-3.5" aria-hidden />
          Searching for: <span className="italic">{message.rewrittenQuery}</span>
        </p>
      )}

      {isWaiting && (
        <div className="flex items-center gap-3 py-1" aria-live="polite">
          <span className="dot-pulse flex gap-1" aria-hidden>
            <span />
            <span />
            <span />
          </span>
          <span className="font-sub text-[14px] text-muted">Searching university records...</span>
        </div>
      )}

      {message.content && (
        <div className={`prose-chat break-words ${message.fallback ? "text-muted" : ""}`}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: (props) => <a {...props} target="_blank" rel="noreferrer" />,
              table: (props) => (
                <div className="table-wrap">
                  <table {...props} />
                </div>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
          {isStreaming && <span className="stream-caret" aria-hidden />}
        </div>
      )}

      {message.status === "error" && (
        <div className="font-sub mt-2 flex flex-wrap items-center gap-3 rounded-xl border border-error/30 bg-error/5 px-3.5 py-2.5 text-sm text-error">
          <AlertCircle className="size-4 shrink-0" aria-hidden />
          <span className="flex-1">{message.error}</span>
          <button onClick={onRetry} className="font-heading rounded-lg border border-error/40 px-2.5 py-1 text-xs font-medium hover:bg-error/10">
            Retry
          </button>
        </div>
      )}

      {message.status === "done" && !message.fallback && <CitationChips citations={message.citations} />}

      {message.status === "done" && message.model && (
        <p className="font-sub mt-2 text-xs text-muted" title="Model that generated this answer">
          Answered by {message.model}
          {message.provider ? ` via ${message.provider}` : ""}
        </p>
      )}

      {message.status === "done" && message.content && (
        <div className="mt-2 flex items-center gap-0.5 opacity-100 transition md:opacity-0 md:group-hover:opacity-100 md:focus-within:opacity-100">
          <IconButton label={copied ? "Copied" : "Copy answer"} onClick={copy}>
            {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
          </IconButton>
          {canRate && message.id && (
            <>
              <IconButton label="Helpful" active={rating === 1} onClick={() => setPendingRating(1)}>
                <ThumbsUp className="size-4" fill={rating === 1 ? "currentColor" : "none"} />
              </IconButton>
              <IconButton label="Not helpful" active={rating === -1} onClick={() => setPendingRating(-1)}>
                <ThumbsDown className="size-4" fill={rating === -1 ? "currentColor" : "none"} />
              </IconButton>
            </>
          )}
          {isLast && (
            <IconButton label="Regenerate" onClick={onRetry}>
              <RefreshCw className="size-4" />
            </IconButton>
          )}
        </div>
      )}

      {pendingRating && (
        <FeedbackDialog
          open
          rating={pendingRating}
          onClose={() => setPendingRating(null)}
          onSubmit={saveFeedback}
        />
      )}
    </div>
  );
}
