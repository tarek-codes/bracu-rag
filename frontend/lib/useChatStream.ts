"use client";

import { useCallback, useRef, useState } from "react";
import { API_BASE, refreshSession } from "./api";
import type { ChatMessage, StreamEvent, UiMessage } from "./types";

let keySeq = 0;
const nextKey = () => `m${Date.now()}_${keySeq++}`;

export function toUiMessage(m: ChatMessage): UiMessage {
  return {
    key: m.id,
    id: m.id,
    role: m.role,
    content: m.content,
    citations: m.citations ?? [],
    feedback: m.feedback,
    status: "done",
    fallback: m.role === "assistant" && (m.citations ?? []).length === 0,
  };
}

/** Parses a buffered SSE chunk into complete events, returning any trailing partial data. */
function parseSse(buffer: string): { events: StreamEvent[]; rest: string } {
  const events: StreamEvent[] = [];
  const blocks = buffer.split("\n\n");
  const rest = blocks.pop() ?? "";
  for (const block of blocks) {
    const data = block
      .split("\n")
      .filter((l) => l.startsWith("data:"))
      .map((l) => l.slice(5).trimStart())
      .join("\n");
    if (!data) continue;
    try {
      events.push(JSON.parse(data) as StreamEvent);
    } catch {
      // Ignore malformed frames rather than breaking the whole stream.
    }
  }
  return { events, rest };
}

interface Options {
  sessionId: string | null;
  onSessionCreated: (id: string) => void;
  onTurnComplete: () => void;
}

export function useChatStream({ sessionId, onSessionCreated, onTurnComplete }: Options) {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const sessionRef = useRef<string | null>(sessionId);

  const patch = useCallback((key: string, update: Partial<UiMessage> | ((m: UiMessage) => Partial<UiMessage>)) => {
    setMessages((prev) =>
      prev.map((m) => (m.key === key ? { ...m, ...(typeof update === "function" ? update(m) : update) } : m)),
    );
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const reset = useCallback((initial: UiMessage[] = [], id: string | null = null) => {
    abortRef.current?.abort();
    sessionRef.current = id;
    setMessages(initial);
  }, []);

  const run = useCallback(
    async (question: string, assistantKey: string) => {
      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);

      const doFetch = () =>
        fetch(`${API_BASE}/chat/stream`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
          body: JSON.stringify({ content: question, session_id: sessionRef.current }),
          signal: controller.signal,
        });

      try {
        let res = await doFetch();
        if (res.status === 401 && (await refreshSession())) res = await doFetch();
        if (res.status === 429) throw new Error("Too many requests right now. Please wait a moment and retry.");
        if (!res.ok || !res.body) throw new Error("The assistant is unavailable right now. Please retry.");

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const { events, rest } = parseSse(buffer);
          buffer = rest;

          for (const ev of events) {
            switch (ev.event) {
              case "query_rewrite":
                patch(assistantKey, { rewrittenQuery: ev.data.rewritten_query });
                break;
              case "sources":
                patch(assistantKey, { citations: ev.data.citations });
                break;
              case "token":
                patch(assistantKey, (m) => ({ content: m.content + ev.data.token, status: "streaming" }));
                break;
              case "done": {
                patch(assistantKey, {
                  id: ev.data.message_id,
                  content: ev.data.full_text,
                  fallback: ev.data.fallback,
                  status: "done",
                });
                const created = sessionRef.current === null;
                sessionRef.current = ev.data.session_id;
                if (created) onSessionCreated(ev.data.session_id);
                break;
              }
              case "error":
                throw new Error(ev.data.message);
            }
          }
        }
        patch(assistantKey, (m) => (m.status === "done" ? {} : { status: "done" }));
      } catch (err) {
        if (controller.signal.aborted) {
          patch(assistantKey, (m) => ({ status: "done", content: m.content || "_Response stopped._" }));
        } else {
          patch(assistantKey, {
            status: "error",
            error: err instanceof Error ? err.message : "Connection lost. Please retry.",
          });
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
        onTurnComplete();
      }
    },
    [patch, onSessionCreated, onTurnComplete],
  );

  const send = useCallback(
    (question: string) => {
      const text = question.trim();
      if (!text || abortRef.current) return;
      const assistantKey = nextKey();
      setMessages((prev) => [
        ...prev,
        { key: nextKey(), role: "user", content: text, citations: [], feedback: null, status: "done" },
        { key: assistantKey, role: "assistant", content: "", citations: [], feedback: null, status: "waiting" },
      ]);
      void run(text, assistantKey);
    },
    [run],
  );

  /** Re-asks the question behind the given assistant message (used by Retry and Regenerate). */
  const retry = useCallback(
    (assistantKey: string) => {
      if (abortRef.current) return;
      const idx = messages.findIndex((m) => m.key === assistantKey);
      const question = idx > 0 ? messages[idx - 1] : undefined;
      if (!question || question.role !== "user") return;
      patch(assistantKey, {
        content: "",
        citations: [],
        feedback: null,
        id: undefined,
        error: undefined,
        rewrittenQuery: undefined,
        status: "waiting",
      });
      void run(question.content, assistantKey);
    },
    [messages, patch, run],
  );

  return { messages, setMessages, streaming, send, retry, stop, reset };
}
