"""
sf_connector.py — Salesforce connector (multi-user, per-request connections).

Public API:
  connect_with_tokens(access_token, instance_url)  → Salesforce instance
  refresh_access_token(refresh_token, instance_url) → new access_token str
  get_schema(object_name, sf)                       → {object, label, queryable, fields}
  run_soql(query, sf)                               → {total_size, records}
  get_available_objects(sf)                         → [object_name, ...]

Schema / objects results are cached per instance_url for 1 hour so repeated
calls within a session stay fast without hitting the Salesforce API.
"""

import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from simple_salesforce import Salesforce

from redis_client import get_redis

load_dotenv(Path(__file__).parent / ".env")

_SCHEMA_TTL = 3600  # seconds — Redis key TTL for schema / object-list cache


# ── Connection factory ─────────────────────────────────────────────────────────

def connect_with_tokens(access_token: str, instance_url: str) -> Salesforce:
    """
    Build a Salesforce client from an existing OAuth access token.
    No network call here — the token is used lazily on the first API request.
    """
    return Salesforce(session_id=access_token, instance_url=instance_url)


def refresh_access_token(refresh_token: str, instance_url: str) -> str:
    """
    Use a Salesforce refresh token to obtain a new access token.

    Returns:
        New access_token string.

    Raises:
        ConnectionError if the refresh fails (e.g. token revoked).
    """
    resp = requests.post(
        f"{instance_url}/services/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "client_id": os.environ["SF_CONSUMER_KEY"],
            "client_secret": os.environ["SF_CONSUMER_SECRET"],
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        err = resp.json()
        raise ConnectionError(
            f"Salesforce token refresh failed — {err.get('error')}: {err.get('error_description', resp.text)}"
        )
    return resp.json()["access_token"]


# ── get_schema (Redis cache, 1 hr TTL) ────────────────────────────────────────

def get_schema(object_name: str, sf: Salesforce) -> dict[str, Any]:
    """
    Return the field schema for a Salesforce object.

    Results are cached in Redis per org for 1 hour, shared across all pods.

    Returns:
        {
          "object":    "Lead",
          "label":     "Lead",
          "queryable": True,
          "fields":    {"FieldName": "fieldtype", ...},
          "cached":    True | False
        }

    Raises:
        ValueError      if the object doesn't exist or isn't accessible
        ConnectionError if the token is expired (caller should refresh)
    """
    r = get_redis()
    redis_key = f"sf:schema:{sf.base_url}:{object_name}"

    raw = r.get(redis_key)
    if raw:
        return {**json.loads(raw), "cached": True}

    try:
        describe = sf.restful(f"sobjects/{object_name}/describe/")
    except Exception as exc:
        msg = str(exc)
        if "NOT_FOUND" in msg or "not found" in msg.lower() or "404" in msg:
            raise ValueError(f"Salesforce object '{object_name}' not found.")
        raise ValueError(f"Could not describe '{object_name}': {exc}")

    schema = {
        "object":    object_name,
        "label":     describe.get("label", object_name),
        "queryable": describe.get("queryable", True),
        "fields":    {field["name"]: field["type"] for field in describe["fields"]},
        "cached":    False,
    }

    r.set(redis_key, json.dumps(schema), ex=_SCHEMA_TTL)
    return schema


def flush_schema(object_name: str, instance_url: str) -> int:
    """Delete all cached schema keys for a given object across all orgs (or one org).
    Returns the number of keys deleted."""
    r = get_redis()
    pattern = f"sf:schema:*{instance_url}*:{object_name}" if instance_url else f"sf:schema:*:{object_name}"
    keys = r.keys(pattern)
    if keys:
        return r.delete(*keys)
    return 0


# ── run_soql ───────────────────────────────────────────────────────────────────

def run_soql(query: str, sf: Salesforce) -> dict[str, Any]:
    """
    Execute a SOQL query and return clean records with SF metadata stripped.

    Uses query_all() which handles pagination automatically.

    Returns:
        {
          "total_size": 42,
          "records":    [{"Id": "...", "Name": "..."}, ...]
        }

    Raises:
        ValueError      if the query is malformed or references invalid fields
        ConnectionError if the token is expired
    """
    try:
        result = sf.query_all(query)
    except Exception as exc:
        raise ValueError(f"SOQL query failed: {exc}")

    records = [
        {k: v for k, v in record.items() if k != "attributes"}
        for record in result.get("records", [])
    ]

    return {
        "total_size": result.get("totalSize", len(records)),
        "records":    records,
    }


# ── get_available_objects ──────────────────────────────────────────────────────

def get_available_objects(sf: Salesforce) -> list[str]:
    """
    Return sorted list of all queryable Salesforce object names in this org.
    Cached in Redis per org for 1 hour.

    Raises:
        ConnectionError if the token is expired
    """
    r = get_redis()
    redis_key = f"sf:objects:{sf.base_url}"

    raw = r.get(redis_key)
    if raw:
        return json.loads(raw)

    try:
        describe = sf.describe()
    except Exception as exc:
        raise ConnectionError(f"Could not fetch object list: {exc}")

    objects = sorted(
        obj["name"]
        for obj in describe["sobjects"]
        if obj.get("queryable", False)
    )

    r.set(redis_key, json.dumps(objects), ex=_SCHEMA_TTL)
    return objects
