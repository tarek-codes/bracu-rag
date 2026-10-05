"use client";

import { useState } from "react";
import { ChevronDown, FileText, Globe } from "lucide-react";
import type { Citation } from "@/lib/types";

function label(c: Citation): string {
  const name = c.title || c.source_path?.split("/").pop() || "Source";
  return c.page ? `${name}, p. ${c.page}` : name;
}

/** Compact source chips under an answer. Each expands inline to show the cited snippet. */
export function CitationChips({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState<number | null>(null);
  if (!citations.length) return null;
  const active = open !== null ? citations[open] : undefined;

  return (
    <div className="mt-4">
      <p className="font-sub mb-2 text-xs font-medium uppercase tracking-wider text-muted">Sources</p>
      <div className="flex flex-wrap gap-1.5">
        {citations.map((c, i) => {
          const isUrl = c.source_path?.startsWith("http");
          const Icon = isUrl ? Globe : FileText;
          return (
            <button
              key={`${c.title}-${i}`}
              onClick={() => setOpen(open === i ? null : i)}
              aria-expanded={open === i}
              className={`font-sub inline-flex max-w-[260px] items-center gap-1.5 rounded-full border px-2.5 py-1 text-[13px] transition ${
                open === i
                  ? "border-accent/40 bg-accent-soft text-accent"
                  : "border-border text-muted hover:border-accent/30 hover:bg-surface hover:text-text"
              }`}
            >
              <span className="font-heading text-[11px] font-semibold opacity-70">{i + 1}</span>
              <Icon className="size-3.5 shrink-0" aria-hidden />
              <span className="truncate">{label(c)}</span>
              <ChevronDown className={`size-3 shrink-0 transition ${open === i ? "rotate-180" : ""}`} aria-hidden />
            </button>
          );
        })}
      </div>

      {active && (
        <div className="fade-up mt-2.5 rounded-xl border border-border bg-surface/60 p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-sm font-medium">{active.title}</p>
            {typeof active.score === "number" && active.score > 0 && (
              <span className="font-sub rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-medium text-accent">
                {Math.round(active.score * 100)}% match
              </span>
            )}
          </div>
          {(active.section || active.page) && (
            <p className="font-sub mt-0.5 text-xs text-muted">
              {[active.section, active.page ? `Page ${active.page}` : null].filter(Boolean).join("  ·  ")}
            </p>
          )}
          {active.snippet && (
            <blockquote className="font-sub mt-3 border-l-2 border-accent/40 pl-3 text-[14px] leading-relaxed text-muted">
              {active.snippet}
            </blockquote>
          )}
          {active.source_path?.startsWith("http") && (
            <a
              href={active.source_path}
              target="_blank"
              rel="noreferrer"
              className="font-sub mt-3 inline-block text-[13px] text-accent hover:underline"
            >
              Open original page
            </a>
          )}
        </div>
      )}
    </div>
  );
}
