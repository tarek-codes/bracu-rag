"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, Square } from "lucide-react";

const MAX = 4000;

export function ChatInput({
  onSend,
  onStop,
  streaming,
  autoFocus,
}: {
  onSend: (text: string) => void;
  onStop: () => void;
  streaming: boolean;
  autoFocus?: boolean;
}) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // Auto grow up to about 6 lines.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`;
  }, [value]);

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  const submit = () => {
    if (streaming || !value.trim()) return;
    onSend(value);
    setValue("");
  };

  return (
    <div>
      <div className="flex items-end gap-2 rounded-2xl border border-border bg-background p-2 pl-4 shadow-[0_1px_0_rgba(0,0,0,0.02)] transition focus-within:border-accent/60 focus-within:ring-4 focus-within:ring-accent/10">
        <label htmlFor="chat-input" className="sr-only">
          Ask about BRAC University
        </label>
        <textarea
          id="chat-input"
          ref={ref}
          rows={1}
          value={value}
          maxLength={MAX}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Ask about BRAC University"
          className="max-h-[168px] flex-1 resize-none bg-transparent py-2 text-[16px] sm:text-[15.5px] leading-6 outline-none placeholder:font-sub placeholder:text-muted"
        />
        {streaming ? (
          <button
            id="stop-button"
            onClick={onStop}
            aria-label="Stop generating"
            className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-text text-background transition hover:opacity-85 active:scale-95"
          >
            <Square className="size-3.5" fill="currentColor" />
          </button>
        ) : (
          <button
            id="send-button"
            onClick={submit}
            disabled={!value.trim()}
            aria-label="Send message"
            className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-accent-fg transition hover:bg-accent-hover active:scale-95 disabled:cursor-not-allowed disabled:bg-surface-hover disabled:text-muted"
          >
            <ArrowUp className="size-4.5" strokeWidth={2.25} />
          </button>
        )}
      </div>
      <div className="font-sub mt-2 flex items-center justify-between gap-2 px-1 text-[11px] sm:text-[12px] text-muted">
        <span className="truncate">Answers from official BRAC University records.</span>
        {value.length > 3800 && (
          <span className={`shrink-0 ${value.length >= MAX ? "text-error" : ""}`}>
            {value.length}/{MAX}
          </span>
        )}
      </div>
    </div>
  );
}
