import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { createRouteHandlerClient } from "@supabase/auth-helpers-nextjs";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

export async function GET(request: Request) {
  const supabase = createRouteHandlerClient({ cookies });
  const {
    data: { session }
  } = await supabase.auth.getSession();

  if (!session?.access_token) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const url = new URL(request.url);
  const upstreamUrl = `${BACKEND_URL}/documents/open${url.search}`;
  if (process.env.NODE_ENV === "development") {
    // eslint-disable-next-line no-console
    console.log("documents/open upstream url", upstreamUrl);
  }

  try {
    let upstream = await fetch(upstreamUrl, {
      redirect: "manual",
      headers: {
        Authorization: `Bearer ${session.access_token}`
      }
    });

    if (upstream.status >= 300 && upstream.status < 400) {
      const location = upstream.headers.get("location");
      if (!location) {
        return NextResponse.json(
          { error: "Upstream request failed" },
          { status: 502 }
        );
      }
      const followUrl = new URL(location, BACKEND_URL);
      followUrl.hash = "";
      upstream = await fetch(followUrl.toString(), {
        headers: {
          Authorization: `Bearer ${session.access_token}`
        }
      });
    }

    if (!upstream.ok) {
      const text = await upstream.text();
      if (process.env.NODE_ENV === "development") {
        // eslint-disable-next-line no-console
        console.log("documents/open upstream status", upstream.status);
      }
      try {
        const json = text ? JSON.parse(text) : { error: "Upstream request failed" };
        return NextResponse.json(json, { status: upstream.status });
      } catch (_err) {
        return NextResponse.json(
          { error: text || "Upstream request failed" },
          { status: upstream.status }
        );
      }
    }

    const headers = new Headers();
    const contentType = upstream.headers.get("content-type");
    const contentDisposition = upstream.headers.get("content-disposition");
    if (contentType) {
      headers.set("Content-Type", contentType);
    }
    if (contentDisposition) {
      headers.set("Content-Disposition", contentDisposition);
    }
    headers.set("Cache-Control", "no-store");

    return new Response(upstream.body, {
      status: upstream.status,
      headers
    });
  } catch (_err) {
    return NextResponse.json(
      { error: "Upstream request failed" },
      { status: 502 }
    );
  }
}
