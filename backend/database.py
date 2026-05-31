"""
database.py — PostgreSQL connection pool and schema initialisation.

Tables created on startup (idempotent):
  users                — app-level accounts (email + bcrypt password)
  sf_connections       — Salesforce OAuth tokens per user (Fernet-encrypted)
  conversation_sessions — chat history moved out of the in-memory dict
"""

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.pool
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── Connection pool ────────────────────────────────────────────────────────────

_pool: psycopg2.pool.SimpleConnectionPool | None = None


def _get_pool() -> psycopg2.pool.SimpleConnectionPool:
    global _pool
    if _pool is None:
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            # Railway / Heroku provide a single connection string
            _pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1, maxconn=20, dsn=database_url
            )
        else:
            # Local dev: individual vars
            _pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=20,
                host=os.environ["DB_HOST"],
                port=int(os.environ.get("DB_PORT", "5432")),
                dbname=os.environ["DB_NAME"],
                user=os.environ["DB_USER"],
                password=os.environ["DB_PASSWORD"],
            )
    return _pool


@contextmanager
def get_db():
    """Yield a psycopg2 connection; auto-commit on success, rollback on error."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# ── Schema init ────────────────────────────────────────────────────────────────

_DDL = """
-- Enable pgcrypto for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- App users
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name          VARCHAR(255),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Salesforce OAuth tokens (encrypted at rest)
CREATE TABLE IF NOT EXISTS sf_connections (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    access_token_enc    TEXT NOT NULL,
    refresh_token_enc   TEXT NOT NULL,
    instance_url        VARCHAR(500) NOT NULL,
    org_id              VARCHAR(255),
    sf_username         VARCHAR(255),
    connected_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_refreshed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (user_id)
);

-- Conversation history (replaces in-memory _sessions dict)
CREATE TABLE IF NOT EXISTS conversation_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id  VARCHAR(255) UNIQUE NOT NULL,
    history     JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Append-only message store (Stage 2) — one row per message, no lost updates
CREATE TABLE IF NOT EXISTS messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  VARCHAR(255) NOT NULL,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS messages_session_created ON messages (session_id, created_at);
"""


def init_db() -> None:
    """Create all tables. Safe to call on every startup (IF NOT EXISTS)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(_DDL)
    print("✓  Database tables initialised.")


# ── User helpers ───────────────────────────────────────────────────────────────

def create_user(email: str, password_hash: str, name: str | None = None) -> dict:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (email, password_hash, name)
                VALUES (%s, %s, %s)
                RETURNING id, email, name, created_at
                """,
                (email.lower().strip(), password_hash, name),
            )
            row = cur.fetchone()
    return {"id": str(row[0]), "email": row[1], "name": row[2], "created_at": str(row[3])}


def get_user_by_email(email: str) -> dict | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, password_hash, name, created_at FROM users WHERE email = %s",
                (email.lower().strip(),),
            )
            row = cur.fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "email": row[1],
        "password_hash": row[2],
        "name": row[3],
        "created_at": str(row[4]),
    }


def get_user_by_id(user_id: str) -> dict | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, name, created_at FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
    if not row:
        return None
    return {"id": str(row[0]), "email": row[1], "name": row[2], "created_at": str(row[3])}


# ── SF Connection helpers ──────────────────────────────────────────────────────

def upsert_sf_connection(
    user_id: str,
    access_token_enc: str,
    refresh_token_enc: str,
    instance_url: str,
    org_id: str | None = None,
    sf_username: str | None = None,
) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sf_connections
                    (user_id, access_token_enc, refresh_token_enc, instance_url, org_id, sf_username)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    access_token_enc  = EXCLUDED.access_token_enc,
                    refresh_token_enc = EXCLUDED.refresh_token_enc,
                    instance_url      = EXCLUDED.instance_url,
                    org_id            = EXCLUDED.org_id,
                    sf_username       = EXCLUDED.sf_username,
                    last_refreshed_at = NOW(),
                    is_active         = TRUE
                """,
                (user_id, access_token_enc, refresh_token_enc, instance_url, org_id, sf_username),
            )


def get_sf_connection(user_id: str) -> dict | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT access_token_enc, refresh_token_enc, instance_url,
                       org_id, sf_username, connected_at, last_refreshed_at
                FROM sf_connections
                WHERE user_id = %s AND is_active = TRUE
                """,
                (user_id,),
            )
            row = cur.fetchone()
    if not row:
        return None
    return {
        "access_token_enc": row[0],
        "refresh_token_enc": row[1],
        "instance_url": row[2],
        "org_id": row[3],
        "sf_username": row[4],
        "connected_at": str(row[5]),
        "last_refreshed_at": str(row[6]),
    }


def update_sf_access_token(user_id: str, access_token_enc: str) -> None:
    """Update only the access token after a refresh."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sf_connections
                SET access_token_enc = %s, last_refreshed_at = NOW()
                WHERE user_id = %s
                """,
                (access_token_enc, user_id),
            )


def delete_sf_connection(user_id: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sf_connections SET is_active = FALSE WHERE user_id = %s",
                (user_id,),
            )


# ── Conversation session helpers ───────────────────────────────────────────────

MAX_HISTORY_TURNS = 10  # keep last N user+assistant pairs


def get_session_history(user_id: str, session_id: str) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT history FROM conversation_sessions
                WHERE session_id = %s AND user_id = %s
                """,
                (session_id, user_id),
            )
            row = cur.fetchone()
    if not row:
        return []
    return row[0] if isinstance(row[0], list) else json.loads(row[0])


def upsert_session_history(user_id: str, session_id: str, history: list[dict]) -> None:
    # Cap length before saving
    if len(history) > MAX_HISTORY_TURNS * 2:
        history = history[-(MAX_HISTORY_TURNS * 2):]

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversation_sessions (user_id, session_id, history)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT (session_id) DO UPDATE SET
                    history    = EXCLUDED.history,
                    updated_at = NOW()
                """,
                (user_id, session_id, json.dumps(history)),
            )


def delete_session(user_id: str, session_id: str) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM conversation_sessions WHERE session_id = %s AND user_id = %s",
                (session_id, user_id),
            )
            cur.execute(
                "DELETE FROM messages WHERE session_id = %s AND user_id = %s",
                (session_id, user_id),
            )


# ── Append-only message helpers (Stage 2) ─────────────────────────────────────

def append_message(user_id: str, session_id: str, role: str, content: str) -> None:
    """Insert a single message row. Never overwrites — two concurrent calls both succeed."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (session_id, user_id, role, content) VALUES (%s, %s, %s, %s)",
                (session_id, user_id, role, content),
            )


def get_session_messages(
    user_id: str,
    session_id: str,
    limit: int = MAX_HISTORY_TURNS * 2,
) -> list[dict]:
    """Return the last `limit` messages for a session, oldest first."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content FROM (
                    SELECT role, content, created_at
                    FROM messages
                    WHERE session_id = %s AND user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                ) sub
                ORDER BY created_at
                """,
                (session_id, user_id, limit),
            )
            rows = cur.fetchall()
    return [{"role": r[0], "content": r[1]} for r in rows]
