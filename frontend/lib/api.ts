/**
 * api.ts — Typed API client.
 *
 * All requests attach the user's JWT as a Bearer token.
 * Queries go through the Next.js proxy (/api/query) to keep
 * the backend URL server-side only.
 */

import { getToken, logout } from "@/lib/auth";
import type { QueryResponse, HealthResponse, SFStatus } from "@/types";

const PROXY   = "/api/query";
const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Auth header ───────────────────────────────────────────────────────────────

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Throws on 401 (auto-logout) or non-OK responses. Passes signal through for cancellation. */
async function guardedFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init.headers ?? {}),
    },
    // signal is already in init if the caller set it — spread preserves it
  });
  if (res.status === 401) {
    logout(); // token expired → back to login
    throw new Error("Session expired. Please log in again.");
  }
  return res;
}

// ── Query ─────────────────────────────────────────────────────────────────────

export async function sendQuery(
  query: string,
  sessionId: string | null
): Promise<QueryResponse> {
  const res = await guardedFetch(PROXY, {
    method: "POST",
    body:   JSON.stringify({ query, session_id: sessionId }),
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Query failed (${res.status}): ${detail}`);
  }

  return res.json() as Promise<QueryResponse>;
}

// ── Health ────────────────────────────────────────────────────────────────────

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await guardedFetch(`${BACKEND}/api/health`);
  if (!res.ok) throw new Error(`Health check failed (${res.status})`);
  return res.json() as Promise<HealthResponse>;
}

// ── Salesforce status ─────────────────────────────────────────────────────────

export async function fetchSFStatus(signal?: AbortSignal): Promise<SFStatus> {
  const res = await guardedFetch(`${BACKEND}/auth/sf-status`, { signal });
  if (!res.ok) throw new Error(`SF status failed (${res.status})`);
  return res.json() as Promise<SFStatus>;
}

// ── Clear session ─────────────────────────────────────────────────────────────

export async function clearSession(sessionId: string): Promise<void> {
  await guardedFetch(`${BACKEND}/api/session/${sessionId}`, { method: "DELETE" });
}
