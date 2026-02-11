"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { supabase } from "@/lib/supabaseClient";
import { AuthCard } from "@/components/auth/AuthCard";
import { Button } from "@/components/ui/button";

export default function RegisterPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRegister = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    if (password.length < 8) {
      setError("Use at least 8 characters.");
      return;
    }

    setLoading(true);

    const result = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          display_name: fullName.trim()
        }
      }
    });

    if (result.error) {
      setError(result.error.message);
      setLoading(false);
      return;
    }

    router.push("/login");
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-[#f6f7fb]">
      <div className="mx-auto w-full max-w-6xl px-6 pt-8">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-sm font-medium text-ink-700"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to Home
        </Link>
      </div>

      <div className="mx-auto flex min-h-[calc(100vh-96px)] w-full max-w-6xl items-start justify-center px-6 pb-16 pt-10 sm:pt-16">
        <AuthCard
          subtitle="Create your account"
          footer={
            <span>
              Already have an account?{" "}
              <Link href="/login" className="font-semibold text-ink-900">
                Sign in
              </Link>
            </span>
          }
        >
          <form className="space-y-5" onSubmit={handleRegister}>
            <div className="space-y-2">
              <label
                htmlFor="fullName"
                className="text-sm font-semibold text-ink-700"
              >
                Full name
              </label>
              <input
                id="fullName"
                type="text"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-ink-900 shadow-soft-sm focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
                placeholder="Enter your name"
              />
            </div>

            <div className="space-y-2">
              <label
                htmlFor="email"
                className="text-sm font-semibold text-ink-700"
              >
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-ink-900 shadow-soft-sm focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
                placeholder="Enter your email"
              />
            </div>

            <div className="space-y-2">
              <label
                htmlFor="password"
                className="text-sm font-semibold text-ink-700"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-ink-900 shadow-soft-sm focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
                placeholder="Create a password"
              />
              <p className="text-xs text-ink-500">Use at least 8 characters.</p>
            </div>

            <div className="space-y-2">
              <label
                htmlFor="confirmPassword"
                className="text-sm font-semibold text-ink-700"
              >
                Confirm password
              </label>
              <input
                id="confirmPassword"
                type="password"
                autoComplete="new-password"
                required
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-ink-900 shadow-soft-sm focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
                placeholder="Confirm your password"
              />
            </div>

            {error ? (
              <p
                className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700"
                role="status"
                aria-live="polite"
              >
                {error}
              </p>
            ) : null}

            <Button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-red-600 py-6 text-base font-semibold text-white hover:bg-red-700"
            >
              {loading ? "Creating..." : "Create Account"}
            </Button>
          </form>
        </AuthCard>
      </div>
    </div>
  );
}
