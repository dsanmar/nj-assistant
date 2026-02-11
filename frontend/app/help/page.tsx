"use client";

import {
  CheckCircle,
  Info,
  MessageCircle,
  TrendingUp,
  XCircle
} from "lucide-react";

export default function HelpPage() {
  return (
    <div className="min-h-screen bg-[#f6f7fb] pb-16 pt-10 sm:pt-14">
      <div className="mx-auto w-full max-w-5xl px-6">
        <div className="space-y-2">
          <h1 className="text-3xl font-semibold text-ink-900 sm:text-4xl">
            Help &amp; Documentation
          </h1>
          <p className="text-sm text-ink-600 sm:text-base">
            Learn how to get the most out of the Knowledge Hub
          </p>
        </div>

        <div className="mt-8 space-y-6">
          <section className="rounded-2xl border border-slate-100 bg-white p-8 shadow-soft-md">
            <h2 className="text-lg font-semibold text-ink-900">
              What This Assistant Does
            </h2>
            <div className="mt-3 space-y-3 text-sm leading-relaxed text-ink-600">
              <p>
                This assistant helps you quickly find answers from official
                construction, materials, and scheduling documents.
              </p>
              <p>
                All responses are grounded in approved source materials and
                include citations so you can verify where each answer comes
                from.
              </p>
            </div>
          </section>

          <section className="rounded-2xl border border-slate-100 bg-white p-8 shadow-soft-md">
            <h2 className="text-lg font-semibold text-ink-900">
              What It Cannot Answer
            </h2>
            <div className="mt-3 space-y-3 text-sm leading-relaxed text-ink-600">
              <p>The assistant prioritizes accuracy over guessing.</p>
              
            </div>
            <div className="mt-5 flex gap-3 rounded-xl border-l-4 border-blue-500 bg-blue-50 px-4 py-4 text-sm text-ink-700">
              <Info className="mt-0.5 h-5 w-5 text-blue-600" aria-hidden="true" />
              <p>
                When you see an “Insufficient Evidence” response, it means there
                was not enough supporting documentation to answer confidently
              </p>
            </div>
          </section>

          <section className="rounded-2xl border border-slate-100 bg-white p-8 shadow-soft-md">
            <h2 className="text-lg font-semibold text-ink-900">
              How to Ask Better Questions
            </h2>
            <p className="mt-2 text-sm text-ink-600">
              Clear, specific questions usually produce better results.
            </p>

            <div className="mt-6 grid gap-6 md:grid-cols-2">
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-emerald-700">
                  <CheckCircle className="h-5 w-5" aria-hidden="true" />
                  Good Questions
                </div>
                <div className="space-y-3">
                  {[
                    "What is the maximum chloride content for washed gravel?",
                    "Summarize Section 401 thickness requirements.",
                    "What are the curing requirements for concrete in Section 901?"
                  ].map((item) => (
                    <div
                      key={item}
                      className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900"
                    >
                      {item}
                    </div>
                  ))}
                </div>
              </div>

              <div className="space-y-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-rose-700">
                  <XCircle className="h-5 w-5" aria-hidden="true" />
                  Unclear Questions
                </div>
                <div className="space-y-3">
                  {[
                    "Is washed gravel okay?",
                    "Explain asphalt rules.",
                    "Tell me about concrete."
                  ].map((item) => (
                    <div
                      key={item}
                      className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900"
                    >
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>

          <section className="rounded-2xl border border-slate-100 bg-white p-8 shadow-soft-md">
            <h2 className="text-lg font-semibold text-ink-900">
              Understanding Confidence and Citations
            </h2>

            <div className="mt-4 space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-ink-900">
                <TrendingUp className="h-5 w-5 text-ink-600" aria-hidden="true" />
                Retrieval Strength
              </div>
              <p className="text-sm text-ink-600">
                Retrieval strength shows how much supporting evidence was found
                in the source documents.
              </p>
            </div>

            <div className="mt-5 grid gap-4 md:grid-cols-3">
              {[
                {
                  label: "STRONG",
                  labelClass: "bg-emerald-100 text-emerald-700",
                  body: "Multiple relevant sources with direct evidence"
                },
                {
                  label: "MEDIUM",
                  labelClass: "bg-amber-100 text-amber-700",
                  body: "Some relevant sources, but evidence may be partial"
                },
                {
                  label: "WEAK",
                  labelClass: "bg-rose-100 text-rose-700",
                  body: "Limited sources; answer may lack detail"
                }
              ].map((item) => (
                <div
                  key={item.label}
                  className="rounded-xl border border-slate-100 bg-white px-4 py-4 text-sm text-ink-600 shadow-soft-sm"
                >
                  <span
                    className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${item.labelClass}`}
                  >
                    {item.label}
                  </span>
                  <p className="mt-3">{item.body}</p>
                </div>
              ))}
            </div>

            <div className="mt-6 space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-ink-900">
                <MessageCircle className="h-5 w-5 text-ink-600" aria-hidden="true" />
                Citations and Page References
              </div>
              <p className="text-sm text-ink-600">
                Each answer includes citations showing where the information came
                from. Citations may include:
              </p>
              <ul className="list-disc space-y-1 pl-5 text-sm text-ink-600">
                <li>Document name</li>
                <li>Section or table reference</li>
                <li>Page number</li>
              </ul>
              <p className="text-sm text-ink-600">
                Clicking a citation opens the document directly to the
                referenced page so you can review the source yourself.
              </p>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
