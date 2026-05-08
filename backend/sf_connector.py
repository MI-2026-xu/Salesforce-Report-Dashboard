"""
Layer 4 — Salesforce connector.

Public API:
  get_schema(object_name)       → {object, label, queryable, fields}
  run_soql(query)               → {total_size, records}
  get_available_objects()       → [object_name, ...]
"""

import os
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from simple_salesforce import Salesforce

load_dotenv(Path(__file__).parent / ".env")

_SCHEMA_TTL = 3600  # seconds — re-fetch schema after 1 hour

# ── Module-level singletons ────────────────────────────────────────────────────
_sf: Salesforce | None = None
_schema_cache: dict[str, tuple[dict, float]] = {}   # {object_name: (schema, timestamp)}
_objects_cache: tuple[list[str], float] | None = None


def _connect() -> Salesforce:
    """Return a cached Salesforce session, authenticating if needed."""
    global _sf
    if _sf is not None:
        return _sf

    domain = os.environ["SF_DOMAIN"]
    password_with_token = os.environ["SF_PASSWORD"] + os.environ.get("SF_SECURITY_TOKEN", "")

    resp = requests.post(
        f"https://{domain}.salesforce.com/services/oauth2/token",
        data={
            "grant_type": "password",
            "client_id": os.environ["SF_CONSUMER_KEY"],
            "client_secret": os.environ["SF_CONSUMER_SECRET"],
            "username": os.environ["SF_USERNAME"],
            "password": password_with_token,
        },
        timeout=30,
    )

    if resp.status_code != 200:
        err = resp.json()
        raise ConnectionError(
            f"Salesforce OAuth failed — {err.get('error')}: {err.get('error_description', resp.text)}"
        )

    data = resp.json()
    _sf = Salesforce(session_id=data["access_token"], instance_url=data["instance_url"])
    return _sf


# ── get_schema (with 1hr cache) ────────────────────────────────────────────────

def get_schema(object_name: str) -> dict[str, Any]:
    """
    Return the field schema for a Salesforce object.

    Results are cached for 1 hour — repeated calls within that window
    return instantly without hitting the Salesforce API.

    Returns:
        {
          "object": "Lead",
          "label": "Lead",
          "queryable": True,
          "fields": {"FieldName": "fieldtype", ...},
          "cached": True | False
        }

    Raises:
        ValueError      if the object doesn't exist or isn't accessible
        ConnectionError if authentication fails
    """
    cached, ts = _schema_cache.get(object_name, (None, 0.0))
    if cached is not None and (time.time() - ts) < _SCHEMA_TTL:
        return {**cached, "cached": True}

    sf = _connect()

    try:
        sf_object = getattr(sf, object_name)
        describe = sf_object.describe()
    except AttributeError:
        raise ValueError(f"Salesforce object '{object_name}' not found.")
    except Exception as exc:
        raise ValueError(f"Could not describe '{object_name}': {exc}")

    schema = {
        "object": object_name,
        "label": describe.get("label", object_name),
        "queryable": describe.get("queryable", True),
        "fields": {field["name"]: field["type"] for field in describe["fields"]},
        "cached": False,
    }

    _schema_cache[object_name] = (schema, time.time())
    return schema


# ── run_soql ───────────────────────────────────────────────────────────────────

def run_soql(query: str) -> dict[str, Any]:
    """
    Execute a SOQL query and return clean records with SF metadata stripped.

    Uses query_all() which follows pagination cursors automatically,
    so result sets larger than 2000 records are fully retrieved.

    Returns:
        {
          "total_size": 42,
          "records": [{"Id": "...", "Name": "..."}, ...]
        }

    Raises:
        ValueError      if the query is malformed or references invalid fields
        ConnectionError if authentication fails
    """
    sf = _connect()

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
        "records": records,
    }


# ── get_available_objects ──────────────────────────────────────────────────────

def get_available_objects() -> list[str]:
    """
    Return sorted list of all queryable Salesforce object names in this org.

    Result is cached for 1 hour alongside schema cache.

    Raises:
        ConnectionError if authentication fails
    """
    global _objects_cache

    if _objects_cache is not None:
        objects, ts = _objects_cache
        if (time.time() - ts) < _SCHEMA_TTL:
            return objects

    sf = _connect()

    try:
        describe = sf.describe()
    except Exception as exc:
        raise ConnectionError(f"Could not fetch object list: {exc}")

    objects = sorted(
        obj["name"]
        for obj in describe["sobjects"]
        if obj.get("queryable", False)
    )

    _objects_cache = (objects, time.time())
    return objects


# ── Manual test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import time as _time

    print("=" * 60)
    print("Day 4 — cache + get_available_objects() test")
    print("=" * 60)

    # 1. Cache test — call get_schema twice, second must be instant
    print("\n[Cache test — get_schema('Lead')]")
    t0 = _time.perf_counter()
    s1 = get_schema("Lead")
    t1 = _time.perf_counter()
    s2 = get_schema("Lead")
    t2 = _time.perf_counter()

    first_ms  = (t1 - t0) * 1000
    second_ms = (t2 - t1) * 1000

    print(f"  First call  (API):  {first_ms:.0f}ms  cached={s1['cached']}")
    print(f"  Second call (cache): {second_ms:.0f}ms  cached={s2['cached']}")

    cache_ok = s2["cached"] and second_ms < 10
    print(f"  {'✓  Cache working — second call < 10ms' if cache_ok else '✗  Cache not working'}")

    # 2. get_available_objects
    print("\n[get_available_objects()]")
    try:
        t0 = _time.perf_counter()
        objects = get_available_objects()
        elapsed_ms = (_time.perf_counter() - t0) * 1000
        print(f"  ✓  {len(objects)} queryable objects found in {elapsed_ms:.0f}ms")
        print(f"     Sample: {objects[:10]}")
        common = [o for o in ["Lead", "Opportunity", "Account", "Contact", "Case"] if o in objects]
        print(f"     Common objects present: {common}")
    except Exception as exc:
        print(f"  ✗  {exc}")

    # 3. Error handling — invalid object
    print("\n[Error handling — invalid object name]")
    try:
        get_schema("NonExistentObject_xyz")
        print("  ✗  Should have raised ValueError")
    except ValueError as exc:
        print(f"  ✓  ValueError raised cleanly: {exc}")

    # 4. Error handling — bad SOQL
    print("\n[Error handling — bad SOQL]")
    try:
        run_soql("SELECT FakeField FROM Lead LIMIT 1")
        print("  ✗  Should have raised ValueError")
    except ValueError as exc:
        print(f"  ✓  ValueError raised cleanly: {exc}")

    print(f"\n{'=' * 60}")
    print("✓  Day 4 complete — caching and get_available_objects() done.\n")
