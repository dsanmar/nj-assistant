import Image from "next/image";
import Link from "next/link";
import { MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import heroImage from "@/components/img/buildings.jpg";

export default function HomePage() {
  return (
    <section className="relative left-1/2 right-1/2 w-screen -ml-[50vw] -mr-[50vw] -mt-8 -mb-16 overflow-hidden">
      <div className="relative h-[calc(100vh-72px)] w-full">
        <Image
          src={heroImage}
          alt="NJDOT Knowledge Hub background"
          fill
          className="object-cover"
          priority
        />
        <div className="absolute inset-0 bg-black/70" />
        <div className="absolute inset-0 flex items-center">
          <div className="mx-auto w-full max-w-6xl px-6">
            <div className="max-w-2xl space-y-6 text-white">
              <h1 className="text-4xl font-semibold leading-tight sm:text-5xl lg:text-6xl">
                NJDOT Knowledge Hub
              </h1>
              <p className="text-base text-white/90 sm:text-lg">
                Ask questions and get answers grounded in official specifications,
                manuals, and material procedures
              </p>
              <Button
                asChild
                className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-6 py-6 text-base font-semibold text-white hover:bg-red-700"
              >
                <Link href="/chat">
                  <MessageSquare className="h-5 w-5" aria-hidden="true" />
                  Launch Chatbot
                </Link>
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
