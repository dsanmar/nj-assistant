"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ExternalLink, FileText, Search } from "lucide-react";
import { RequireAuth } from "@/lib/auth";
import { supabase } from "@/lib/supabaseClient";
import { BrowserPdfViewer } from "@/components/BrowserPdfViewer";

type DocumentItem = {
  id: number;
  filename: string;
  display_name: string;
  doc_type: string;
  mp_id?: string | null;
  pages: number;
  description?: string | null;
};

type DocumentsResponse = {
  documents: DocumentItem[];
};

type SearchResult = {
  chunk_id: number;
  score: number;
  snippet: string;
  page_start: number;
  page_end: number;
  filename: string;
  display_name: string;
  doc_type: string;
  mp_id?: string | null;
  section_id?: string | null;
  heading?: string | null;
  chunk_kind?: string | null;
  table_uid?: string | null;
  table_label?: string | null;
  open_url: string;
};

type SearchResponse = {
  query: string;
  scope: "all" | "standspec" | "scheduling" | "mp" | "mp_only";
  total: number | null;
  offset: number;
  limit: number;
  results: SearchResult[];
};

const SEARCH_DEBOUNCE_MS = 300;
const SEARCH_LIMIT = 20;

const docTypeLabel = (value: string) =>
  value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<DocumentItem | null>(null);
  const [selectedPage, setSelectedPage] = useState(1);
  const [isExpanded, setIsExpanded] = useState(false);

  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchOffset, setSearchOffset] = useState(0);
  const [searchTotal, setSearchTotal] = useState<number | null>(null);

  const [docType, setDocType] = useState("all");
  const [mpFilter, setMpFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    let isMounted = true;
    supabase.auth
      .getSession()
      .then(async ({ data }) => {
        const token = data.session?.access_token;
        if (!token) {
          return { status: 401 } as Response;
        }
        return fetch("/api/documents", {
          headers: { Authorization: `Bearer ${token}` }
        });
      })
      .then(async (resp) => {
        if (resp.status === 401) {
          router.replace(`/login?redirectedFrom=${encodeURIComponent(pathname)}`);
          return null;
        }
        if (!resp.ok) {
          throw new Error("Failed to load documents");
        }
        return (await resp.json()) as DocumentsResponse;
      })
      .then((data) => {
        if (!data || !isMounted) return;
        setDocuments(data.documents);
        setSelectedDoc(data.documents[0] ?? null);
        setSelectedPage(1);
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof Error ? err.message : "Request failed");
        }
      });
    return () => {
      isMounted = false;
    };
  }, [pathname, router]);

  const docTypes = useMemo(() => {
    const values = new Set<string>();
    documents.forEach((doc) => values.add(doc.doc_type));
    return ["all", ...Array.from(values)];
  }, [documents]);

  const filteredDocs = useMemo(() => {
    const mpQuery = mpFilter.trim().toLowerCase();
    return documents.filter((doc) => {
      if (docType !== "all" && doc.doc_type !== docType) {
        return false;
      }
      if (mpQuery) {
        const mp = (doc.mp_id ?? "").toLowerCase();
        if (!mp || (!mp.startsWith(mpQuery) && mp !== mpQuery)) {
          return false;
        }
      }
      return true;
    });
  }, [documents, docType, mpFilter]);

  useEffect(() => {
    if (!filteredDocs.length) {
      setSelectedDoc(null);
      return;
    }
    if (!selectedDoc || !filteredDocs.some((doc) => doc.id === selectedDoc.id)) {
      setSelectedDoc(filteredDocs[0]);
      setSelectedPage(1);
    }
  }, [filteredDocs, selectedDoc]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search.trim());
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    setSearchOffset(0);
  }, [debouncedSearch, docType, mpFilter]);

  useEffect(() => {
    let isMounted = true;
    const query = debouncedSearch.trim();
    if (!query) {
      setSearchResults([]);
      setSearchTotal(null);
      setSearchError(null);
      setSearchLoading(false);
      return;
    }
    setSearchLoading(true);
    setSearchError(null);
    supabase.auth
      .getSession()
      .then(async ({ data }) => {
        const token = data.session?.access_token;
        if (!token) {
          return { status: 401 } as Response;
        }
        return fetch("/api/documents/search", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            query,
            scope: "all",
            doc_type: docType === "all" ? null : docType,
            mp_id: mpFilter.trim() || null,
            k: SEARCH_LIMIT,
            offset: searchOffset
          })
        });
      })
      .then(async (resp) => {
        if (!isMounted) return null;
        if (resp.status === 401) {
          router.replace(`/login?redirectedFrom=${encodeURIComponent(pathname)}`);
          return null;
        }
        if (!resp.ok) {
          throw new Error("Failed to search documents");
        }
        return (await resp.json()) as SearchResponse;
      })
      .then((data) => {
        if (!data || !isMounted) return;
        setSearchResults(data.results);
        setSearchTotal(data.total);
      })
      .catch((err) => {
        if (isMounted) {
          setSearchError(err instanceof Error ? err.message : "Request failed");
        }
      })
      .finally(() => {
        if (isMounted) {
          setSearchLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [debouncedSearch, docType, mpFilter, pathname, router, searchOffset]);

  const isSearching = debouncedSearch.trim().length > 0;

  const fileUrl = selectedDoc
    ? `/api/documents/file?filename=${encodeURIComponent(selectedDoc.filename)}`
    : null;

  const openPdfInNewTab = async (filename: string, page?: number) => {
    try {
      const { data } = await supabase.auth.getSession();
      const token = data.session?.access_token;
      if (!token) {
        router.replace(`/login?redirectedFrom=${encodeURIComponent(pathname)}`);
        return;
      }
      const resp = await fetch(
        `/api/documents/file?filename=${encodeURIComponent(filename)}`,
        {
          headers: {
            Authorization: `Bearer ${token}`
          }
        }
      );
      if (!resp.ok) {
        throw new Error("Failed to open document");
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const target = page ? `${url}#page=${page}` : url;
      window.open(target, "_blank", "noreferrer");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    }
  };

  const downloadPdf = async (filename: string, label: string) => {
    try {
      const { data } = await supabase.auth.getSession();
      const token = data.session?.access_token;
      if (!token) {
        router.replace(`/login?redirectedFrom=${encodeURIComponent(pathname)}`);
        return;
      }
      const resp = await fetch(
        `/api/documents/file?filename=${encodeURIComponent(filename)}`,
        {
          headers: {
            Authorization: `Bearer ${token}`
          }
        }
      );
      if (!resp.ok) {
        throw new Error("Failed to download document");
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = label || filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    }
  };

  const highlightSnippet = (text: string, query: string) => {
    if (!query) return text;
    const words = Array.from(
      new Set(
        query
          .split(/\s+/)
          .map((word) => word.trim())
          .filter(Boolean)
      )
    );
    if (!words.length) return text;
    const escaped = words.map((word) =>
      word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
    );
    const splitRegex = new RegExp(`(${escaped.join("|")})`, "gi");
    const testRegex = new RegExp(`^(${escaped.join("|")})$`, "i");
    return text.split(splitRegex).map((part, idx) => {
      if (testRegex.test(part)) {
        return (
          <mark
            key={`${part}-${idx}`}
            className="rounded bg-yellow-100 px-1 text-ink-900"
          >
            {part}
          </mark>
        );
      }
      return <span key={`${part}-${idx}`}>{part}</span>;
    });
  };

  const leftColumnClass = isExpanded ? "hidden" : "lg:col-span-6";
  const rightColumnClass = isExpanded
    ? "lg:col-span-12"
    : "lg:col-span-6";

  return (
    <RequireAuth>
      <div className="min-h-screen overflow-hidden bg-[#f6f7fb] pb-12 pt-8">
        <div className="mx-auto w-full max-w-7xl px-6">
          <header className="space-y-2">
            <h1 className="text-3xl font-semibold text-ink-900">
              Document Library
            </h1>
            <p className="text-sm text-ink-600">
              Browse and search NJDOT documentation
            </p>
          </header>

          <div className="mt-6 grid gap-6 lg:grid-cols-12">
            <section
              className={`rounded-2xl border border-slate-100 bg-white shadow-soft-md ${leftColumnClass}`}
            >
              <div className="flex h-[80vh] flex-col p-6">
                <div className="shrink-0 space-y-4">
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-400" />
                    <input
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="Search documents..."
                      className="w-full rounded-xl border border-slate-200 bg-white py-3 pl-12 pr-4 text-sm text-ink-700 shadow-soft-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
                    />
                  </div>
                  <div className="grid gap-3 md:grid-cols-[1fr_1fr]">
                    <select
                      value={docType}
                      onChange={(event) => setDocType(event.target.value)}
                      className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-ink-700 shadow-soft-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
                    >
                      {docTypes.map((type) => (
                        <option key={type} value={type}>
                          {type === "all"
                            ? "All Document Types"
                            : docTypeLabel(type)}
                        </option>
                      ))}
                    </select>
                    <input
                      value={mpFilter}
                      onChange={(event) => setMpFilter(event.target.value)}
                      placeholder="MP Number (e.g., 401)"
                      className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-ink-700 shadow-soft-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
                    />
                  </div>
                  {error ? (
                    <p className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
                      {error}
                    </p>
                  ) : null}
                </div>

                <div className="mt-5 flex-1 space-y-4 overflow-y-auto pr-2">
                  {isSearching ? (
                    <div className="space-y-4">
                      <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-ink-600">
                        <span>
                          Results for “{debouncedSearch}”
                          {searchTotal !== null ? ` • ${searchTotal} found` : ""}
                        </span>
                        <button
                          type="button"
                          onClick={() => setSearch("")}
                          className="text-sm font-semibold text-blue-600"
                        >
                          Clear search
                        </button>
                      </div>
                      {searchLoading ? (
                        <p className="text-sm text-ink-500">Searching…</p>
                      ) : searchError ? (
                        <p className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
                          {searchError}
                        </p>
                      ) : searchResults.length ? (
                        searchResults.map((result) => {
                          const isSelected =
                            selectedDoc?.filename === result.filename &&
                            selectedPage === result.page_start;
                          const tag =
                            result.chunk_kind === "equation"
                              ? "Equation"
                              : result.chunk_kind === "table_row"
                              ? "Table"
                              : null;

                          return (
                            <button
                              key={result.chunk_id}
                              type="button"
                              onClick={() => {
                                const doc = documents.find(
                                  (d) => d.filename === result.filename
                                );
                                if (doc) {
                                  setSelectedDoc(doc);
                                  setSelectedPage(result.page_start || 1);
                                }
                              }}
                              className={`w-full rounded-2xl border p-4 text-left shadow-soft-sm transition ${
                                isSelected
                                  ? "border-blue-500 bg-blue-50/40"
                                  : "border-slate-100 bg-white hover:border-blue-200"
                              }`}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="flex items-start gap-4">
                                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-red-50 text-red-600">
                                    <FileText
                                      className="h-6 w-6"
                                      aria-hidden="true"
                                    />
                                  </div>
                                  <div>
                                    <p className="text-sm font-semibold text-ink-900">
                                      {result.display_name}
                                    </p>
                                    <p className="mt-1 text-xs text-ink-600">
                                      Page {result.page_start}
                                    </p>
                                  </div>
                                </div>
                                <button
                                  type="button"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    openPdfInNewTab(
                                      result.filename,
                                      result.page_start
                                    );
                                  }}
                                  className="rounded-full border border-slate-200 p-2 text-ink-500 hover:text-ink-700"
                                  aria-label="Open in new tab"
                                >
                                  <ExternalLink
                                    className="h-4 w-4"
                                    aria-hidden="true"
                                  />
                                </button>
                              </div>
                              <div className="mt-3 text-sm text-ink-700">
                                {highlightSnippet(result.snippet, debouncedSearch)}
                              </div>
                              <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-ink-600">
                                <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">
                                  {docTypeLabel(result.doc_type)}
                                </span>
                                <span>Page {result.page_start}</span>
                                {result.mp_id ? (
                                  <span>MP {result.mp_id}</span>
                                ) : null}
                                {tag ? (
                                  <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                                    {tag}
                                  </span>
                                ) : null}
                              </div>
                            </button>
                          );
                        })
                      ) : (
                        <p className="text-sm text-ink-600">No results found.</p>
                      )}

                      {searchResults.length ? (
                        <div className="flex items-center justify-between pt-2">
                          <button
                            type="button"
                            onClick={() =>
                              setSearchOffset((prev) =>
                                Math.max(0, prev - SEARCH_LIMIT)
                              )
                            }
                            disabled={searchOffset === 0}
                            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-semibold text-ink-700 disabled:cursor-not-allowed disabled:text-ink-400"
                          >
                            Previous
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              setSearchOffset((prev) => prev + SEARCH_LIMIT)
                            }
                            disabled={
                              searchResults.length < SEARCH_LIMIT ||
                              (searchTotal !== null &&
                                searchOffset + SEARCH_LIMIT >= searchTotal)
                            }
                            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-semibold text-ink-700 disabled:cursor-not-allowed disabled:text-ink-400"
                          >
                            Next
                          </button>
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <>
                      {filteredDocs.map((doc) => {
                        const isSelected = selectedDoc?.id === doc.id;
                        return (
                          <button
                            key={doc.id}
                            type="button"
                            onClick={() => {
                              setSelectedDoc(doc);
                              setSelectedPage(1);
                            }}
                            className={`w-full rounded-2xl border p-4 text-left shadow-soft-sm transition ${
                              isSelected
                                ? "border-blue-500 bg-blue-50/40"
                                : "border-slate-100 bg-white hover:border-blue-200"
                            }`}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="flex items-start gap-4">
                                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-red-50 text-red-600">
                                  <FileText
                                    className="h-6 w-6"
                                    aria-hidden="true"
                                  />
                                </div>
                                <div>
                                  <p className="text-sm font-semibold text-ink-900">
                                    {doc.display_name}
                                  </p>
                                  <p className="mt-1 text-xs text-ink-600">
                                    {doc.description ??
                                      `${docTypeLabel(doc.doc_type)} • ${doc.filename}`}
                                  </p>
                                </div>
                              </div>
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  openPdfInNewTab(doc.filename);
                                }}
                                className="rounded-full border border-slate-200 p-2 text-ink-500 hover:text-ink-700"
                                aria-label="Open in new tab"
                              >
                                <ExternalLink
                                  className="h-4 w-4"
                                  aria-hidden="true"
                                />
                              </button>
                            </div>
                            <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-ink-600">
                              <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">
                                {docTypeLabel(doc.doc_type)}
                              </span>
                              <span>{doc.pages} pages</span>
                              {doc.mp_id ? <span>MP {doc.mp_id}</span> : null}
                            </div>
                          </button>
                        );
                      })}
                      {!filteredDocs.length && !error ? (
                        <p className="text-sm text-ink-600">
                          No documents match your filters.
                        </p>
                      ) : null}
                    </>
                  )}
                </div>
              </div>
            </section>

            <aside
              className={`rounded-2xl border border-slate-100 bg-white shadow-soft-md ${rightColumnClass}`}
            >
              <div className="flex h-[80vh] flex-col">
                <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-6 py-5">
                  <h2 className="text-lg font-semibold text-ink-900">
                    Document Viewer
                  </h2>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setIsExpanded((prev) => !prev)}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-ink-700"
                    >
                      {isExpanded ? "Split view" : "Expand viewer"}
                    </button>
                  </div>
                </div>
                <div className="flex-1 px-6 py-6">
                  <BrowserPdfViewer
                    fileUrl={fileUrl}
                    page={selectedPage}
                    title={selectedDoc?.display_name}
                  />
                </div>
                {selectedDoc ? (
                  <div className="shrink-0 px-6 pb-6">
                    <button
                      type="button"
                      onClick={() =>
                        downloadPdf(selectedDoc.filename, selectedDoc.display_name)
                      }
                      className="inline-flex w-full items-center justify-center rounded-xl bg-red-600 px-5 py-3 text-sm font-semibold text-white hover:bg-red-700"
                    >
                      Download PDF
                    </button>
                  </div>
                ) : null}
              </div>
            </aside>
          </div>
        </div>
      </div>
    </RequireAuth>
  );
}
