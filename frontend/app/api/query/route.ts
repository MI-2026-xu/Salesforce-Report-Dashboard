/**
 * Next.js API route — proxies POST /api/query to the Python FastAPI backend.
 *
 * Why proxy instead of calling FastAPI directly from the browser?
 *   1. Keeps backend URL server-side only.
 *   2. Avoids CORS preflight in production (same-origin request).
 *   3. One place to add auth headers, rate-limiting, logging later.
 */

import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const backendRes = await fetch(`${BACKEND}/api/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const data = await backendRes.json();

    return NextResponse.json(data, { status: backendRes.status });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { error: "proxy_error", detail: message },
      { status: 502 }
    );
  }
}
