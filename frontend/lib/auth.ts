/**
 * auth.ts — Client-side auth utilities.
 *
 * Token is stored in localStorage under "sf_dashboard_token".
 * All API calls attach it as a Bearer header via api.ts.
 */

import type { User } from "@/types";

const TOKEN_KEY = "sf_dashboard_token";
const USER_KEY  = "sf_dashboard_user";

// ── Token storage ─────────────────────────────────────────────────────────────

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

/** Clear both localStorage keys AND the middleware cookie atomically. */
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  // Expire the cookie the middleware reads — without this, the Edge middleware
  // still sees a valid cookie after logout and bounces the user back to "/" in
  // an infinite redirect loop instead of letting them reach /login.
  document.cookie = `${TOKEN_KEY}=; path=/; max-age=0; SameSite=Lax`;
}

// ── Cached user ───────────────────────────────────────────────────────────────

export function getCachedUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function setCachedUser(user: User): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

// ── Auth state ────────────────────────────────────────────────────────────────

export function isLoggedIn(): boolean {
  return Boolean(getToken());
}

export function logout(): void {
  clearToken();
  window.location.href = "/login";
}

// ── Decode JWT payload (no verification — verification happens server-side) ───

export function decodeTokenPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

export function isTokenExpired(token: string): boolean {
  const payload = decodeTokenPayload(token);
  if (!payload || typeof payload.exp !== "number") return true;
  return Date.now() / 1000 > payload.exp;
}
