"use client";

import Image from "next/image";
import logo from "@/components/img/njdot_logo.png";

type AuthCardProps = {
  subtitle: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
};

export function AuthCard({ subtitle, children, footer }: AuthCardProps) {
  return (
    <div className="w-full max-w-xl rounded-2xl bg-white p-8 shadow-soft-xl sm:p-10">
      <div className="flex flex-col items-center text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white">
          <Image
            src={logo}
            alt="NJDOT logo"
            width={48}
            height={48}
            className="h-12 w-12"
            priority
          />
        </div>
        <h1 className="mt-5 text-2xl font-semibold text-ink-900 sm:text-3xl">
          NJDOT Knowledge Hub
        </h1>
        <p className="mt-2 text-sm text-ink-600 sm:text-base">{subtitle}</p>
      </div>
      <div className="mt-8">{children}</div>
      {footer ? (
        <div className="mt-6 text-center text-sm text-ink-600">{footer}</div>
      ) : null}
    </div>
  );
}
