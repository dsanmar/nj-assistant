"use client";

type BrowserPdfViewerProps = {
  fileUrl: string | null;
  page: number;
  title?: string;
};

export function BrowserPdfViewer({ fileUrl, page, title }: BrowserPdfViewerProps) {
  if (!fileUrl) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-ink-500">
        Select a document to preview.
      </div>
    );
  }

  const src = `${fileUrl}#page=${Math.max(1, page)}`;

  return (
    <iframe
      key={`${fileUrl}|${page}`}
      src={src}
      title={title ?? "PDF Viewer"}
      className="h-full w-full rounded-2xl border border-slate-200 bg-white"
    />
  );
}
