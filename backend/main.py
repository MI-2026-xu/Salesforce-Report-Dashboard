"""
main.py — FastAPI server with multi-user auth + Salesforce OAuth 2.0.

Auth routes (no JWT required):
  POST /auth/register       — create account
  POST /auth/login          — returns JWT
  GET  /auth/salesforce     — redirect browser → Salesforce OAuth screen
  GET  /auth/callback       — exchange code → store tokens → redirect frontend

Protected routes (Bearer JWT required):
  GET  /auth/me             — current user profile
  GET  /auth/sf-status      — SF connection status for current user
  DELETE /auth/sf-disconnect — remove SF tokens for current user
  POST /api/query           — run AI agent against user's Salesforce org
  GET  /api/health          — health (uses user's SF connection)
  GET  /api/objects         — object list from user's org
  DELETE /api/session/{id}  — clear conversation history

Run locally:
  uvicorn main:app --reload --port 8000

Production (Railway reads PORT automatically via Procfile):
  web: uvicorn main:app --host 0.0.0.0 --port $PORT
"""

import os
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel, EmailStr, Field
from simple_salesforce import Salesforce

from agent import run_agent
from auth import (
    create_access_token,
    create_state_token,
    decode_state_token,
    generate_pkce_pair,
    hash_password,
    verify_password,
)
from crypto import decrypt, encrypt
from database import (
    append_message,
    create_user,
    delete_session,
    delete_sf_connection,
    get_session_messages,
    get_sf_connection,
    get_user_by_email,
    get_user_by_id,
    init_db,
    update_sf_access_token,
    upsert_sf_connection,
)
from sf_connector import (
    connect_with_tokens,
    get_available_objects,
    refresh_access_token,
)

load_dotenv(Path(__file__).parent / ".env")

# ── App setup ──────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Salesforce AI Dashboard API",
    description="Natural language Salesforce queries powered by Claude AI — multi-user",
    version="2.0.0",
)

# ALLOWED_ORIGINS accepts a comma-separated list so both local and production
# URLs can be whitelisted from a single env var.
# Example: ALLOWED_ORIGINS=https://your-app.vercel.app,http://localhost:3000
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_SF_CONSUMER_KEY    = os.environ["SF_CONSUMER_KEY"]
_SF_CONSUMER_SECRET = os.environ["SF_CONSUMER_SECRET"]
_SF_DOMAIN          = os.environ.get("SF_DOMAIN", "login")
_APP_URL            = os.environ.get("APP_URL", "http://localhost:8000")
_FRONTEND_URL       = os.environ.get("FRONTEND_URL", "http://localhost:3000")
_SF_CALLBACK_URL    = f"{_APP_URL}/auth/callback"


# ── Startup ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup() -> None:
    init_db()


# ── Auth dependency ────────────────────────────────────────────────────────────

_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """
    FastAPI dependency — verifies the Bearer JWT and returns the user dict.
    Raises HTTP 401 on invalid / expired tokens.
    """
    try:
        from auth import get_user_id_from_token
        user_id = get_user_id_from_token(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_sf_for_user(user: dict = Depends(get_current_user)) -> Salesforce:
    """
    FastAPI dependency — loads the user's Salesforce connection from DB,
    decrypts the tokens, and returns a live Salesforce client.

    Token refresh is protected by a 30-second Redis lock so that two
    simultaneous requests for the same user never both call Salesforce's
    refresh endpoint (which would invalidate the first token).
    """
    from redis_client import get_redis

    conn = get_sf_connection(user["id"])
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No Salesforce account connected. Please visit /connect to link your org.",
        )

    access_token  = decrypt(conn["access_token_enc"])
    refresh_token = decrypt(conn["refresh_token_enc"])
    instance_url  = conn["instance_url"]

    sf = connect_with_tokens(access_token, instance_url)

    # Quick connectivity check — refresh token if stale
    try:
        sf.restful("sobjects/")
    except Exception:
        r = get_redis()
        lock_key = f"sf:refresh-lock:{user['id']}"

        got_lock = r.set(lock_key, "1", nx=True, ex=30)
        if got_lock:
            try:
                new_access = refresh_access_token(refresh_token, instance_url)
                update_sf_access_token(user["id"], encrypt(new_access))
                sf = connect_with_tokens(new_access, instance_url)
            except ConnectionError as exc:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Salesforce session expired and could not be refreshed: {exc}",
                )
            finally:
                r.delete(lock_key)
        else:
            # Another request is mid-refresh — wait for it, then read the new token
            time.sleep(1)
            fresh = get_sf_connection(user["id"])
            if fresh:
                sf = connect_with_tokens(decrypt(fresh["access_token_enc"]), instance_url)

    return sf


# ── Request / Response models ──────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Password (min 8 chars)")
    name: str | None = Field(None, description="Display name")


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user: dict


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    session_id: str | None = Field(None, description="Omit to start a new session")


class QueryResponse(BaseModel):
    session_id: str
    summary: str
    rows: list[dict]
    total_size: int
    row_count: int
    chart_type: str
    insight: str | None
    soql: str | None
    response: str
    tool_calls: list[dict]
    error: str | None



# ── Auth routes ────────────────────────────────────────────────────────────────

@app.post("/auth/register", response_model=AuthResponse, status_code=201)
async def register(req: RegisterRequest) -> AuthResponse:
    """Create a new account and return a JWT."""
    if get_user_by_email(req.email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    try:
        user = create_user(
            email=req.email,
            password_hash=hash_password(req.password),
            name=req.name,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not create user: {exc}")

    token = create_access_token(user["id"])
    return AuthResponse(token=token, user={k: v for k, v in user.items() if k != "password_hash"})


@app.post("/auth/login", response_model=AuthResponse)
async def login(req: LoginRequest) -> AuthResponse:
    """Verify credentials and return a JWT."""
    user = get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = create_access_token(user["id"])
    return AuthResponse(token=token, user={k: v for k, v in user.items() if k != "password_hash"})


@app.get("/auth/me")
async def me(current_user: dict = Depends(get_current_user)) -> dict:
    """Return the current user's profile (no password hash)."""
    return {k: v for k, v in current_user.items() if k != "password_hash"}


@app.get("/auth/sf-status")
async def sf_status(current_user: dict = Depends(get_current_user)) -> dict:
    """Check whether this user has a Salesforce org connected."""
    conn = get_sf_connection(current_user["id"])
    if not conn:
        return {"connected": False}
    return {
        "connected": True,
        "instance_url": conn["instance_url"],
        "sf_username": conn.get("sf_username"),
        "org_id": conn.get("org_id"),
        "connected_at": conn.get("connected_at"),
    }


@app.delete("/auth/sf-disconnect")
async def sf_disconnect(current_user: dict = Depends(get_current_user)) -> dict:
    """Remove the stored Salesforce tokens for this user."""
    delete_sf_connection(current_user["id"])
    return {"status": "disconnected"}


# ── Debug endpoint (no auth) ──────────────────────────────────────────────────

@app.get("/auth/debug")
async def oauth_debug() -> dict:
    """
    Returns the exact OAuth configuration this server will use.
    Visit http://localhost:8000/auth/debug in your browser and compare
    'callback_url' with what is registered in Salesforce Setup → App Manager
    → your Connected App → Manage Consumer Details → Callback URL.
    They must match character-for-character (case-sensitive, no trailing slash).
    """
    from auth import generate_pkce_pair
    _, sample_challenge = generate_pkce_pair()

    sample_params = urlencode({
        "response_type":         "code",
        "client_id":             _SF_CONSUMER_KEY[:12] + "...",   # truncated for safety
        "redirect_uri":          _SF_CALLBACK_URL,
        "scope":                 "api refresh_token",
        "code_challenge":        sample_challenge[:12] + "...",
        "code_challenge_method": "S256",
        "state":                 "<jwt>",
    })

    return {
        "callback_url":  _SF_CALLBACK_URL,
        "sf_domain":     _SF_DOMAIN,
        "scopes":        ["api", "refresh_token"],
        "pkce_method":   "S256",
        "sample_auth_url": f"https://{_SF_DOMAIN}.salesforce.com/services/oauth2/authorize?{sample_params}",
        "checklist": [
            f"1. In Salesforce Setup → App Manager → your app → Manage Consumer Details → "
            f"Callback URL must contain exactly: {_SF_CALLBACK_URL}",
            "2. OAuth Policies → Permitted Users must be 'All users may self-authorize'",
            "3. Selected OAuth Scopes must include: 'Access and manage your data (api)' "
            "AND 'Perform requests on your behalf at any time (refresh_token, offline_access)'",
            "4. If 'Require Proof Key for Code Exchange (PKCE)' is ON in the Connected App, "
            "that is fine — our code sends code_challenge + code_verifier correctly.",
        ],
    }


# ── Salesforce OAuth 2.0 Web Server Flow ──────────────────────────────────────

@app.get("/auth/salesforce")
async def salesforce_oauth_start(
    request: Request,
    token: str | None = None,
    switch: bool = False,        # ?switch=true → force Salesforce login screen
    current_user: dict | None = None,
) -> RedirectResponse:
    """
    Step 1 — Redirect the browser to Salesforce's OAuth consent screen.

    Accepts the JWT either as a Bearer header (normal API calls) OR as a
    `?token=` query param (browser redirect from the Connect page cannot
    send custom headers, so we allow the query-param fallback here only).

    ?switch=true adds `prompt=login` to the Salesforce URL, which forces
    the Salesforce login page even if the browser already has an active
    Salesforce session. Use this to connect a different Salesforce account.
    """
    from auth import get_user_id_from_token
    from jose import JWTError as _JWTError

    # Resolve user: prefer Authorization header, fall back to ?token= param
    if current_user is None:
        raw_token = token
        if raw_token is None:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                raw_token = auth_header[7:]
        if not raw_token:
            raise HTTPException(status_code=401, detail="Authentication required")
        try:
            user_id = get_user_id_from_token(raw_token)
        except _JWTError:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        user = get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        current_user = user

    # Generate PKCE pair — verifier is stored in the state JWT so we can
    # retrieve it at /auth/callback without any server-side session store.
    code_verifier, code_challenge = generate_pkce_pair()
    state = create_state_token(current_user["id"], code_verifier)

    oauth_params: dict = {
        "response_type":         "code",
        "client_id":             _SF_CONSUMER_KEY,
        "redirect_uri":          _SF_CALLBACK_URL,
        "state":                 state,
        # "offline_access" is NOT requested — many Connected Apps don't have it
        # enabled and Salesforce rejects with OAUTH_APPROVAL_ERROR_GENERIC.
        # "refresh_token" alone is sufficient for long-lived access.
        "scope":                 "api refresh_token",
        "code_challenge":        code_challenge,
        "code_challenge_method": "S256",
    }

    # Force Salesforce to show the login screen (ignore existing browser session).
    # Used when the user wants to connect a different Salesforce account.
    if switch:
        oauth_params["prompt"] = "login"

    params   = urlencode(oauth_params)
    auth_url = f"https://{_SF_DOMAIN}.salesforce.com/services/oauth2/authorize?{params}"
    print(f"[OAuth] Redirecting. callback={_SF_CALLBACK_URL!r} switch={switch}")
    return RedirectResponse(url=auth_url)


@app.get("/auth/callback")
async def salesforce_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    """
    Step 2 — Salesforce redirects here after user approval.
    Exchange the code for tokens, store them encrypted, redirect to frontend.
    """
    frontend_connect = f"{_FRONTEND_URL}/connect"

    # User denied or Salesforce error — surface the full description so we
    # can see exactly what Salesforce is objecting to.
    if error:
        desc = error_description or ""
        print(f"[OAuth callback] Salesforce returned error: {error!r}  desc: {desc!r}")
        import urllib.parse as _ul
        msg = _ul.quote(f"{error}: {desc}" if desc else error)
        return RedirectResponse(url=f"{frontend_connect}?error={msg}")

    if not code or not state:
        return RedirectResponse(url=f"{frontend_connect}?error=missing_params")

    # Verify state → get user_id + PKCE code_verifier
    try:
        user_id, code_verifier = decode_state_token(state)
    except JWTError:
        return RedirectResponse(url=f"{frontend_connect}?error=invalid_state")

    # Exchange authorisation code for tokens (include code_verifier for PKCE)
    resp = requests.post(
        f"https://{_SF_DOMAIN}.salesforce.com/services/oauth2/token",
        data={
            "grant_type":    "authorization_code",
            "code":          code,
            "client_id":     _SF_CONSUMER_KEY,
            "client_secret": _SF_CONSUMER_SECRET,
            "redirect_uri":  _SF_CALLBACK_URL,
            "code_verifier": code_verifier,   # PKCE — must match the challenge sent earlier
        },
        timeout=30,
    )

    if resp.status_code != 200:
        try:
            err_body = resp.json()
        except Exception:
            err_body = {"raw": resp.text}
        print(f"[OAuth callback] Token exchange failed {resp.status_code}: {err_body}")
        import urllib.parse as _ul
        err_msg = err_body.get("error_description") or err_body.get("error") or "token_exchange_failed"
        return RedirectResponse(url=f"{frontend_connect}?error={_ul.quote(err_msg)}")

    data = resp.json()
    access_token  = data["access_token"]
    refresh_token = data.get("refresh_token", "")
    instance_url  = data["instance_url"]

    # Fetch org ID and username from the identity endpoint
    org_id      = None
    sf_username = None
    try:
        identity_resp = requests.get(
            data["id"],
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        if identity_resp.status_code == 200:
            id_data     = identity_resp.json()
            org_id      = id_data.get("organization_id")
            sf_username = id_data.get("username")
    except Exception:
        pass  # non-fatal — store connection anyway

    # Persist encrypted tokens
    upsert_sf_connection(
        user_id=user_id,
        access_token_enc=encrypt(access_token),
        refresh_token_enc=encrypt(refresh_token),
        instance_url=instance_url,
        org_id=org_id,
        sf_username=sf_username,
    )

    return RedirectResponse(url=f"{_FRONTEND_URL}/?sf=connected")


# ── Query route ────────────────────────────────────────────────────────────────

@app.post("/api/query", response_model=QueryResponse)
async def query(
    req: QueryRequest,
    current_user: dict = Depends(get_current_user),
    sf: Salesforce = Depends(get_sf_for_user),
) -> QueryResponse:
    """Run the AI agent against the user's Salesforce org."""
    session_id = req.session_id or str(uuid.uuid4())
    history    = get_session_messages(current_user["id"], session_id)

    try:
        result = run_agent(req.query, sf=sf, conversation_history=history)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Persist — two appends can never overwrite each other (no lost updates)
    append_message(current_user["id"], session_id, "user",      req.query)
    append_message(current_user["id"], session_id, "assistant", result.get("response", ""))

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


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health() -> dict:
    """Lightweight health check — no auth, no SF call. For load balancers. <50 ms."""
    return {"status": "ok", "version": app.version}


@app.get("/api/health/deep")
async def health_deep(
    current_user: dict = Depends(get_current_user),
    sf: Salesforce = Depends(get_sf_for_user),
) -> dict:
    """Full health check — verifies SF connectivity. For monitoring dashboards."""
    try:
        sf.restful("sobjects/")
        return {"status": "ok", "salesforce": "connected", "version": app.version}
    except Exception as exc:
        return {"status": "degraded", "salesforce": f"error: {exc}", "version": app.version}


@app.get("/api/objects")
async def objects(
    current_user: dict = Depends(get_current_user),
    sf: Salesforce = Depends(get_sf_for_user),
) -> dict[str, Any]:
    """Returns queryable Salesforce object names from the user's org."""
    try:
        obj_list = get_available_objects(sf)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"count": len(obj_list), "objects": obj_list}


@app.delete("/api/session/{session_id}")
async def clear_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict[str, str]:
    """Clear conversation history for a session."""
    delete_session(current_user["id"], session_id)
    return {"status": "cleared", "session_id": session_id}
