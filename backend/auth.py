"""
auth.py — JWT token helpers, bcrypt password utilities, and PKCE helpers.

JWT payload:  {"sub": "<user_id_uuid>", "exp": <unix_timestamp>}
Algorithm:    HS256
Secret:       JWT_SECRET env var (generate with: python -c "import secrets; print(secrets.token_hex(32))")

PKCE (RFC 7636) is required by Salesforce when the Connected App has
"Require Proof Key for Code Exchange" enabled.  The code_verifier is
embedded inside the short-lived state JWT so no server-side store is needed.
"""

import hashlib
import base64
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from jose import JWTError, jwt
from passlib.context import CryptContext

load_dotenv(Path(__file__).parent / ".env")

_SECRET = os.environ["JWT_SECRET"]
_ALGORITHM = "HS256"
_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "10080"))  # 7 days default

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password helpers ───────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


# ── JWT helpers ────────────────────────────────────────────────────────────────

def create_access_token(user_id: str) -> str:
    """Create a signed JWT for a given user_id (UUID string)."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT.
    Raises jose.JWTError on invalid / expired tokens.
    Returns the full payload dict (includes "sub" and "exp").
    """
    return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])


def get_user_id_from_token(token: str) -> str:
    """
    Convenience wrapper — returns just the user_id (sub) string.
    Raises JWTError if token is invalid or expired.
    """
    payload = decode_token(token)
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise JWTError("Token missing 'sub' claim")
    return user_id


# ── PKCE helpers (RFC 7636) ────────────────────────────────────────────────────

def generate_pkce_pair() -> tuple[str, str]:
    """
    Generate a PKCE (code_verifier, code_challenge) pair.

    code_verifier  — cryptographically random URL-safe string (86 chars)
    code_challenge — BASE64URL(SHA-256(code_verifier)), no padding

    Both are returned; the verifier is stored in the state JWT and sent at
    token-exchange time; the challenge goes in the authorisation URL.
    """
    code_verifier  = secrets.token_urlsafe(64)          # 86 URL-safe chars
    digest         = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


# ── State token for Salesforce OAuth CSRF + PKCE ──────────────────────────────
# We encode the user_id AND the PKCE code_verifier in a short-lived JWT used
# as the OAuth `state` param.  This binds the callback to the correct user
# without needing any server-side session store.

_STATE_EXPIRE_MINUTES = 15


def create_state_token(user_id: str, code_verifier: str) -> str:
    """
    Short-lived (15 min) JWT embedded in the SF OAuth `state` param.
    Carries both the user_id (sub) and the PKCE code_verifier (cv).
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=_STATE_EXPIRE_MINUTES)
    payload = {
        "sub":     user_id,
        "exp":     expire,
        "purpose": "sf_oauth_state",
        "cv":      code_verifier,      # PKCE verifier — recovered at /auth/callback
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def decode_state_token(state: str) -> tuple[str, str]:
    """
    Verify the state JWT and return (user_id, code_verifier).
    Raises JWTError if the token is invalid, expired, or tampered with.
    """
    payload = jwt.decode(state, _SECRET, algorithms=[_ALGORITHM])
    if payload.get("purpose") != "sf_oauth_state":
        raise JWTError("Invalid state token purpose")
    user_id: str | None = payload.get("sub")
    code_verifier: str | None = payload.get("cv")
    if not user_id or not code_verifier:
        raise JWTError("State token missing required claims")
    return user_id, code_verifier
