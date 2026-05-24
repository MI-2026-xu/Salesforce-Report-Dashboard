"use client";

/**
 * ChatMessage — renders a single chat bubble.
 *
 * User messages: right-aligned dark bubble.
 * Assistant messages: left-aligned with optional data panel (table / chart).
 * Error messages: left-aligned red pill.
 *
 * ResultChart is loaded client-only (recharts uses window/document).
 */

import dynamic from "next/dynamic";
import { ChatMessage as ChatMessageType } from "@/types";
import ResultTable from "./ResultTable";

// SSR=false: recharts reads window.innerWidth on mount — crashes on server
const ResultChart = dynamic(() => import("./ResultChart"), { ssr: false });

interface Props {
  message: ChatMessageType;
}

export default function ChatMessage({ message }: Props) {
  const isUser = message.role === "user";
  const isError = message.role === "error";
  const data = message.data;

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      {/* Avatar */}
      {!isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold mr-3 mt-1">
          AI
        </div>
      )}

      <div className={`${isUser ? "max-w-[75%] items-end" : "max-w-[90%] items-start"} flex flex-col gap-2`}>
        {/* Bubble */}
        <div
          className={`px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
            isUser
              ? "bg-blue-600 text-white rounded-br-sm"
              : isError
              ? "bg-red-50 text-red-700 border border-red-200 rounded-bl-sm"
              : "bg-white text-gray-800 border border-gray-200 rounded-bl-sm shadow-sm"
          }`}
        >
          {message.content}
        </div>

        {/* Data panel — only on assistant messages with rows */}
        {data && data.rows.length > 0 && (
          <div className="w-full bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
            {/* Insight pill */}
            {data.insight && (
              <div className="bg-blue-50 border-b border-blue-100 px-4 py-2 text-xs text-blue-700 font-medium">
                💡 {data.insight}
              </div>
            )}

            {/* Chart or table */}
            {data.chart_type !== "table" ? (
              <ResultChart rows={data.rows} chartType={data.chart_type} />
            ) : (
              <ResultTable rows={data.rows} totalSize={data.total_size} />
            )}

            {/* SOQL debug */}
            {data.soql && (
              <details className="border-t border-gray-100">
                <summary className="px-4 py-2 text-xs text-gray-400 cursor-pointer hover:text-gray-600 select-none">
                  🔍 View SOQL
                </summary>
                <pre className="px-4 pb-3 text-xs text-gray-600 font-mono bg-gray-50 overflow-x-auto whitespace-pre-wrap">
                  {data.soql}
                </pre>
              </details>
            )}
          </div>
        )}

        {/* Tool call trace — collapsible, shown even when no rows (e.g. clarification) */}
        {data && data.tool_calls.length > 0 && (
          <details className="w-full">
            <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600 select-none">
              ⚙ {data.tool_calls.length} step{data.tool_calls.length !== 1 ? "s" : ""} taken
            </summary>
            <div className="mt-1.5 bg-gray-50 border border-gray-200 rounded-xl overflow-hidden divide-y divide-gray-100">
              {data.tool_calls.map((tc, i) => (
                <div key={i} className="px-3 py-2 flex items-start gap-2">
                  {/* Status dot */}
                  <span className={`mt-0.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                    tc.status === "ok"    ? "bg-green-500" :
                    tc.status === "retry" ? "bg-amber-400" :
                                           "bg-red-500"
                  }`} />
                  <div className="min-w-0">
                    <span className="text-xs font-mono font-medium text-gray-700">
                      {tc.tool}()
                    </span>
                    <span className="text-xs text-gray-400 ml-2">
                      → {tc.result_summary}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </details>
        )}

        {/* Timestamp */}
        <span className="text-xs text-gray-400">
          {message.timestamp.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
      </div>

      {/* User avatar */}
      {isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gray-700 flex items-center justify-center text-white text-xs font-bold ml-3 mt-1">
          You
        </div>
      )}
    </div>
  );
}
