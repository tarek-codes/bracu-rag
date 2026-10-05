"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthCard, Field, FormError, SubmitButton } from "@/components/auth/AuthCard";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Errors = Partial<Record<"full_name" | "email" | "password" | "confirm", string>>;

export default function RegisterPage() {
  const router = useRouter();
  const { setUser } = useAuth();
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const fullName = String(form.get("full_name")).trim();
    const email = String(form.get("email")).trim();
    const password = String(form.get("password"));
    const confirm = String(form.get("confirm"));

    const next: Errors = {};
    if (!fullName) next.full_name = "Please enter your name.";
    if (!/^\S+@\S+\.\S+$/.test(email)) next.email = "Enter a valid email address.";
    if (password.length < 8) next.password = "Use at least 8 characters.";
    if (confirm !== password) next.confirm = "Passwords do not match.";
    setErrors(next);
    setFormError(null);
    if (Object.keys(next).length) return;

    setLoading(true);
    try {
      // Registration always creates a regular user account. There is no role field.
      await api.register(email, password, fullName);
      const { user } = await api.login(email, password);
      setUser(user);
      router.replace("/chat");
      router.refresh();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not create your account. Please try again.");
      setLoading(false);
    }
  }

  return (
    <AuthCard
      title="Create your account"
      subtitle="Save your conversations and pick up where you left off."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-accent hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <Field id="full_name" label="Full name" autoComplete="name" error={errors.full_name} />
        <Field
          id="email"
          label="Email"
          type="email"
          autoComplete="email"
          placeholder="you@g.bracu.ac.bd"
          error={errors.email}
        />
        <Field id="password" label="Password" type="password" autoComplete="new-password" error={errors.password} />
        <Field id="confirm" label="Confirm password" type="password" autoComplete="new-password" error={errors.confirm} />
        <FormError message={formError} />
        <SubmitButton loading={loading}>Create account</SubmitButton>
      </form>
    </AuthCard>
  );
}
