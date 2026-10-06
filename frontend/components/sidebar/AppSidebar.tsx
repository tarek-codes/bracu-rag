"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  Check,
  Eraser,
  LayoutDashboard,
  LogIn,
  LogOut,
  Moon,
  MoreHorizontal,
  PanelLeftClose,
  Pencil,
  SquarePen,
  Sun,
  Trash2,
} from "lucide-react";
import { BrandMark } from "@/components/BrandMark";
import { ConfirmDialog } from "@/components/ui/Modal";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import type { ChatSession } from "@/lib/types";

function groupSessions(sessions: ChatSession[]): [string, ChatSession[]][] {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const day = 86_400_000;
  const groups: Record<string, ChatSession[]> = { Today: [], Yesterday: [], "Previous 7 days": [], Older: [] };
  for (const s of sessions) {
    const t = new Date(s.updated_at).getTime();
    const key =
      t >= startOfToday.getTime()
        ? "Today"
        : t >= startOfToday.getTime() - day
          ? "Yesterday"
          : t >= startOfToday.getTime() - 7 * day
            ? "Previous 7 days"
            : "Older";
    groups[key].push(s);
  }
  return Object.entries(groups).filter(([, list]) => list.length > 0);
}

function SessionItem({
  session,
  active,
  isSelecting,
  selected,
  onToggleSelect,
  onRename,
  onClear,
  onDelete,
  onNavigate,
}: {
  session: ChatSession;
  active: boolean;
  isSelecting?: boolean;
  selected?: boolean;
  onToggleSelect?: () => void;
  onRename: (title: string) => void;
  onClear: () => void;
  onDelete: () => void;
  onNavigate: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState<"clear" | "delete" | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => !menuRef.current?.contains(e.target as Node) && setMenuOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);

  if (isSelecting) {
    return (
      <button
        type="button"
        onClick={onToggleSelect}
        className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[14px] transition ${
          selected
            ? "bg-accent-soft/80 font-medium text-text"
            : "text-text/85 hover:bg-surface-hover"
        }`}
      >
        <div
          className={`flex size-4 shrink-0 items-center justify-center rounded border transition ${
            selected
              ? "border-accent bg-accent text-white"
              : "border-border bg-background"
          }`}
        >
          {selected && <Check className="size-3 stroke-[3]" />}
        </div>
        <span className="truncate flex-1">{session.title || "New Conversation"}</span>
      </button>
    );
  }

  if (editing) {
    return (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const title = String(new FormData(e.currentTarget).get("title")).trim();
          if (title && title !== session.title) onRename(title);
          setEditing(false);
        }}
      >
        <input
          name="title"
          defaultValue={session.title}
          autoFocus
          maxLength={255}
          onBlur={(e) => e.currentTarget.form?.requestSubmit()}
          onKeyDown={(e) => e.key === "Escape" && setEditing(false)}
          aria-label="Conversation title"
          className="w-full rounded-lg border border-accent bg-background px-2.5 py-1.5 text-sm outline-none"
        />
      </form>
    );
  }

  return (
    <div ref={menuRef} className="group relative">
      <Link
        href={`/chat/${session.id}`}
        onClick={onNavigate}
        aria-current={active ? "page" : undefined}
        className={`block truncate rounded-lg py-2 pl-2.5 pr-8 text-[14px] transition ${
          active ? "bg-accent-soft font-medium text-accent" : "text-text/85 hover:bg-surface-hover"
        }`}
      >
        {session.title || "New Conversation"}
      </Link>
      <button
        onClick={() => setMenuOpen((o) => !o)}
        aria-label={`Options for ${session.title}`}
        aria-expanded={menuOpen}
        className={`absolute right-1 top-1/2 -translate-y-1/2 rounded-md p-1 text-muted hover:text-text ${
          menuOpen || active ? "opacity-100" : "opacity-100 md:opacity-0 md:group-hover:opacity-100"
        }`}
      >
        <MoreHorizontal className="size-4" />
      </button>
      {menuOpen && (
        <div
          role="menu"
          className="fade-up absolute right-0 top-full z-20 mt-1 w-44 overflow-hidden rounded-xl border border-border bg-background p-1 shadow-lg shadow-black/5"
        >
          {[
            { label: "Rename", icon: Pencil, run: () => setEditing(true) },
            { label: "Clear messages", icon: Eraser, run: () => setConfirm("clear") },
            { label: "Delete", icon: Trash2, run: () => setConfirm("delete"), danger: true },
          ].map(({ label, icon: Icon, run, danger }) => (
            <button
              key={label}
              role="menuitem"
              onClick={() => {
                setMenuOpen(false);
                run();
              }}
              className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13.5px] hover:bg-surface ${
                danger ? "text-error" : ""
              }`}
            >
              <Icon className="size-4" aria-hidden />
              {label}
            </button>
          ))}
        </div>
      )}
      <ConfirmDialog
        open={confirm === "delete"}
        onClose={() => setConfirm(null)}
        onConfirm={onDelete}
        title="Delete conversation?"
        description={`"${session.title}" and all its messages will be permanently deleted.`}
        confirmLabel="Delete"
      />
      <ConfirmDialog
        open={confirm === "clear"}
        onClose={() => setConfirm(null)}
        onConfirm={onClear}
        title="Clear messages?"
        description="All messages in this conversation will be removed. The conversation itself stays."
        confirmLabel="Clear"
      />
    </div>
  );
}

export function AppSidebar({
  sessions,
  loading,
  activeId,
  mobileOpen,
  onCloseMobile,
  onCollapse,
  onNewChat,
  onRename,
  onClear,
  onDelete,
  onBulkDelete,
}: {
  sessions: ChatSession[];
  loading: boolean;
  activeId: string | null;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  onCollapse: () => void;
  onNewChat: () => void;
  onRename: (id: string, title: string) => void;
  onClear: (id: string) => void;
  onDelete: (id: string) => void;
  onBulkDelete: (ids: string[]) => void;
}) {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const [isSelecting, setIsSelecting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [confirmBulk, setConfirmBulk] = useState(false);

  useEffect(() => {
    if (sessions.length === 0 && isSelecting) {
      setIsSelecting(false);
      setSelectedIds(new Set());
    }
  }, [sessions.length, isSelecting]);

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    if (selectedIds.size === sessions.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(sessions.map((s) => s.id)));
    }
  };

  const handleBulkDelete = () => {
    if (selectedIds.size === 0) return;
    onBulkDelete(Array.from(selectedIds));
    setSelectedIds(new Set());
    setIsSelecting(false);
    setConfirmBulk(false);
  };

  const initials = (user?.full_name || user?.email || "?")
    .split(/[\s@]/)
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase())
    .join("");

  return (
    <>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 backdrop-blur-xs transition-opacity duration-200 md:hidden animate-fade-in"
          onClick={onCloseMobile}
          aria-hidden
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[285px] max-w-[85vw] flex-col border-r border-border bg-surface shadow-2xl transition-transform duration-200 ease-out md:static md:z-auto md:w-[260px] md:shadow-none md:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-label="Conversations"
      >
        <div className="flex items-center justify-between px-3 pb-2 pt-3.5">
          <Link
            href="/chat"
            onClick={() => {
              if (isSelecting) setIsSelecting(false);
              onNewChat();
            }}
            className="flex items-center gap-2.5 rounded-lg px-1 py-1"
          >
            <BrandMark size={28} />
            <span className="font-heading text-[15px] font-semibold tracking-tight">BRACU Assistant</span>
          </Link>
          <button
            onClick={() => (mobileOpen ? onCloseMobile() : onCollapse())}
            className="rounded-lg p-1.5 text-muted hover:bg-surface-hover hover:text-text"
            aria-label="Close sidebar"
          >
            <PanelLeftClose className="size-[18px]" />
          </button>
        </div>

        <div className="px-3 py-2 flex items-center gap-2">
          <Link
            id="new-chat-button"
            href="/chat"
            onClick={() => {
              if (isSelecting) setIsSelecting(false);
              onNewChat();
            }}
            className="flex-1 flex items-center gap-2.5 rounded-xl border border-border bg-background px-3 py-2.5 text-[14px] font-medium transition hover:border-accent/30 hover:text-accent"
          >
            <SquarePen className="size-4" aria-hidden />
            New chat
          </Link>
          {user && sessions.length > 0 && (
            <button
              type="button"
              id="bulk-select-toggle"
              onClick={() => {
                setIsSelecting(!isSelecting);
                setSelectedIds(new Set());
              }}
              title={isSelecting ? "Cancel selection" : "Select multiple conversations"}
              className={`rounded-xl border px-3 py-2.5 text-[13px] font-medium transition flex items-center justify-center shrink-0 ${
                isSelecting
                  ? "border-accent bg-accent-soft text-accent"
                  : "border-border bg-background text-muted hover:text-text hover:bg-surface-hover"
              }`}
            >
              {isSelecting ? "Cancel" : "Select"}
            </button>
          )}
        </div>

        {isSelecting && (
          <div className="mx-3 mb-2 flex items-center justify-between rounded-xl border border-border bg-background px-2.5 py-2 text-xs">
            <button
              type="button"
              id="select-all-chats"
              onClick={selectAll}
              className="font-medium text-accent hover:underline"
            >
              {selectedIds.size === sessions.length ? "Deselect all" : "Select all"}
            </button>
            <div className="flex items-center gap-1.5">
              <span className="text-muted font-medium">
                {selectedIds.size} selected
              </span>
              <button
                type="button"
                id="bulk-delete-confirm-button"
                disabled={selectedIds.size === 0}
                onClick={() => setConfirmBulk(true)}
                className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-error transition hover:bg-error/10 disabled:opacity-40 disabled:hover:bg-transparent"
              >
                <Trash2 className="size-3.5" />
                Delete
              </button>
            </div>
          </div>
        )}

        <nav className="flex-1 overflow-y-auto px-3 pb-3">
          {!user ? (
            <div className="font-sub mt-4 rounded-xl border border-dashed border-border p-4 text-[14px] text-muted">
              <p>Sign in to save conversations and see your history here.</p>
              <Link href="/login" className="font-heading mt-3 inline-flex items-center gap-1.5 text-[13px] font-medium text-accent hover:underline">
                <LogIn className="size-3.5" /> Sign in
              </Link>
            </div>
          ) : loading ? (
            <div className="mt-4 space-y-2">
              {[70, 55, 80, 60].map((w) => (
                <div key={w} className="h-7 animate-pulse rounded-lg bg-surface-hover" style={{ width: `${w}%` }} />
              ))}
            </div>
          ) : sessions.length === 0 ? (
            <p className="font-sub mt-4 px-2.5 text-[13.5px] text-muted">No conversations yet.</p>
          ) : (
            groupSessions(sessions).map(([label, list]) => (
              <div key={label} className="mt-4">
                <p className="font-sub mb-1 px-2.5 text-[12px] font-medium text-muted">{label}</p>
                <div className="space-y-0.5">
                  {list.map((s) => (
                    <SessionItem
                      key={s.id}
                      session={s}
                      active={s.id === activeId}
                      isSelecting={isSelecting}
                      selected={selectedIds.has(s.id)}
                      onToggleSelect={() => toggleSelect(s.id)}
                      onNavigate={onCloseMobile}
                      onRename={(t) => onRename(s.id, t)}
                      onClear={() => onClear(s.id)}
                      onDelete={() => onDelete(s.id)}
                    />
                  ))}
                </div>
              </div>
            ))
          )}
        </nav>

        <ConfirmDialog
          open={confirmBulk}
          onClose={() => setConfirmBulk(false)}
          onConfirm={handleBulkDelete}
          title={`Delete ${selectedIds.size} conversation${selectedIds.size === 1 ? "" : "s"}?`}
          description={`The selected ${selectedIds.size} conversation${selectedIds.size === 1 ? "" : "s"} and all associated messages will be permanently deleted.`}
          confirmLabel={`Delete ${selectedIds.size}`}
        />

        <div className="border-t border-border p-3">
          {user && (
            <div className="mb-2 flex items-center gap-2.5 px-1">
              <span className="font-heading flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent">
                {initials}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13.5px] font-medium">{user.full_name || user.email}</p>
                <p className="font-sub truncate text-[12px] text-muted">
                  {user.role === "admin" ? "Administrator" : user.email}
                </p>
              </div>
            </div>
          )}
          <div className="flex items-center gap-1">
            <button
              onClick={toggle}
              className="flex flex-1 items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] text-muted hover:bg-surface-hover hover:text-text"
              aria-label="Toggle theme"
            >
              {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
              {theme === "dark" ? "Light" : "Dark"}
            </button>
            {user?.role === "admin" && (
              <Link
                href="/admin/knowledge"
                className="flex flex-1 items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] text-muted hover:bg-surface-hover hover:text-text"
              >
                <LayoutDashboard className="size-4" /> Admin
              </Link>
            )}
            {user ? (
              <button
                onClick={logout}
                className="flex flex-1 items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] text-muted hover:bg-surface-hover hover:text-error"
              >
                <LogOut className="size-4" /> Sign out
              </button>
            ) : (
              <Link
                href="/register"
                className="flex flex-1 items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] text-muted hover:bg-surface-hover hover:text-text"
              >
                <LogIn className="size-4" /> Register
              </Link>
            )}
          </div>
        </div>
      </aside>
    </>
  );
}
