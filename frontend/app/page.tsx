"use client";

/**
 * Main chat page — multi-user, authenticated.
 *
 * On mount:
 *  1. Reads JWT from localStorage.
 *  2. Checks /auth/sf-status — if not connected, redirects to /connect.
 *  3. Loads health status from the backend.
 * Header now shows user's email + a dropdown for Connect / Disconnect / Sign out.
 */

import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import ChatMessage from "@/components/ChatMessage";
import { sendQuery, fetchHealth, clearSession, fetchSFStatus } from "@/lib/api";
import { getCachedUser, logout, getToken } from "@/lib/auth";
import type { ChatMessage as ChatMessageType, HealthResponse, User } from "@/types";

function uid() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

const SUGGESTIONS = [
  "How many leads do we have in total?",
  "Show me leads breakdown by status",
  "Top 5 opportunities by amount",
  "Show me all accounts by industry",
];

export default function Home() {
  const router       = useRouter();
  const searchParams = useSearchParams();

  const [messages,  setMessages]  = useState<ChatMessageType[]>([]);
  const [input,     setInput]     = useState("");
  const [loading,   setLoading]   = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [health,    setHealth]    = useState<HealthResponse | null>(null);
  const [user,      setUser]      = useState<User | null>(null);
  const [sfReady,   setSfReady]   = useState(false);   // true once SF connection confirmed
  const [menuOpen,  setMenuOpen]  = useState(false);
  const [retryCount, setRetryCount] = useState(0);     // backend cold-start retries

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLTextAreaElement>(null);

  // ── Bootstrap: verify auth + SF connection ─────────────────────────────────
  // Retries up to 3 times (with 3 s gaps) to handle backend cold-start.
  // Only redirects to /connect after all retries are exhausted.
  const MAX_RETRIES = 3;
  const RETRY_TIMEOUT_MS = 10_000; // 10 s per attempt — enough for cold start

  useEffect(() => {
    const token = getToken();
    if (!token) {
      document.cookie = "sf_dashboard_token=; path=/; max-age=0; SameSite=Lax";
      router.replace("/login");
      return;
    }

    setUser(getCachedUser());

    // If just returned from OAuth (?sf=connected), redirect to /connect success page
    const sfParam = searchParams.get("sf");
    if (sfParam === "connected") {
      router.replace("/connect?sf=connected");
      return;
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), RETRY_TIMEOUT_MS);

    fetchSFStatus(controller.signal)
      .then((status) => {
        clearTimeout(timeout);
        if (!status.connected) {
          router.replace("/connect");
        } else {
          setSfReady(true);
          fetchHealth()
            .then(setHealth)
            .catch(() =>
              setHealth({ status: "degraded", salesforce: "unreachable", version: "—" })
            );
        }
      })
      .catch((err) => {
        clearTimeout(timeout);
        if (err?.name === "AbortError" || err?.message?.includes("fetch")) {
          // Backend not ready yet — retry if we haven't hit the limit
          if (retryCount < MAX_RETRIES) {
            setTimeout(() => setRetryCount((n) => n + 1), 3000);
          } else {
            // Exhausted retries — send to /connect so the user sees a clear error
            router.replace("/connect?error=backend_unreachable");
          }
        } else {
          // 401 → api.ts already called logout(); anything else → /connect
          router.replace("/connect");
        }
      });

    return () => { clearTimeout(timeout); controller.abort(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, searchParams, retryCount]);

  // ── Auto-scroll ────────────────────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Submit ─────────────────────────────────────────────────────────────────
  const submit = useCallback(
    async (query: string) => {
      const trimmed = query.trim();
      if (!trimmed || loading) return;

      setInput("");
      setLoading(true);

      const userMsg: ChatMessageType = {
        id: uid(), role: "user", content: trimmed, timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);

      try {
        const data = await sendQuery(trimmed, sessionId);
        setSessionId(data.session_id);
        setMessages((prev) => [
          ...prev,
          { id: uid(), role: "assistant", content: data.summary || data.response, data, timestamp: new Date() },
        ]);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          {
            id: uid(), role: "error",
            content: err instanceof Error ? err.message : "Something went wrong.",
            timestamp: new Date(),
          },
        ]);
      } finally {
        setLoading(false);
        inputRef.current?.focus();
      }
    },
    [loading, sessionId]
  );

  // ── New chat ───────────────────────────────────────────────────────────────
  const newChat = useCallback(async () => {
    if (sessionId) await clearSession(sessionId).catch(() => {});
    setMessages([]);
    setSessionId(null);
    setInput("");
    inputRef.current?.focus();
  }, [sessionId]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(input); }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
  };

  // Not ready yet — show loading / retry status
  if (!sfReady) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-gray-500">
            {retryCount === 0
              ? "Connecting to backend…"
              : `Backend starting up… (attempt ${retryCount + 1} of ${MAX_RETRIES + 1})`}
          </p>
          {retryCount > 0 && (
            <p className="text-xs text-gray-400">This takes a few seconds on cold start</p>
          )}
        </div>
      </div>
    );
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* ── Header ───────────────────────────────────────────────────────── */}
      <header className="flex-shrink-0 bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
              />
            </svg>
          </div>
          <div>
            <h1 className="text-sm font-semibold text-gray-900">Salesforce AI Dashboard</h1>
            <p className="text-xs text-gray-500">Powered by Claude</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Connection badge */}
          {health && (
            <div className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full ${
              health.status === "ok"
                ? "bg-green-50 text-green-700 border border-green-200"
                : "bg-red-50 text-red-700 border border-red-200"
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${health.status === "ok" ? "bg-green-500" : "bg-red-500"}`} />
              {health.status === "ok" ? "Connected" : "Disconnected"}
            </div>
          )}

          {/* New Chat */}
          {messages.length > 0 && (
            <button
              onClick={newChat}
              className="text-xs text-gray-500 hover:text-gray-800 px-3 py-1.5 rounded-lg border border-gray-200 hover:border-gray-300 transition-colors"
            >
              New Chat
            </button>
          )}

          {/* User menu */}
          <div className="relative">
            <button
              onClick={() => setMenuOpen((o) => !o)}
              className="flex items-center gap-2 pl-2 pr-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors text-xs text-gray-700"
            >
              <div className="w-6 h-6 bg-blue-600 rounded-full flex items-center justify-center text-white text-[10px] font-bold">
                {(user?.name ?? user?.email ?? "U")[0].toUpperCase()}
              </div>
              <span className="hidden sm:block max-w-[120px] truncate">
                {user?.name ?? user?.email ?? "Account"}
              </span>
              <svg className="w-3 h-3 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {menuOpen && (
              <>
                {/* Backdrop */}
                <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                <div className="absolute right-0 top-full mt-1 w-48 bg-white border border-gray-200 rounded-xl shadow-lg z-20 overflow-hidden">
                  <div className="px-3 py-2 border-b border-gray-100">
                    <p className="text-xs text-gray-500 truncate">{user?.email}</p>
                  </div>
                  <button
                    onClick={() => { setMenuOpen(false); router.push("/connect"); }}
                    className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                  >
                    <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
                      />
                    </svg>
                    Manage Salesforce
                  </button>
                  <button
                    onClick={() => { setMenuOpen(false); logout(); }}
                    className="w-full text-left px-3 py-2 text-sm text-red-600 hover:bg-red-50 flex items-center gap-2"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
                      />
                    </svg>
                    Sign out
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </header>

      {/* ── Messages ──────────────────────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full min-h-[60vh] text-center">
              <div className="w-16 h-16 bg-blue-100 rounded-2xl flex items-center justify-center mb-4">
                <svg className="w-8 h-8 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
                  />
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-gray-800 mb-2">
                Ask anything about your Salesforce data
              </h2>
              <p className="text-sm text-gray-500 mb-8 max-w-sm">
                I can query leads, opportunities, accounts and more. Try one of these:
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-lg">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => submit(s)}
                    className="text-left text-sm bg-white border border-gray-200 rounded-xl px-4 py-3 hover:border-blue-300 hover:bg-blue-50 transition-colors text-gray-700"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg) => <ChatMessage key={msg.id} message={msg} />)
          )}

          {loading && (
            <div className="flex justify-start mb-4">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold mr-3 mt-1">
                AI
              </div>
              <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
                <div className="flex gap-1.5 items-center h-4">
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </main>

      {/* ── Input bar ─────────────────────────────────────────────────────── */}
      <footer className="flex-shrink-0 bg-white border-t border-gray-200 px-4 py-3 shadow-sm">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-end gap-2 bg-gray-50 border border-gray-300 rounded-2xl px-4 py-2 focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100 transition-all">
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Ask about your Salesforce data…"
              disabled={loading}
              className="flex-1 bg-transparent resize-none outline-none text-sm text-gray-800 placeholder-gray-400 py-1.5 max-h-[120px] disabled:opacity-50"
            />
            <button
              onClick={() => submit(input)}
              disabled={!input.trim() || loading}
              className="flex-shrink-0 w-8 h-8 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 rounded-xl flex items-center justify-center transition-colors mb-0.5"
              aria-label="Send"
            >
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
          <p className="text-xs text-gray-400 mt-1.5 text-center">
            Press Enter to send · Shift+Enter for new line · Read-only access
          </p>
        </div>
      </footer>
    </div>
  );
}
