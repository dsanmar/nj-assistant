"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { supabase } from "@/lib/supabaseClient";
import { useAuth } from "@/lib/auth";
import { AuthCard } from "@/components/auth/AuthCard";
import { Button } from "@/components/ui/button";

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectedFrom = searchParams.get("redirectedFrom") || "/chat";
  const { session, loading: authLoading } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && session) {
      router.replace(redirectedFrom);
    }
  }, [authLoading, session, redirectedFrom, router]);

  const handleSignIn = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError(null);

    const result = await supabase.auth.signInWithPassword({ email, password });
    if (result.error) {
      setError(result.error.message);
      setLoading(false);
      return;
    }

    router.push(redirectedFrom);
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
          subtitle="Sign in to your account"
          footer={
            <span>
              Don&apos;t have an account?{" "}
              <Link href="/register" className="font-semibold text-ink-900">
                Create one
              </Link>
            </span>
          }
        >
          <form className="space-y-5" onSubmit={handleSignIn}>
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
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-ink-900 shadow-soft-sm focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
                placeholder="Enter your password"
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
              {loading ? "Signing in..." : "Sign In"}
            </Button>
          </form>
        </AuthCard>
      </div>
    </div>
  );
}
