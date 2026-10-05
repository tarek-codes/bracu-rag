"use client";

import { useState } from "react";
import { AlertCircle, CheckCircle2, Globe, Loader2 } from "lucide-react";
import { Button, Modal } from "@/components/ui/Modal";
import { ApiError, api } from "@/lib/api";

export function UrlCrawlModal({
  open,
  onClose,
  onQueued,
}: {
  open: boolean;
  onClose: () => void;
  onQueued: () => void;
}) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  function validateUrl(val: string): boolean {
    try {
      const parsed = new URL(val);
      return parsed.protocol === "http:" || parsed.protocol === "https:";
    } catch {
      return false;
    }
  }

  async function handleCrawl() {
    const trimmed = url.trim();
    if (!validateUrl(trimmed)) {
      setError("Please provide a valid web URL starting with https:// or http://");
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const job = await api.ingestUrl(trimmed);
      setSuccess(`URL queued for ingestion successfully (Job: ${job.id.slice(0, 8)}).`);
      setTimeout(() => {
        setUrl("");
        setSuccess(null);
        onQueued();
        onClose();
      }, 1200);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to queue URL. Please check the address.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => {
        if (!loading) {
          setUrl("");
          setError(null);
          setSuccess(null);
          onClose();
        }
      }}
      title="Index Web Page URL"
      description="Enter a public university webpage URL. The crawler extracts the content, splits it into chunks, and indexes it."
    >
      <div className="space-y-4">
        <div>
          <label htmlFor="target-url" className="block text-sm font-medium">
            Target Page URL
          </label>
          <div className="relative mt-1.5">
            <Globe className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted" />
            <input
              id="target-url"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.bracu.ac.bd/academics/programs"
              className="font-sub w-full rounded-xl border border-border bg-background py-2.5 pl-10 pr-3.5 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
            />
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-xl border border-error/30 bg-error/5 p-3 text-sm text-error">
            <AlertCircle className="size-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div className="flex items-center gap-2 rounded-xl border border-success/30 bg-success/5 p-3 text-sm text-success">
            <CheckCircle2 className="size-4 shrink-0" />
            <span>{success}</span>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button onClick={handleCrawl} disabled={!url.trim() || loading}>
            {loading ? (
              <span className="flex items-center gap-2">
                <Loader2 className="size-4 animate-spin" /> Queuing...
              </span>
            ) : (
              "Queue Ingestion"
            )}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
