"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUpRight, Menu } from "lucide-react";
import { ApiError, api } from "@/lib/api";
import { toUiMessage, useChatStream } from "@/lib/useChatStream";
import type { UiMessage } from "@/lib/types";
import { BrandMark } from "@/components/BrandMark";
import { ChatInput } from "./ChatInput";
import { MessageItem } from "./MessageItem";

const SUGGESTIONS = [
  "What is the undergraduate tuition fee per credit?",
  "How is CGPA calculated and what is academic probation?",
  "What scholarships and waivers are available?",
  "How do I apply for admission to an undergraduate program?",
];

export function ChatWorkspace({
  sessionId,
  signedIn,
  onSessionCreated,
  onTurnComplete,
  onOpenSidebar,
}: {
  sessionId: string | null;
  signedIn: boolean;
  onSessionCreated: (id: string) => void;
  onTurnComplete: () => void;
  onOpenSidebar: () => void;
}) {
  const createdRef = useRef<string | null>(null);
  const [loading, setLoading] = useState(!!sessionId);
  const [loadError, setLoadError] = useState<string | null>(null);

  const handleCreated = useCallback(
    (id: string) => {
      createdRef.current = id;
      onSessionCreated(id);
    },
    [onSessionCreated],
  );

  const { messages, setMessages, streaming, send, retry, stop, reset } = useChatStream({
    sessionId,
    onSessionCreated: handleCreated,
    onTurnComplete,
  });

  // The layout remounts this component per conversation, so history loads once on mount.
  // A session created by this instance (null -> new id) is already on screen and skipped.
  useEffect(() => {
    if (!sessionId || sessionId === createdRef.current) return;
    let cancelled = false;
    api
      .getSession(sessionId)
      .then((s) => !cancelled && reset(s.messages.map(toUiMessage), s.id))
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(
          err instanceof ApiError && (err.status === 404 || err.status === 403)
            ? "This conversation does not exist or you do not have access to it."
            : "Could not load this conversation.",
        );
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [sessionId, reset]);

  // Stick to the bottom while streaming unless the user scrolled up.
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const sendAndStick = (text: string) => {
    stickRef.current = true;
    send(text);
  };

  const updateMessage = (m: UiMessage) => setMessages((prev) => prev.map((x) => (x.key === m.key ? m : x)));

  const empty = !loading && !loadError && messages.length === 0;

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col">
      {/* Mobile top bar */}
      <div className="flex items-center gap-2 border-b border-border px-3 py-2.5 md:hidden">
        <button onClick={onOpenSidebar} className="rounded-lg p-2 hover:bg-surface" aria-label="Open sidebar">
          <Menu className="size-5" />
        </button>
        <span className="font-heading text-[15px] font-semibold">BRACU Assistant</span>
      </div>

      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        className="flex-1 overflow-y-auto"
      >
        {empty ? (
          <div className="mx-auto flex min-h-full max-w-[768px] flex-col items-center justify-center px-5 py-12 text-center">
            <div className="fade-up">
              <BrandMark size={48} />
            </div>
            <h1 className="fade-up font-heading mt-6 text-[26px] font-semibold tracking-tight sm:text-3xl">
              How can I help you today?
            </h1>
            <p className="fade-up font-sub mt-2 max-w-md text-[16px] text-muted">
              Ask anything about BRAC University: admissions, tuition, academic rules, courses and campus life.
            </p>
            <div className="mt-9 grid w-full max-w-[620px] gap-2.5 sm:grid-cols-2">
              {SUGGESTIONS.map((q, i) => (
                <button
                  key={q}
                  onClick={() => sendAndStick(q)}
                  style={{ animationDelay: `${80 + i * 50}ms` }}
                  className="fade-up group font-sub flex items-start justify-between gap-3 rounded-xl border border-border px-4 py-3 text-left text-[14.5px] leading-snug text-muted transition hover:border-accent/30 hover:bg-surface hover:text-text"
                >
                  <span>{q}</span>
                  <ArrowUpRight className="mt-0.5 size-4 shrink-0 opacity-0 transition group-hover:opacity-60" aria-hidden />
                </button>
              ))}
            </div>
            {!signedIn && (
              <p className="font-sub mt-8 text-[13px] text-muted">
                Chatting as a guest. <Link href="/login" className="text-accent hover:underline">Sign in</Link> to save your conversations.
              </p>
            )}
          </div>
        ) : (
          <div className="mx-auto max-w-[768px] space-y-8 px-5 pb-6 pt-8">
            {loading &&
              [0, 1].map((i) => (
                <div key={i} className="space-y-3">
                  <div className="ml-auto h-10 w-2/5 animate-pulse rounded-2xl bg-surface" />
                  <div className="h-4 w-4/5 animate-pulse rounded bg-surface" />
                  <div className="h-4 w-3/5 animate-pulse rounded bg-surface" />
                </div>
              ))}
            {loadError && (
              <div className="font-sub rounded-xl border border-border bg-surface p-6 text-center text-muted">
                <p>{loadError}</p>
                <Link href="/chat" className="font-heading mt-3 inline-block text-sm font-medium text-accent hover:underline">
                  Start a new chat
                </Link>
              </div>
            )}
            {messages.map((m, i) => (
              <MessageItem
                key={m.key}
                message={m}
                isLast={i === messages.length - 1 && !streaming}
                canRate={signedIn}
                onRetry={() => retry(m.key)}
                onFeedbackSaved={updateMessage}
              />
            ))}
          </div>
        )}
      </div>

      <div className="mx-auto w-full max-w-[768px] px-4 pb-4 pt-2 sm:px-5">
        <ChatInput onSend={sendAndStick} onStop={stop} streaming={streaming} autoFocus={!sessionId} />
      </div>
    </div>
  );
}
