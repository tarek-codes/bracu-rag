"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Clock, Loader2, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import type { IngestionJob } from "@/lib/types";

export function JobsSection({ onJobFinished }: { onJobFinished?: () => void }) {
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let timer: NodeJS.Timeout;

    const fetchJobs = async () => {
      try {
        const list = await api.listJobs(10);
        setJobs(list);
        const hasActive = list.some((j) => j.status === "pending" || j.status === "processing");
        if (!hasActive && onJobFinished) {
          onJobFinished();
        }
        if (hasActive) {
          timer = setTimeout(fetchJobs, 3500);
        }
      } catch {
        // Polling error non-blocking
      } finally {
        setLoading(false);
      }
    };

    void fetchJobs();
    return () => clearTimeout(timer);
  }, [onJobFinished]);

  if (loading && jobs.length === 0) return null;
  if (jobs.length === 0) return null;

  return (
    <div className="rounded-2xl border border-border bg-surface/40 p-4">
      <div className="flex items-center justify-between pb-3 border-b border-border">
        <h3 className="font-heading text-sm font-semibold">Recent Ingestion Jobs</h3>
        <span className="font-sub text-xs text-muted">Auto-updating</span>
      </div>

      <div className="mt-3 space-y-2">
        {jobs.slice(0, 5).map((job) => {
          const isPending = job.status === "pending";
          const isProcessing = job.status === "processing";
          const isDone = job.status === "done";
          const isFailed = job.status === "failed";

          return (
            <div
              key={job.id}
              className="flex items-center justify-between gap-3 rounded-xl border border-border/80 bg-background px-3 py-2 text-xs"
            >
              <div className="flex items-center gap-2 min-w-0">
                {isProcessing && <Loader2 className="size-3.5 animate-spin text-accent shrink-0" />}
                {isPending && <Clock className="size-3.5 text-amber-500 shrink-0" />}
                {isDone && <CheckCircle2 className="size-3.5 text-success shrink-0" />}
                {isFailed && <XCircle className="size-3.5 text-error shrink-0" />}

                <span className="font-medium capitalize">{job.source_type}</span>
                <span className="font-mono text-muted text-[11px] truncate max-w-[120px]">
                  {job.id.slice(0, 8)}
                </span>

                {job.stats && (
                  <span className="font-sub text-muted hidden sm:inline">
                    ({job.stats.chunks_added || 0} chunks added, {job.stats.files_skipped || 0} skipped)
                  </span>
                )}
              </div>

              <div className="shrink-0 flex items-center gap-2">
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
                    isDone
                      ? "bg-success/10 text-success"
                      : isFailed
                        ? "bg-error/10 text-error"
                        : "bg-accent/10 text-accent animate-pulse"
                  }`}
                >
                  {job.status}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
