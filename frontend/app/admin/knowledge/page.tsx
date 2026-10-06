"use client";

import { useCallback, useEffect, useState } from "react";
import {
  FileText,
  Globe,
  RefreshCw,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import { ChunkInspectionModal } from "@/components/admin/ChunkInspectionModal";
import { JobsSection } from "@/components/admin/JobsSection";
import { UploadModal } from "@/components/admin/UploadModal";
import { UrlCrawlModal } from "@/components/admin/UrlCrawlModal";
import { Button, ConfirmDialog } from "@/components/ui/Modal";
import { api } from "@/lib/api";
import type { DocumentItem } from "@/lib/types";

export default function KnowledgeBasePage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [urlOpen, setUrlOpen] = useState(false);
  const [inspectDocId, setInspectDocId] = useState<string | null>(null);
  const [deleteDoc, setDeleteDoc] = useState<DocumentItem | null>(null);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<Set<string>>(new Set());
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [reindexingId, setReindexingId] = useState<string | null>(null);

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.listDocuments(search, 0, 100);
      setDocuments(res.documents);
      setTotal(res.total);
    } catch {
      // Non-blocking error handling
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadDocuments();
    }, 250);
    return () => clearTimeout(timer);
  }, [loadDocuments]);

  async function handleReindex(docId: string) {
    setReindexingId(docId);
    try {
      await api.reindexDocument(docId);
      await loadDocuments();
    } catch {
      // Non-blocking
    } finally {
      setReindexingId(null);
    }
  }

  async function handleDelete() {
    if (!deleteDoc) return;
    try {
      await api.deleteDocument(deleteDoc.id);
      await loadDocuments();
    } catch {
      // Non-blocking
    } finally {
      setDeleteDoc(null);
    }
  }

  async function handleBulkDelete() {
    if (selectedDocumentIds.size === 0) return;
    try {
      await api.bulkDeleteDocuments([...selectedDocumentIds]);
      setSelectedDocumentIds(new Set());
      await loadDocuments();
    } catch {
      // Non-blocking
    }
  }

  const allDocumentsSelected =
    documents.length > 0 && documents.every((document) => selectedDocumentIds.has(document.id));

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight">Knowledge Base</h1>
          <p className="font-sub mt-1 text-sm text-muted">
            Manage university documents, crawl institutional pages, and inspect vector chunks.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Button variant="ghost" onClick={() => setUrlOpen(true)} className="flex items-center gap-2">
            <Globe className="size-4" /> Index URL
          </Button>
          <Button onClick={() => setUploadOpen(true)} className="flex items-center gap-2">
            <Upload className="size-4" /> Upload Document
          </Button>
        </div>
      </div>

      {/* Jobs section */}
      <JobsSection onJobFinished={loadDocuments} />

      {/* Filter and Search Bar */}
      <div className="flex items-center justify-between gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search documents by title or path..."
            className="font-sub w-full rounded-xl border border-border bg-background py-2 pl-10 pr-4 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
          />
        </div>
        <span className="font-sub text-xs text-muted">
          Total: <strong className="text-text">{total}</strong> documents
        </span>
      </div>

      {selectedDocumentIds.size > 0 && (
        <div className="flex items-center justify-between rounded-xl border border-error/30 bg-error/5 px-4 py-3">
          <span className="text-sm text-error">
            {selectedDocumentIds.size} document{selectedDocumentIds.size === 1 ? "" : "s"} selected
          </span>
          <Button variant="danger" onClick={() => setBulkDeleteOpen(true)} className="text-xs">
            Delete Selected
          </Button>
        </div>
      )}

      {/* Documents Table */}
      <div className="overflow-hidden rounded-2xl border border-border bg-background shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-surface text-xs font-semibold text-muted uppercase tracking-wider">
              <tr>
                <th className="w-12 px-5 py-3.5">
                  <input
                    type="checkbox"
                    checked={allDocumentsSelected}
                    onChange={(event) => {
                      setSelectedDocumentIds(
                        event.target.checked ? new Set(documents.map((document) => document.id)) : new Set(),
                      );
                    }}
                    aria-label="Select all visible documents"
                  />
                </th>
                <th className="px-5 py-3.5">Document</th>
                <th className="px-4 py-3.5">Source Type</th>
                <th className="px-4 py-3.5 text-center">Chunks</th>
                <th className="px-4 py-3.5">Last Updated</th>
                <th className="px-5 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {loading && documents.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center text-muted">
                    Loading knowledge documents...
                  </td>
                </tr>
              ) : documents.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center text-muted">
                    <p className="font-medium">No documents found.</p>
                    <p className="font-sub mt-1 text-xs">
                      Upload a file or add a public web URL to start building the knowledge base.
                    </p>
                  </td>
                </tr>
              ) : (
                documents.map((doc) => {
                  const isUrl = doc.source === "url" || doc.source_path?.startsWith("http");
                  const SourceIcon = isUrl ? Globe : FileText;
                  const isReindexing = reindexingId === doc.id;

                  return (
                    <tr key={doc.id} className="transition hover:bg-surface/50">
                      <td className="px-5 py-4">
                        <input
                          type="checkbox"
                          checked={selectedDocumentIds.has(doc.id)}
                          onChange={(event) => {
                            setSelectedDocumentIds((current) => {
                              const next = new Set(current);
                              if (event.target.checked) next.add(doc.id);
                              else next.delete(doc.id);
                              return next;
                            });
                          }}
                          aria-label={`Select ${doc.title}`}
                        />
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <div className="rounded-lg bg-surface p-2 text-accent">
                            <SourceIcon className="size-4 shrink-0" />
                          </div>
                          <div className="min-w-0 max-w-md">
                            <button
                              type="button"
                              onClick={() => setInspectDocId(doc.id)}
                              className="font-heading block max-w-full truncate text-left text-sm font-semibold text-text hover:text-accent hover:underline"
                            >
                              {doc.title}
                            </button>
                            <p className="font-sub truncate text-xs text-muted" title={doc.source_path || ""}>
                              {doc.source_path || "Uploaded document"}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-4">
                        <span className="font-sub inline-block rounded-md bg-surface px-2.5 py-1 text-xs font-medium text-text">
                          {isUrl ? "Web URL" : doc.mime_type?.split("/")[1]?.toUpperCase() || "File"}
                        </span>
                      </td>
                      <td className="px-4 py-4 text-center">
                        <button
                          onClick={() => setInspectDocId(doc.id)}
                          className="font-heading rounded-md bg-accent-soft px-2.5 py-1 text-xs font-semibold text-accent hover:underline"
                        >
                          {doc.chunks_count} chunks
                        </button>
                      </td>
                      <td className="px-4 py-4 text-xs text-muted whitespace-nowrap">
                        <div>
                          {new Date(doc.updated_at).toLocaleDateString(undefined, {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                          })}
                        </div>
                        <div className="font-sub text-[11px] text-muted/80">
                          {new Date(doc.updated_at).toLocaleTimeString(undefined, {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </div>
                      </td>
                      <td className="px-5 py-4 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleReindex(doc.id)}
                            disabled={isReindexing}
                            title="Re-index document"
                            className="rounded-lg p-1.5 text-muted hover:bg-surface hover:text-accent disabled:opacity-50"
                          >
                            <RefreshCw className={`size-4 ${isReindexing ? "animate-spin text-accent" : ""}`} />
                          </button>
                          <button
                            onClick={() => setDeleteDoc(doc)}
                            title="Delete document"
                            className="rounded-lg p-1.5 text-muted hover:bg-surface hover:text-error"
                          >
                            <Trash2 className="size-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modals */}
      <UploadModal open={uploadOpen} onClose={() => setUploadOpen(false)} onUploaded={loadDocuments} />
      <UrlCrawlModal open={urlOpen} onClose={() => setUrlOpen(false)} onQueued={loadDocuments} />
      <ChunkInspectionModal
        documentId={inspectDocId}
        open={!!inspectDocId}
        onClose={() => setInspectDocId(null)}
      />
      <ConfirmDialog
        open={!!deleteDoc}
        onClose={() => setDeleteDoc(null)}
        onConfirm={handleDelete}
        title="Delete Document?"
        description={`"${deleteDoc?.title}" and its ${deleteDoc?.chunks_count || 0} vector chunks will be permanently removed.`}
        confirmLabel="Delete Document"
      />
      <ConfirmDialog
        open={bulkDeleteOpen}
        onClose={() => setBulkDeleteOpen(false)}
        onConfirm={handleBulkDelete}
        title="Delete Selected Documents?"
        description={`${selectedDocumentIds.size} selected document${selectedDocumentIds.size === 1 ? "" : "s"} and all associated vector chunks will be permanently deleted.`}
        confirmLabel="Delete Selected"
      />
    </div>
  );
}
