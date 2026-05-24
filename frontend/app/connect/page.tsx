"use client";

/**
 * /connect — Salesforce OAuth connection page.
 *
 * States:
 *   • Already connected  → show org info + disconnect button
 *   • Not connected      → "Connect Salesforce" button (starts OAuth flow)
 *   • ?sf=connected      → success banner after OAuth callback
 *   • ?error=...         → error banner if OAuth failed
 */

import { useEffect, useState, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getToken, getCachedUser, logout } from "@/lib/auth";
import type { SFStatus, User } from "@/types";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function ConnectPage() {
  const router       = useRouter();
  const searchParams = useSearchParams();

  const [sfStatus,   setSfStatus]   = useState<SFStatus | null>(null);
  const [user,       setUser]       = useState<User | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [error,      setError]      = useState<string | null>(null);
  const [success,    setSuccess]    = useState(false);

  const token = getToken();

  const fetchSFStatus = useCallback(async () => {
    if (!token) {
      // No localStorage token — clear stale cookie and redirect to login.
      document.cookie = "sf_dashboard_token=; path=/; max-age=0; SameSite=Lax";
      router.replace("/login");
      return;
    }
    try {
      const res = await fetch(`${BACKEND}/auth/sf-status`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 401) { logout(); return; }
      setSfStatus(await res.json());
    } catch {
      setError("Could not reach the server. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, [token, router]);

  useEffect(() => {
    setUser(getCachedUser());
    // Handle OAuth callback params
    const sfParam    = searchParams.get("sf");
    const errorParam = searchParams.get("error");
    if (sfParam === "connected") setSuccess(true);
    if (errorParam) {
      // backend_unreachable means the backend was slow to start — not an OAuth
      // failure. Show a gentler message; the SF connection itself is fine.
      if (errorParam === "backend_unreachable") {
        setError("The backend took a moment to start up. Your Salesforce connection is still active — click Go to Dashboard.");
      } else {
        setError(`Salesforce connection failed: ${errorParam}`);
      }
    }
    fetchSFStatus();
  }, [fetchSFStatus, searchParams]);

  /**
   * Start the Salesforce OAuth flow.
   * @param forceLogin  true → adds `prompt=login` so Salesforce always shows
   *                    the login screen, letting the user pick a different org.
   *                    false (default) → reuses the existing browser session if
   *                    the user is already logged into Salesforce (faster).
   */
  const startOAuth = (forceLogin = false) => {
    if (!token) return;
    setConnecting(true);
    const switchParam = forceLogin ? "&switch=true" : "";
    window.location.href = `${BACKEND}/auth/salesforce?token=${encodeURIComponent(token)}${switchParam}`;
  };

  // The backend reads the token from the Authorization header, but since this
  // is a browser redirect (not fetch), we pass it as a query param that the
  // backend can also accept. See main.py get /auth/salesforce.
  const disconnect = async () => {
    if (!token) return;
    await fetch(`${BACKEND}/auth/sf-disconnect`, {
      method:  "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    setSfStatus({ connected: false });
    setSuccess(false);
    setError(null);
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-sm text-gray-500 animate-pulse">Loading…</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center shadow-md">
            <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
              />
            </svg>
          </div>
          <div>
            <h1 className="text-lg font-bold text-gray-900">Salesforce AI Dashboard</h1>
            <p className="text-xs text-gray-500">Hi, {user?.name ?? user?.email ?? "there"}</p>
          </div>
        </div>

        <div className="bg-white rounded-2xl shadow-xl p-8">
          {/* Success banner */}
          {success && (
            <div className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-xl px-4 py-3 mb-6 text-sm text-green-700">
              <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Salesforce connected successfully!
            </div>
          )}

          {/* Error banner */}
          {error && (
            <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-xl px-4 py-3 mb-6 text-sm text-red-700">
              <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
              {error}
            </div>
          )}

          {sfStatus?.connected ? (
            /* ── Connected state ── */
            <>
              <div className="flex items-center gap-3 mb-6">
                <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center">
                  <svg className="w-5 h-5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-semibold text-gray-900">Salesforce Connected</p>
                  <p className="text-xs text-gray-500">{sfStatus.sf_username ?? sfStatus.instance_url}</p>
                </div>
              </div>

              <div className="bg-gray-50 rounded-xl p-4 mb-6 space-y-2 text-xs text-gray-600">
                {sfStatus.instance_url && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">Instance</span>
                    <span className="font-mono truncate max-w-[220px]">{sfStatus.instance_url}</span>
                  </div>
                )}
                {sfStatus.org_id && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">Org ID</span>
                    <span className="font-mono">{sfStatus.org_id}</span>
                  </div>
                )}
                {sfStatus.connected_at && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">Connected</span>
                    <span>{new Date(sfStatus.connected_at).toLocaleDateString()}</span>
                  </div>
                )}
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => router.push("/")}
                  className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 rounded-lg text-sm transition-colors"
                >
                  Go to Dashboard →
                </button>
                <button
                  onClick={disconnect}
                  className="px-4 py-2.5 border border-red-200 text-red-600 hover:bg-red-50 rounded-lg text-sm transition-colors"
                >
                  Disconnect
                </button>
              </div>

              {/* Switch to a different SF org without disconnecting first */}
              <div className="text-center mt-3">
                <button
                  onClick={() => startOAuth(true)}
                  disabled={connecting}
                  className="text-xs text-gray-400 hover:text-blue-600 underline underline-offset-2 transition-colors"
                >
                  Switch to a different Salesforce account
                </button>
              </div>
            </>
          ) : (
            /* ── Not connected state ── */
            <>
              <div className="text-center mb-6">
                <div className="w-16 h-16 bg-blue-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
                  <svg className="w-8 h-8 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
                    />
                  </svg>
                </div>
                <h2 className="text-lg font-semibold text-gray-900 mb-2">Connect your Salesforce org</h2>
                <p className="text-sm text-gray-500 leading-relaxed">
                  Securely link your Salesforce account. We&apos;ll redirect you to Salesforce
                  to approve read-only access — your credentials never touch our servers.
                </p>
              </div>

              {/* Primary connect button — reuses existing SF browser session if present */}
              <button
                onClick={() => startOAuth(false)}
                disabled={connecting}
                className="w-full flex items-center justify-center gap-3 bg-[#00A1E0] hover:bg-[#0087BD] disabled:bg-gray-300 text-white font-semibold py-3 rounded-xl text-sm transition-colors shadow-sm"
              >
                {connecting ? (
                  <span>Redirecting to Salesforce…</span>
                ) : (
                  <>
                    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M10.5 2C7.46 2 5 4.46 5 7.5c0 .28.02.56.06.83C3.28 9.06 2 10.79 2 12.75 2 15.1 3.9 17 6.25 17H17c2.76 0 5-2.24 5-5 0-2.42-1.72-4.44-4-4.9V7c0-2.76-2.24-5-5-5h-2.5z"/>
                    </svg>
                    Connect with Salesforce
                  </>
                )}
              </button>

              {/* Switch-account link — forces the SF login screen via prompt=login */}
              <div className="text-center mt-2">
                <button
                  onClick={() => startOAuth(true)}
                  disabled={connecting}
                  className="text-xs text-gray-400 hover:text-blue-600 underline underline-offset-2 transition-colors disabled:opacity-50"
                >
                  Use a different Salesforce account
                </button>
              </div>

              <div className="mt-3 flex items-start gap-2 text-xs text-gray-400">
                <svg className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                  />
                </svg>
                <span>Read-only access. Tokens are encrypted at rest. You can disconnect any time.</span>
              </div>
            </>
          )}
        </div>

        {/* Logout link */}
        <p className="text-center mt-4 text-xs text-gray-500">
          <button onClick={logout} className="underline hover:text-gray-700 transition-colors">
            Sign out
          </button>
        </p>
      </div>
    </div>
  );
}
