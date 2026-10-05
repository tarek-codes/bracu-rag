"use client";

import Link from "next/link";
import { Loader2 } from "lucide-react";
import { BrandMark } from "@/components/BrandMark";

export function AuthCard({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  footer: React.ReactNode;
}) {
  return (
    <main className="flex min-h-full items-center justify-center px-4 py-12">
      <div className="fade-up w-full max-w-[380px]">
        <Link href="/chat" className="mb-8 flex items-center justify-center gap-2.5" aria-label="BRACU Assistant home">
          <BrandMark size={36} />
          <span className="font-heading text-lg font-semibold tracking-tight">BRACU Assistant</span>
        </Link>
        <div className="rounded-2xl border border-border bg-background p-7 sm:bg-surface/40">
          <h1 className="font-heading text-xl font-semibold tracking-tight">{title}</h1>
          <p className="font-sub mt-1 text-[15px] text-muted">{subtitle}</p>
          <div className="mt-6">{children}</div>
        </div>
        <p className="font-sub mt-6 text-center text-[15px] text-muted">{footer}</p>
      </div>
    </main>
  );
}

export function Field({
  id,
  label,
  error,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { id: string; label: string; error?: string }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <input
        id={id}
        name={id}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-error` : undefined}
        className={`font-sub w-full rounded-xl border bg-background px-3.5 py-2.5 text-[15px] outline-none transition placeholder:text-muted/70 focus:border-accent focus:ring-2 focus:ring-accent/20 ${
          error ? "border-error" : "border-border"
        }`}
        {...props}
      />
      {error && (
        <p id={`${id}-error`} className="font-sub text-[13px] text-error">
          {error}
        </p>
      )}
    </div>
  );
}

export function SubmitButton({ loading, children }: { loading: boolean; children: React.ReactNode }) {
  return (
    <button
      type="submit"
      disabled={loading}
      className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-[15px] font-medium text-accent-fg transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-70"
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="font-sub rounded-lg border border-error/30 bg-error/5 px-3 py-2 text-sm text-error">
      {message}
    </p>
  );
}
