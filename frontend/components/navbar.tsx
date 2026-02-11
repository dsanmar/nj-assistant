"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import logo from "@/components/img/njdot_logo.png";

const baseLinks = [
  { href: "/chat", label: "Chatbot" },
  { href: "/documents", label: "Library" },
  { href: "/help", label: "Help" }
];

export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { session, signOut } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  if (pathname === "/login" || pathname === "/register") {
    return null;
  }

  const role =
    session?.user?.app_metadata?.role ?? session?.user?.user_metadata?.role;
  const isAdmin = role === "admin";
  const links = isAdmin
    ? [...baseLinks, { href: "/admin", label: "Admin" }]
    : baseLinks;

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white">
      <div className="mx-auto flex h-[72px] w-full max-w-6xl items-center px-6">
        <Link href="/" className="flex items-center gap-3">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-white">
            <Image
              src={logo}
              alt="NJDOT logo"
              width={52}
              height={52}
              className="h-12 w-12"
              priority
            />
          </div>
          <div className="text-lg font-semibold text-ink-900">NJDOT</div>
        </Link>
        <div className="ml-auto hidden items-center gap-10 md:flex">
          <nav className="flex items-center gap-10 text-sm font-medium text-ink-700">
            {links.map((link) => {
              const isActive = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`border-b-2 pb-1 ${
                    isActive ? "border-ink-900 text-ink-900" : "border-transparent"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
          {session ? (
            <Button
              variant="secondary"
              size="sm"
              type="button"
              onClick={async () => {
                await signOut();
                router.push("/login");
                router.refresh();
              }}
            >
              Logout
            </Button>
          ) : (
            <Button
              asChild
              size="sm"
              className="rounded-xl bg-red-600 px-5 text-white hover:bg-red-700"
            >
              <Link href="/login">Login</Link>
            </Button>
          )}
        </div>
        <button
          type="button"
          className="inline-flex items-center justify-center rounded-lg border border-slate-200 p-2 text-ink-700 md:hidden"
          aria-label="Toggle navigation"
          onClick={() => setMenuOpen((open) => !open)}
        >
          <span className="block h-0.5 w-5 rounded bg-ink-700" />
          <span className="mt-1 block h-0.5 w-5 rounded bg-ink-700" />
          <span className="mt-1 block h-0.5 w-5 rounded bg-ink-700" />
        </button>
      </div>
      {menuOpen ? (
        <div className="border-t border-slate-200 bg-white md:hidden">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-6 py-4 text-sm font-medium text-ink-700">
            {links.map((link) => (
              <Link key={link.href} href={link.href}>
                {link.label}
              </Link>
            ))}
            {session ? (
              <Button
                variant="secondary"
                size="sm"
                type="button"
                onClick={async () => {
                  await signOut();
                  router.push("/login");
                  router.refresh();
                }}
              >
                Logout
              </Button>
            ) : (
              <Button
                asChild
                size="sm"
                className="rounded-xl bg-red-600 px-5 text-white hover:bg-red-700"
              >
                <Link href="/login">Login</Link>
              </Button>
            )}
          </div>
        </div>
      ) : null}
    </header>
  );
}
