"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthCard, Field, FormError, SubmitButton } from "@/components/auth/AuthCard";
import { api } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";

function safeReturnUrl(role: "admin" | "user"): string | null {
  const url = new URLSearchParams(window.location.search).get("returnUrl");
  if (!url || !url.startsWith("/") || url.startsWith("//")) return null;
  if (url.startsWith("/admin") && role !== "admin") return null;
  return url;
}

export default function LoginPage() {
  const router = useRouter();
  const { setUser } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setLoading(true);
    setError(null);
    try {
      const { user } = await api.login(String(form.get("email")), String(form.get("password")));
      setUser(user);
      router.replace(safeReturnUrl(user.role) ?? homeFor(user));
      router.refresh();
    } catch {
      // Generic on purpose: never reveal which part was wrong or the account type.
      setError("Invalid email or password");
      setLoading(false);
    }
  }

  return (
    <AuthCard
      title="Welcome back"
      subtitle="Sign in to continue your conversations."
      footer={
        <>
          New here?{" "}
          <Link href="/register" className="font-medium text-accent hover:underline">
            Create an account
          </Link>
          <span className="mx-2 text-border">|</span>
          <Link href="/chat" className="hover:text-text">
            Continue as guest
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <Field id="email" label="Email" type="email" autoComplete="email" placeholder="you@g.bracu.ac.bd" required />
        <Field id="password" label="Password" type="password" autoComplete="current-password" required />
        <FormError message={error} />
        <SubmitButton loading={loading}>Sign in</SubmitButton>
      </form>
    </AuthCard>
  );
}
