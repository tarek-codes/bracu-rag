"use client";

import { useRef, useState } from "react";
import { AlertCircle, CheckCircle2, FileUp, Loader2, Upload } from "lucide-react";
import { Button, Modal } from "@/components/ui/Modal";
import { ApiError, api } from "@/lib/api";

const ALLOWED_EXTS = [".pdf", ".docx", ".txt", ".md", ".markdown"];
const MAX_BYTES = 25 * 1024 * 1024; // 25 MB

export function UploadModal({
  open,
  onClose,
  onUploaded,
}: {
  open: boolean;
  onClose: () => void;
  onUploaded: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function validateFile(f: File): string | null {
    const ext = "." + f.name.split(".").pop()?.toLowerCase();
    if (!ALLOWED_EXTS.includes(ext)) {
      return `File type "${ext}" not supported. Allowed formats: ${ALLOWED_EXTS.join(", ")}`;
    }
    if (f.size > MAX_BYTES) {
      return `File exceeds maximum size limit of ${MAX_BYTES / (1024 * 1024)}MB.`;
    }
    return null;
  }

  function handleFileSelected(f: File) {
    const validationError = validateFile(f);
    if (validationError) {
      setError(validationError);
      setFile(null);
    } else {
      setError(null);
      setFile(f);
    }
  }

  async function handleUpload() {
    if (!file) return;
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const job = await api.uploadDocument(file);
      setSuccess(`File "${file.name}" queued successfully (Job: ${job.id.slice(0, 8)}).`);
      setTimeout(() => {
        setSuccess(null);
        setFile(null);
        onUploaded();
        onClose();
      }, 1200);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to upload document. Please retry.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => {
        if (!loading) {
          setFile(null);
          setError(null);
          setSuccess(null);
          onClose();
        }
      }}
      title="Upload Knowledge Document"
      description="Upload official university documents to be parsed, chunked, and indexed into the vector database."
    >
      <div className="space-y-4">
        {/* Dropzone */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            const dropped = e.dataTransfer.files[0];
            if (dropped) handleFileSelected(dropped);
          }}
          onClick={() => inputRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-6 text-center transition ${
            isDragging
              ? "border-accent bg-accent-soft/40"
              : file
                ? "border-accent/50 bg-surface"
                : "border-border hover:border-accent/40 hover:bg-surface/50"
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            accept={ALLOWED_EXTS.join(",")}
            className="hidden"
            onChange={(e) => {
              const selected = e.target.files?.[0];
              if (selected) handleFileSelected(selected);
            }}
          />

          <div className="rounded-full bg-surface-hover p-3 text-accent">
            <Upload className="size-6" />
          </div>

          {file ? (
            <div className="mt-3">
              <p className="font-heading text-sm font-semibold text-text">{file.name}</p>
              <p className="font-sub mt-0.5 text-xs text-muted">
                {(file.size / 1024).toFixed(1)} KB (Click or drop to replace)
              </p>
            </div>
          ) : (
            <div className="mt-3">
              <p className="text-sm font-medium">Click to select or drag and drop file</p>
              <p className="font-sub mt-1 text-xs text-muted">
                PDF, DOCX, Markdown, or Plain Text (up to 25MB)
              </p>
            </div>
          )}
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
          <Button onClick={handleUpload} disabled={!file || loading}>
            {loading ? (
              <span className="flex items-center gap-2">
                <Loader2 className="size-4 animate-spin" /> Ingesting...
              </span>
            ) : (
              <span className="flex items-center gap-1.5">
                <FileUp className="size-4" /> Start Ingestion
              </span>
            )}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
