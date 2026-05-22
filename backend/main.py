"""
FastAPI server — Sprint 2 · Day 13.

Routes:
  POST /api/query    — main agent endpoint (accepts plain-English query)
  GET  /api/health   — server + Salesforce connection status
  GET  /api/objects  — all queryable Salesforce object names

Run:
  uvicorn main:app --reload --port 8000
"""

import os
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent import run_agent
from sf_connector import get_available_objects, _connect

load_dotenv(Path(__file__).parent / ".env")

# ── App setup ──────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Salesforce AI Dashboard API",
    description="Natural language Salesforce queries powered by Claude AI",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("CORS_ORIGIN", "http://localhost:3000"), "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory session store ────────────────────────────────────────────────────
# Keyed by session_id → list of message dicts (conversation history).
# Cleared on server restart — good enough for demo; replace with Redis for prod.

_sessions: dict[str, list[dict]] = {}
MAX_HISTORY_TURNS = 10  # keep last N user+assistant pairs per session


# ── Request / Response models ──────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000,
                       description="Plain-English question about Salesforce data")
    session_id: str | None = Field(None,
                                   description="Session ID for multi-turn context. "
                                               "Omit to start a new session.")


class QueryResponse(BaseModel):
    session_id: str
    summary: str
    rows: list[dict]
    total_size: int
    row_count: int
    chart_type: str           # "table" | "bar" | "pie"
    insight: str | None
    soql: str | None
    response: str             # Claude's full text
    tool_calls: list[dict]
    error: str | None


class HealthResponse(BaseModel):
    status: str               # "ok" | "degraded"
    salesforce: str           # "connected" | "error: <msg>"
    version: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.post("/api/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    """
    Run the AI agent against Salesforce with a plain-English query.

    Pass `session_id` from a previous response to continue the conversation.
    Omit it (or pass null) to start fresh.
    """
    # Resolve session
    session_id = req.session_id or str(uuid.uuid4())
    history = _sessions.get(session_id, [])

    try:
        result = run_agent(req.query, conversation_history=history)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Update session history (store only user + final assistant messages)
    history.append({"role": "user",      "content": req.query})
    history.append({"role": "assistant", "content": result.get("response", "")})

    # Cap history length so context doesn't grow indefinitely
    if len(history) > MAX_HISTORY_TURNS * 2:
        history = history[-(MAX_HISTORY_TURNS * 2):]

    _sessions[session_id] = history

    return QueryResponse(
        session_id=session_id,
        summary=result.get("summary", ""),
        rows=result.get("rows", []),
        total_size=result.get("total_size", 0),
        row_count=result.get("row_count", 0),
        chart_type=result.get("chart_type", "table"),
        insight=result.get("insight"),
        soql=result.get("soql"),
        response=result.get("response", ""),
        tool_calls=result.get("tool_calls", []),
        error=result.get("error"),
    )


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """
    Returns server status and Salesforce connection state.
    Safe to call repeatedly — uses the cached SF connection.
    """
    try:
        _connect()
        sf_status = "connected"
    except Exception as exc:
        sf_status = f"error: {exc}"

    overall = "ok" if sf_status == "connected" else "degraded"

    return HealthResponse(
        status=overall,
        salesforce=sf_status,
        version=app.version,
    )


@app.get("/api/objects")
async def objects() -> dict[str, Any]:
    """
    Returns all queryable Salesforce object names in the connected org.
    Uses the 1-hour cache from sf_connector — fast after the first call.
    """
    try:
        obj_list = get_available_objects()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "count": len(obj_list),
        "objects": obj_list,
    }


@app.delete("/api/session/{session_id}")
async def clear_session(session_id: str) -> dict[str, str]:
    """Clear conversation history for a session (used by the 'New Chat' button)."""
    _sessions.pop(session_id, None)
    return {"status": "cleared", "session_id": session_id}
