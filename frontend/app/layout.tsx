import type { Metadata } from "next";
import { Space_Grotesk } from "next/font/google";
import "./globals.css";
import { Navbar } from "@/components/navbar";
import { AuthProvider } from "@/lib/auth";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-sans"
});

export const metadata: Metadata = {
  title: "NJDOT Assistant",
  description: "Enterprise knowledge assistant for NJDOT"
};

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={spaceGrotesk.variable}>
      <body className="min-h-screen">
        <AuthProvider>
          <div className="min-h-screen bg-[radial-gradient(circle_at_top,_#ffffff_0%,_#eef3fb_45%,_#d8e4f5_100%)]">
            <Navbar />
            <main className="mx-auto w-full max-w-6xl px-6 pb-16 pt-8">
              {children}
            </main>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
