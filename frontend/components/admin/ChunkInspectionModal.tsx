"use client";

import { useEffect, useState } from "react";
import { FileText, Hash, Loader2 } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { api } from "@/lib/api";
import type { DocumentDetail } from "@/lib/types";

export function ChunkInspectionModal({
  documentId,
  open,
  onClose,
}: {
  documentId: string | null;
  open: boolean;
  onClose: () => void;
}) {
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !documentId) return;
    let active = true;
    api
      .getDocument(documentId)
      .then((data) => {
        if (active) {
          setDoc(data);
          setLoading(false);
        }
      })
      .catch(() => {
        if (active) {
          setDoc(null);
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [open, documentId]);

  const activeDoc = open ? doc : null;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={activeDoc ? `Chunks: ${activeDoc.title}` : "Inspect Document Chunks"}
      description={
        activeDoc
          ? `${activeDoc.chunks.length} chunks indexed (${activeDoc.mime_type || "text"})`
          : "Viewing indexed document content and chunk boundaries."
      }
    >
      <div className="max-h-[70vh] space-y-5 overflow-y-auto pr-1">
        {loading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="size-6 animate-spin text-accent" />
          </div>
        )}

        {!loading && activeDoc && (
          <section className="rounded-xl border border-border bg-surface/50 p-4">
            <div className="mb-2 flex items-center gap-2">
              <FileText className="size-4 text-accent" />
              <h3 className="font-heading text-sm font-semibold text-text">Indexed document content</h3>
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted">
              {activeDoc.content || "No indexed content found."}
            </p>
          </section>
        )}

        {!loading && activeDoc && activeDoc.chunks.length === 0 && (
          <p className="py-6 text-center text-sm text-muted">No chunks found for this document.</p>
        )}

        {!loading &&
          activeDoc &&
          activeDoc.chunks.map((c) => (
            <div key={c.id} className="rounded-xl border border-border bg-surface/50 p-3.5 transition hover:bg-surface">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-2">
                <div className="flex items-center gap-2">
                  <span className="flex items-center gap-1 font-heading text-xs font-semibold text-accent">
                    <Hash className="size-3" /> Chunk {c.chunk_index}
                  </span>
                  {c.page && (
                    <span className="font-sub rounded-md bg-surface px-2 py-0.5 text-[11px] text-muted">
                      Page {c.page}
                    </span>
                  )}
                </div>
                {c.title && (
                  <span className="max-w-[200px] truncate text-xs font-medium text-text">
                    {c.title}
                  </span>
                )}
              </div>
              <p className="font-sub mt-2.5 whitespace-pre-wrap text-xs leading-relaxed text-muted">
                {c.content}
              </p>
              <div className="mt-2 text-right">
                <span className="font-mono text-[10px] text-muted/60">
                  Hash: {c.chunk_hash.slice(0, 12)}...
                </span>
              </div>
            </div>
          ))}
      </div>
    </Modal>
  );
}
