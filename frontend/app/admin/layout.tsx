"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Database, LogOut, MessageSquare, Moon, Sun, Users } from "lucide-react";
import { BrandMark } from "@/components/BrandMark";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && user?.role !== "admin") {
      router.replace(user ? "/chat" : "/login?returnUrl=/admin/knowledge");
    }
  }, [loading, user, router]);

  if (loading || user?.role !== "admin") {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      </div>
    );
  }

  const navItems = [
    { href: "/admin/knowledge", label: "Knowledge Base", icon: Database },
    { href: "/admin/users", label: "Users & Roles", icon: Users },
  ];

  return (
    <div className="flex h-dvh overflow-hidden bg-background">
      {/* Admin Sidebar */}
      <aside className="flex w-[260px] shrink-0 flex-col border-r border-border bg-surface">
        <div className="flex items-center gap-3 px-4 py-4">
          <BrandMark size={32} />
          <div className="min-w-0 flex-1">
            <span className="font-heading block truncate text-sm font-semibold tracking-tight">
              BRACU Admin
            </span>
            <span className="font-sub block text-[11px] text-muted">Knowledge Manager</span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 px-3 py-2">
          {navItems.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                  active
                    ? "bg-accent-soft text-accent font-semibold"
                    : "text-muted hover:bg-surface-hover hover:text-text"
                }`}
              >
                <Icon className="size-4 shrink-0" aria-hidden />
                {label}
              </Link>
            );
          })}

          <div className="pt-3">
            <div className="my-2 border-t border-border" />
            <Link
              href="/chat"
              className="flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm text-muted transition hover:bg-surface-hover hover:text-text"
            >
              <MessageSquare className="size-4 shrink-0" aria-hidden />
              Switch to Student Chat
            </Link>
          </div>
        </nav>

        {/* Footer */}
        <div className="border-t border-border p-3">
          <div className="mb-2 flex items-center gap-2.5 px-1">
            <span className="font-heading flex size-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent">
              {(user.full_name || user.email)[0]?.toUpperCase()}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium">{user.full_name || user.email}</p>
              <span className="inline-block rounded bg-accent/10 px-1.5 py-0.2 text-[10px] font-medium text-accent">
                Admin
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={toggle}
              className="flex flex-1 items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-muted hover:bg-surface-hover hover:text-text"
            >
              {theme === "dark" ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
              {theme === "dark" ? "Light" : "Dark"}
            </button>
            <button
              onClick={logout}
              className="flex flex-1 items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-muted hover:bg-surface-hover hover:text-error"
            >
              <LogOut className="size-3.5" /> Sign out
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
