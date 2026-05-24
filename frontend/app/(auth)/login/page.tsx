"use client";

/**
 * Login / Register page.
 * Toggles between two forms; on success stores the JWT + sets a cookie,
 * then redirects to the originally requested URL (or /connect if fresh signup).
 */

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { setToken, setCachedUser, isLoggedIn } from "@/lib/auth";
import type { AuthResponse } from "@/types";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function LoginPage() {
  const router       = useRouter();
  const searchParams = useSearchParams();
  const [mode,     setMode]     = useState<"login" | "register">("login");
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [name,     setName]     = useState("");
  const [error,    setError]    = useState<string | null>(null);
  const [loading,  setLoading]  = useState(false);

  // Already logged in → skip to dashboard
  useEffect(() => {
    if (isLoggedIn()) router.replace("/");
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const endpoint = mode === "login" ? "/auth/login" : "/auth/register";
    const body     = mode === "login"
      ? { email, password }
      : { email, password, name: name || undefined };

    try {
      const res = await fetch(`${BACKEND}${endpoint}`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(body),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.detail ?? "Something went wrong.");
        return;
      }

      const auth = data as AuthResponse;

      // Persist token in localStorage AND as a cookie (for middleware)
      setToken(auth.token);
      setCachedUser(auth.user);
      document.cookie = `sf_dashboard_token=${auth.token}; path=/; max-age=${7 * 24 * 3600}; SameSite=Lax`;

      // New registrations → connect Salesforce; returning logins → original URL or home
      const next = searchParams.get("next");
      if (mode === "register") {
        router.replace("/connect");
      } else {
        router.replace(next ?? "/");
      }
    } catch {
      setError("Could not reach the server. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-xl p-8">
      {/* Tab switcher */}
      <div className="flex rounded-xl bg-gray-100 p-1 mb-6">
        {(["login", "register"] as const).map((m) => (
          <button
            key={m}
            onClick={() => { setMode(m); setError(null); }}
            className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${
              mode === m
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {m === "login" ? "Sign in" : "Create account"}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Name (register only) */}
        {mode === "register" && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Name <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your name"
              className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
        )}

        {/* Email */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        {/* Password */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={mode === "register" ? "Minimum 8 characters" : "Your password"}
            className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2.5 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-medium py-2.5 rounded-lg text-sm transition-colors"
        >
          {loading
            ? (mode === "login" ? "Signing in…" : "Creating account…")
            : (mode === "login" ? "Sign in" : "Create account")}
        </button>
      </form>

      {mode === "register" && (
        <p className="mt-4 text-xs text-center text-gray-500">
          After registering you&apos;ll connect your Salesforce org.
        </p>
      )}
    </div>
  );
}
