/**
 * middleware.ts — Next.js Edge Middleware for route protection.
 *
 * Protected routes (token required):  /  and  /connect
 * Public routes (no token needed):    /login
 *
 * The token is read from the "sf_dashboard_token" cookie that the login page
 * writes after a successful auth response (in addition to localStorage).
 * Middleware runs on the Edge — it cannot access localStorage — so we rely
 * on the cookie for the gate check; localStorage is used client-side for
 * attaching the Bearer header to API calls.
 */

import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS  = ["/login"];
const BACKEND_PATHS = ["/api/auth", "/api/query"];   // proxied to FastAPI, skip guard

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Let Next.js internal routes and static files through
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    BACKEND_PATHS.some((p) => pathname.startsWith(p))
  ) {
    return NextResponse.next();
  }

  const rawToken = req.cookies.get("sf_dashboard_token")?.value;

  // Treat a malformed cookie (not a 3-part JWT) as absent — this prevents
  // the middleware from blocking a redirect-to-login when the client has
  // already cleared localStorage but left a stale/corrupted cookie.
  const token = rawToken && rawToken.split(".").length === 3 ? rawToken : undefined;

  // If the cookie is stale/malformed, clear it on the response so the browser
  // stops sending it on future requests.
  const clearCookieHeader = !token && rawToken
    ? { "Set-Cookie": "sf_dashboard_token=; path=/; max-age=0; SameSite=Lax" }
    : {};

  // Unauthenticated user hitting a protected route → redirect to /login
  if (!token && !PUBLIC_PATHS.includes(pathname)) {
    const loginUrl = req.nextUrl.clone();
    loginUrl.pathname = "/login";
    loginUrl.searchParams.set("next", pathname);
    const res = NextResponse.redirect(loginUrl);
    if (clearCookieHeader["Set-Cookie"]) {
      res.headers.set("Set-Cookie", clearCookieHeader["Set-Cookie"]);
    }
    return res;
  }

  // Already logged in and trying to visit /login → redirect to home
  if (token && pathname === "/login") {
    const homeUrl = req.nextUrl.clone();
    homeUrl.pathname = "/";
    homeUrl.searchParams.delete("next");
    return NextResponse.redirect(homeUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
