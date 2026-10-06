"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { PanelLeftOpen, SquarePen } from "lucide-react";
import { ChatWorkspace } from "@/components/chat/ChatWorkspace";
import { AppSidebar } from "@/components/sidebar/AppSidebar";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ChatSession } from "@/lib/types";

/**
 * The chat shell lives in the layout so the sidebar and the active stream survive
 * navigation between /chat and /chat/[id]. The pages themselves render nothing.
 */
export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const params = useParams<{ id?: string }>();
  const activeId = params.id ?? null;
  const { user, loading: authLoading } = useAuth();

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [workspaceKey, setWorkspaceKey] = useState(0);
  // The session this workspace instance created. Moving to its URL must not remount (the stream is live).
  const [pinnedId, setPinnedId] = useState<string | null>(null);
  const conversationKey = activeId && activeId !== pinnedId ? activeId : "fresh";

  const refreshSessions = useCallback(() => {
    if (!user) return;
    api
      .listSessions()
      .then((list) => setSessions(list.filter((s) => s.user_id === user.id)))
      .catch(() => undefined)
      .finally(() => setSessionsLoading(false));
  }, [user]);

  useEffect(() => {
    if (!authLoading) refreshSessions();
  }, [authLoading, refreshSessions]);

  const newChat = useCallback(() => {
    setMobileOpen(false);
    setPinnedId(null);
    setWorkspaceKey((k) => k + 1);
  }, []);

  const onSessionCreated = useCallback(
    (id: string) => {
      // Only signed in users have a saved conversation URL to move to.
      if (user) {
        setPinnedId(id);
        router.replace(`/chat/${id}`);
      }
    },
    [router, user],
  );

  const rename = async (id: string, title: string) => {
    setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, title } : s)));
    await api.renameSession(id, title).catch(refreshSessions);
  };

  const clear = async (id: string) => {
    await api.clearSession(id).catch(() => undefined);
    if (id === activeId) setWorkspaceKey((k) => k + 1);
    refreshSessions();
  };

  const remove = async (id: string) => {
    setSessions((prev) => prev.filter((s) => s.id !== id));
    await api.deleteSession(id).catch(refreshSessions);
    if (id === activeId) {
      router.push("/chat");
      setWorkspaceKey((k) => k + 1);
    }
  };

  const bulkRemove = async (ids: string[]) => {
    if (ids.length === 0) return;
    const idsSet = new Set(ids);
    setSessions((prev) => prev.filter((s) => !idsSet.has(s.id)));
    await api.bulkDeleteSessions(ids).catch(refreshSessions);
    if (activeId && idsSet.has(activeId)) {
      router.push("/chat");
      setWorkspaceKey((k) => k + 1);
    }
  };

  return (
    <div className="flex h-dvh overflow-hidden">
      <div className={collapsed ? "md:hidden" : "contents"}>
        <AppSidebar
          sessions={sessions}
          loading={authLoading || (!!user && sessionsLoading)}
          activeId={activeId}
          mobileOpen={mobileOpen}
          onCloseMobile={() => setMobileOpen(false)}
          onCollapse={() => setCollapsed(true)}
          onNewChat={newChat}
          onRename={rename}
          onClear={clear}
          onDelete={remove}
          onBulkDelete={bulkRemove}
        />
      </div>

      <main className="relative flex min-w-0 flex-1">
        {collapsed && (
          <div className="absolute left-3 top-3 z-10 hidden gap-1 md:flex">
            <button
              onClick={() => setCollapsed(false)}
              className="rounded-lg p-2 text-muted hover:bg-surface hover:text-text"
              aria-label="Open sidebar"
            >
              <PanelLeftOpen className="size-[18px]" />
            </button>
            <button
              onClick={() => {
                router.push("/chat");
                newChat();
              }}
              className="rounded-lg p-2 text-muted hover:bg-surface hover:text-text"
              aria-label="New chat"
            >
              <SquarePen className="size-[18px]" />
            </button>
          </div>
        )}
        <ChatWorkspace
          key={`${workspaceKey}:${conversationKey}`}
          sessionId={activeId}
          signedIn={!!user}
          onSessionCreated={onSessionCreated}
          onTurnComplete={refreshSessions}
          onOpenSidebar={() => setMobileOpen(true)}
        />
        {children}
      </main>
    </div>
  );
}
