/**
 * Typed API client — thin wrapper around fetch to the Python backend.
 * All calls go through the Next.js API proxy (/api/query) so the
 * backend URL is never exposed to the browser in production.
 */

import type { QueryResponse, HealthResponse } from "@/types";

const PROXY = "/api/query";              // Next.js route handler (same origin)
const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Query ─────────────────────────────────────────────────────────────────────

export async function sendQuery(
  query: string,
  sessionId: string | null
): Promise<QueryResponse> {
  const res = await fetch(PROXY, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, session_id: sessionId }),
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Query failed (${res.status}): ${detail}`);
  }

  return res.json() as Promise<QueryResponse>;
}

// ── Health ────────────────────────────────────────────────────────────────────

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${BACKEND}/api/health`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Health check failed (${res.status})`);
  return res.json() as Promise<HealthResponse>;
}

// ── Clear session ─────────────────────────────────────────────────────────────

export async function clearSession(sessionId: string): Promise<void> {
  await fetch(`${BACKEND}/api/session/${sessionId}`, { method: "DELETE" });
}
