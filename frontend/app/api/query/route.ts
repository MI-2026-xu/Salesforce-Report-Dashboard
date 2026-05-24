/**
 * Next.js API route — proxies POST /api/query to the Python FastAPI backend.
 * Forwards the Authorization header so the backend can authenticate the user.
 */

import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const auth = req.headers.get("Authorization") ?? "";

    const backendRes = await fetch(`${BACKEND}/api/query`, {
      method:  "POST",
      headers: {
        "Content-Type": "application/json",
        ...(auth ? { Authorization: auth } : {}),
      },
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
