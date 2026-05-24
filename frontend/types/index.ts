// ── API Types ────────────────────────────────────────────────────────────────

export interface QueryRequest {
  query: string;
  session_id?: string | null;
}

export interface QueryResponse {
  session_id: string;
  summary: string;
  rows: Record<string, unknown>[];
  total_size: number;
  row_count: number;
  chart_type: "table" | "bar" | "pie";
  insight: string | null;
  soql: string | null;
  response: string;
  tool_calls: ToolCall[];
  error: string | null;
}

export interface ToolCall {
  tool: string;
  input: Record<string, unknown>;
  status: "ok" | "error" | "retry";
  result_summary: string;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  salesforce: string;
  version: string;
}

// ── Chat Types ───────────────────────────────────────────────────────────────

export type MessageRole = "user" | "assistant" | "error";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  data?: QueryResponse;   // present on assistant messages that have data
  timestamp: Date;
}
