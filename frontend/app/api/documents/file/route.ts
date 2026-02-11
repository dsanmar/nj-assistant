import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { createRouteHandlerClient } from "@supabase/auth-helpers-nextjs";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8000";

export async function GET(request: Request) {
  const supabase = createRouteHandlerClient({ cookies });
  const {
    data: { session }
  } = await supabase.auth.getSession();

  if (!session?.access_token) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const filename = searchParams.get("filename");
  if (!filename) {
    return NextResponse.json({ error: "filename is required" }, { status: 400 });
  }

  try {
    const upstream = await fetch(
      `${BACKEND_URL}/documents/file?filename=${encodeURIComponent(filename)}`,
      {
        headers: {
          Authorization: `Bearer ${session.access_token}`
        }
      }
    );

    if (!upstream.ok || !upstream.body) {
      const text = await upstream.text();
      return NextResponse.json(
        { error: text || "Upstream request failed" },
        { status: upstream.status }
      );
    }

    const contentType =
      upstream.headers.get("content-type") ?? "application/pdf";
    const contentLength = upstream.headers.get("content-length");
    const contentDisposition = upstream.headers.get("content-disposition") ?? "";
    const safeName = filename.split("/").pop() || "document.pdf";

    const headers = new Headers({
      "Content-Type": contentType,
      "Cache-Control": "no-store"
    });
    if (contentLength) {
      headers.set("Content-Length", contentLength);
    }
    if (contentDisposition && !contentDisposition.toLowerCase().includes("attachment")) {
      headers.set("Content-Disposition", contentDisposition);
    } else {
      headers.set("Content-Disposition", `inline; filename="${safeName}"`);
    }

    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers
    });
  } catch (err) {
    return NextResponse.json(
      { error: "Upstream request failed" },
      { status: 502 }
    );
  }
}
