"use client";

import { useMemo, useRef, useState } from "react";
import {
  Bot,
  ChevronDown,
  ExternalLink,
  Send
} from "lucide-react";
import { RequireAuth } from "@/lib/auth";

type ScopeType = "all" | "standspec" | "scheduling" | "mp" | "mp_only";
type AskMode = "answer" | "sources_only";

type AskCitation = {
  display_name: string;
  filename: string;
  doc_type: string;
  section_id?: string | null;
  heading?: string | null;
  page_start: number;
  page_end: number;
  snippet: string;
  open_url: string;
  chunk_kind?: string | null;
};

type AskResponse = {
  query: string;
  scope: ScopeType;
  confidence: "strong" | "medium" | "weak";
  answer: string;
  citations: AskCitation[];
  table?: { table_uid: string; open_url?: string | null } | null;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  tableOpenUrl?: string | null;
};

const scopeOptions: { value: ScopeType; label: string }[] = [
  { value: "standspec", label: "Standard Specifications" },
  { value: "scheduling", label: "Scheduling Manual" },
  { value: "mp", label: "Materials Procedures" },
  { value: "all", label: "All Documents" }
];

function devLog(label: string, payload: unknown) {
  if (process.env.NODE_ENV === "development") {
    // eslint-disable-next-line no-console
    console.log(label, payload);
  }
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: "Hello! What would you like to know?" }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [scope, setScope] = useState<ScopeType>("standspec");
  const [mode, setMode] = useState<AskMode>("answer");
  const [answerDetails, setAnswerDetails] = useState<{
    confidence: AskResponse["confidence"];
    citations: AskCitation[];
    table?: AskResponse["table"];
  } | null>(null);
  const [excerptsOpen, setExcerptsOpen] = useState(false);
  const citationsRef = useRef<HTMLDivElement | null>(null);
  const [expandedMessages, setExpandedMessages] = useState<Record<number, boolean>>({});

  const strengthBadge = useMemo(() => {
    const conf = answerDetails?.confidence;
    if (!conf) return "bg-slate-100 text-slate-500";
    if (conf === "strong") return "bg-emerald-100 text-emerald-700";
    if (conf === "medium") return "bg-amber-100 text-amber-700";
    return "bg-rose-100 text-rose-700";
  }, [answerDetails]);
  const hasCitations = (answerDetails?.citations?.length ?? 0) > 0;
  const citations = answerDetails?.citations ?? [];

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const userMessage = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setLoading(true);

    try {
      const resp = await fetch("/api/chat/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: userMessage,
          scope,
          k: 8,
          mode
        })
      });

      const data = (await resp.json()) as AskResponse;
      devLog("ask_response", data);

      if (!resp.ok) {
        throw new Error(data?.answer || "Request failed");
      }

      const nextAnswer =
        data.answer?.trim() ||
        (mode === "sources_only"
          ? "Sources only: see citations on the right."
          : "Sorry, I couldn’t generate an answer.");
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: nextAnswer,
          tableOpenUrl: data.table?.open_url ?? null
        }
      ]);
      setAnswerDetails({
        confidence: data.confidence,
        citations: data.citations ?? [],
        table: data.table ?? null
      });
      setExcerptsOpen(false);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Sorry, something went wrong. Please try again."
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <RequireAuth>
      <div className="min-h-screen bg-[#f6f7fb] pb-12 pt-8">
        <div className="mx-auto w-full max-w-7xl px-6">
          <div className="grid gap-6 lg:grid-cols-[1.7fr_0.8fr]">
            <section className="rounded-2xl border border-slate-100 bg-white shadow-soft-md">
            <div className="border-b border-slate-100 px-6 py-5">
              <h1 className="text-lg font-semibold text-ink-900">
                Chat Assistant
              </h1>
            </div>
            <div className="px-6 py-6">
              <div className="h-[460px] space-y-6 overflow-y-auto pr-2">
                {messages.map((message, idx) =>
                  message.role === "assistant" ? (
                    <div key={`${message.role}-${idx}`} className="flex items-start gap-4">
                      <div className="flex h-10 w-10 shrink-0 self-start items-center justify-center rounded-full bg-blue-900 text-white">
                        <Bot className="h-5 w-5" aria-hidden="true" />
                      </div>
                      <div className="max-w-2xl rounded-2xl bg-slate-100 px-5 py-4 text-sm text-ink-800 whitespace-pre-wrap break-words">
                        {message.content.length > 600 && !expandedMessages[idx]
                          ? `${message.content.slice(0, 600)}...`
                          : message.content}
                        {message.content.length > 600 ? (
                          <div className="mt-3">
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedMessages((prev) => ({
                                  ...prev,
                                  [idx]: !prev[idx]
                                }))
                              }
                              className="text-xs font-semibold text-blue-600"
                            >
                              {expandedMessages[idx] ? "Show less" : "Show more"}
                            </button>
                          </div>
                        ) : null}
                        {message.tableOpenUrl ? (
                          <div className="mt-4">
                            <button
                              type="button"
                              onClick={() =>
                                window.open(
                                  `/api${message.tableOpenUrl}`,
                                  "_blank",
                                  "noopener,noreferrer"
                                )
                              }
                              className="inline-flex items-center gap-2 rounded-lg border border-blue-200 bg-white px-3 py-2 text-xs font-semibold text-blue-700 hover:bg-blue-50"
                            >
                              Open table in NJDOT manual
                              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                            </button>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ) : (
                    <div key={`${message.role}-${idx}`} className="flex justify-end">
                      <div className="max-w-xs rounded-2xl bg-blue-900 px-5 py-4 text-sm text-white">
                        {message.content}
                      </div>
                    </div>
                  )
                )}
              </div>
            </div>

            <div className="border-t border-slate-100 px-6 py-6">
              <div className="flex flex-wrap gap-3">
                <div className="flex-1">
                  <select
                    value={scope}
                    onChange={(event) => setScope(event.target.value as ScopeType)}
                    className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-ink-700 shadow-soft-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
                  >
                    {scopeOptions.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setMode((prev) => (prev === "answer" ? "sources_only" : "answer"))
                  }
                  className={`inline-flex items-center gap-2 rounded-xl border px-4 py-3 text-sm font-semibold shadow-soft-sm ${
                    mode === "answer"
                      ? "border-blue-200 bg-blue-50 text-blue-700"
                      : "border-slate-200 bg-slate-50 text-ink-700"
                  }`}
                >
                  {mode === "answer" ? "Answer Mode" : "Sources Only"}
                </button>
              </div>
              <div className="mt-4 flex flex-col gap-3 sm:flex-row">
                <input
                  type="text"
                  placeholder="Ask a question about NJDOT documentation..."
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  className="w-full flex-1 rounded-xl border border-slate-200 bg-white px-4 py-4 text-sm text-ink-700 shadow-soft-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
                />
                <button
                  type="button"
                  onClick={handleSend}
                  disabled={!input.trim() || loading}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-red-600 px-6 py-4 text-sm font-semibold text-white shadow-soft-md hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-red-400 sm:w-auto"
                >
                  <Send className="h-5 w-5" aria-hidden="true" />
                  {loading ? "Thinking..." : "Send"}
                </button>
              </div>
            </div>
            </section>

            <aside className="rounded-2xl border border-slate-100 bg-white shadow-soft-md">
              <div className="border-b border-slate-100 px-6 py-5">
                <h2 className="text-lg font-semibold text-ink-900">
                  Answer Details
                </h2>
              </div>
              <div className="space-y-6 px-6 py-6">
                <div className="space-y-3">
                  <p className="text-sm font-semibold text-ink-700">
                    Retrieval Strength
                  </p>
                  <span
                    className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${strengthBadge}`}
                  >
                    {answerDetails?.confidence?.toUpperCase() ?? "—"}
                  </span>
                </div>

              <div className="space-y-3">
                <p className="text-sm font-semibold text-ink-700">Citations</p>
                <div ref={citationsRef} className="space-y-3">
                  {citations.length === 0 ? (
                    <p className="text-sm text-ink-500">No citations yet</p>
                  ) : null}
                  {citations.slice(0, 3).map((item, idx) => {
                    const section = item.section_id
                      ? `Section ${item.section_id}`
                      : item.heading || "Document";
                    const page = `Page ${item.page_start}`;
                    const pageIndex = item.page_start ?? 1;
                    const url = `/api/documents/file?filename=${encodeURIComponent(
                      item.filename
                    )}#page=${pageIndex}`;

                    return (
                      <div
                        key={`${item.display_name}-${idx}`}
                        className="flex w-full items-start justify-between gap-3 rounded-xl bg-blue-50 px-4 py-4 text-left text-sm text-ink-700"
                      >
                        <div>
                          <p className="font-semibold text-ink-900">
                            {item.display_name}
                          </p>
                          <p className="mt-1 text-xs text-ink-600">
                            {section} • {page}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => window.open(url, "_blank", "noopener,noreferrer")}
                          className="rounded-full p-2 text-ink-500 hover:text-ink-800"
                          aria-label="Open document"
                        >
                          <ExternalLink className="h-4 w-4" aria-hidden="true" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>

              {citations.length > 0 ? (
                <>
                  <button
                    type="button"
                    onClick={() => setExcerptsOpen((prev) => !prev)}
                    className="flex w-full items-center justify-between border-t border-slate-100 pt-4 text-sm font-semibold text-ink-700"
                  >
                    <span>Relevant Excerpts</span>
                    <ChevronDown
                      className={`h-5 w-5 text-ink-500 transition ${
                        excerptsOpen ? "rotate-180" : ""
                      }`}
                      aria-hidden="true"
                    />
                  </button>
                  {excerptsOpen ? (
                    <div className="space-y-3">
                      {citations.slice(0, 5).map((item, idx) => (
                        <div
                          key={`${item.filename}-${idx}`}
                          className="rounded-xl border border-slate-100 bg-white px-4 py-3 text-sm text-ink-600"
                        >
                          {item.snippet}
                        </div>
                      ))}
                    </div>
                  ) : null}
                </>
              ) : null}
              </div>
            </aside>
          </div>
        </div>
      </div>
    </RequireAuth>
  );
}
