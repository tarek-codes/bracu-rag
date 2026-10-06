"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Database, LogOut, Menu, MessageSquare, Moon, Sun, Users, X } from "lucide-react";
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

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navItems = [
    { href: "/admin/knowledge", label: "Knowledge Base", icon: Database },
    { href: "/admin/users", label: "Users & Roles", icon: Users },
  ];

  return (
    <div className="flex h-dvh overflow-hidden bg-background flex-col md:flex-row">
      {/* Mobile Admin Header */}
      <div className="flex items-center justify-between border-b border-border bg-surface px-4 py-3 md:hidden">
        <div className="flex items-center gap-2.5">
          <BrandMark size={28} />
          <div>
            <span className="font-heading block text-sm font-semibold tracking-tight">BRACU Admin</span>
            <span className="font-sub block text-[10px] text-muted">Knowledge Manager</span>
          </div>
        </div>
        <button
          onClick={() => setMobileMenuOpen((v) => !v)}
          className="rounded-lg p-2 text-muted hover:bg-surface-hover hover:text-text active:scale-95 transition"
          aria-label="Toggle admin menu"
        >
          {mobileMenuOpen ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
      </div>

      {/* Mobile Drawer Overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-xs md:hidden"
          onClick={() => setMobileMenuOpen(false)}
          aria-hidden
        />
      )}

      {/* Admin Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-[270px] max-w-[85vw] flex-col border-r border-border bg-surface shadow-2xl transition-transform duration-200 ease-out md:static md:z-auto md:w-[260px] md:shadow-none md:translate-x-0 ${
          mobileMenuOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-4 py-4">
          <div className="flex items-center gap-3">
            <BrandMark size={32} />
            <div className="min-w-0 flex-1">
              <span className="font-heading block truncate text-sm font-semibold tracking-tight">
                BRACU Admin
              </span>
              <span className="font-sub block text-[11px] text-muted">Knowledge Manager</span>
            </div>
          </div>
          <button
            onClick={() => setMobileMenuOpen(false)}
            className="rounded-lg p-1.5 text-muted hover:bg-surface-hover hover:text-text md:hidden"
            aria-label="Close menu"
          >
            <X className="size-5" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 px-3 py-2">
          {navItems.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                onClick={() => setMobileMenuOpen(false)}
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
              onClick={() => setMobileMenuOpen(false)}
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
