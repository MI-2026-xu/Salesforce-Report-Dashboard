"use client";

/**
 * Main chat page — Sprint 3 · Days 16–17.
 *
 * Layout: fixed header → scrollable message list → sticky input bar.
 * State: messages[], sessionId, loading, health status.
 */

import { useState, useRef, useEffect, useCallback } from "react";
import ChatMessage from "@/components/ChatMessage";
import { sendQuery, fetchHealth, clearSession } from "@/lib/api";
import type { ChatMessage as ChatMessageType, HealthResponse } from "@/types";

// Tiny ID generator — avoids adding the uuid dep just for this
function uid() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

// ── Suggested queries shown on the empty state ────────────────────────────────
const SUGGESTIONS = [
  "How many leads do we have in total?",
  "Show me leads breakdown by status",
  "Top 5 opportunities by amount",
  "Show me all accounts by industry",
];

export default function Home() {
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // ── Health check on mount ─────────────────────────────────────────────────
  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() =>
        setHealth({ status: "degraded", salesforce: "unreachable", version: "—" })
      );
  }, []);

  // ── Auto-scroll to bottom on new messages ────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Submit ────────────────────────────────────────────────────────────────
  const submit = useCallback(
    async (query: string) => {
      const trimmed = query.trim();
      if (!trimmed || loading) return;

      setInput("");
      setLoading(true);

      // Append user message immediately
      const userMsg: ChatMessageType = {
        id: uid(),
        role: "user",
        content: trimmed,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);

      try {
        const data = await sendQuery(trimmed, sessionId);

        // Persist session for multi-turn
        setSessionId(data.session_id);

        const assistantMsg: ChatMessageType = {
          id: uid(),
          role: "assistant",
          content: data.summary || data.response,
          data,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        const errorMsg: ChatMessageType = {
          id: uid(),
          role: "error",
          content:
            err instanceof Error
              ? err.message
              : "Something went wrong. Is the backend running?",
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, errorMsg]);
      } finally {
        setLoading(false);
        inputRef.current?.focus();
      }
    },
    [loading, sessionId]
  );

  // ── New chat ──────────────────────────────────────────────────────────────
  const newChat = useCallback(async () => {
    if (sessionId) await clearSession(sessionId).catch(() => {});
    setMessages([]);
    setSessionId(null);
    setInput("");
    inputRef.current?.focus();
  }, [sessionId]);

  // ── Keyboard: Enter submits, Shift+Enter = newline ────────────────────────
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(input);
    }
  };

  // ── Auto-resize textarea ──────────────────────────────────────────────────
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* ── Header ─────────────────────────────────────────────────────── */}
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
              <span className={`w-1.5 h-1.5 rounded-full ${
                health.status === "ok" ? "bg-green-500" : "bg-red-500"
              }`} />
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
        </div>
      </header>

      {/* ── Messages ───────────────────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto">
          {messages.length === 0 ? (
            /* Empty state */
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
            messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} />
            ))
          )}

          {/* Loading indicator */}
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

      {/* ── Input bar ──────────────────────────────────────────────────── */}
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
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                />
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
