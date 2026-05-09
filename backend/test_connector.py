"""
Sprint 1 · Day 6 — Layer 4 acceptance tests.

10 test cases that must all pass before moving to Sprint 2:
  [1]  get_schema — Lead
  [2]  get_schema — Opportunity
  [3]  get_schema — Account
  [4]  run_soql  — basic fetch with LIMIT
  [5]  run_soql  — WHERE filter
  [6]  run_soql  — date literal (THIS_YEAR)
  [7]  run_soql  — multi-object complexity (Opportunity with Amount)
  [8]  run_soql  — aggregate GROUP BY
  [9]  error case — invalid object name raises ValueError
  [10] cache hit  — second get_schema call returns cached=True instantly

Run:
    venv/Scripts/python.exe -m pytest test_connector.py -v
"""

import time
import pytest
from sf_connector import get_schema, get_available_objects, run_soql


# ── Helpers ───────────────────────────────────────────────────────────────────

def assert_schema(schema: dict, object_name: str) -> None:
    assert schema["object"] == object_name
    assert isinstance(schema["label"], str) and schema["label"]
    assert schema["queryable"] is True
    assert "Id" in schema["fields"], "Every SF object must have an Id field"
    assert len(schema["fields"]) > 5, "Schema should have more than 5 fields"


def assert_soql_result(result: dict) -> None:
    assert "total_size" in result
    assert "records" in result
    assert isinstance(result["records"], list)
    assert isinstance(result["total_size"], int)
    for record in result["records"]:
        assert "attributes" not in record, "SF metadata must be stripped from records"


# ── [1] Schema — Lead ─────────────────────────────────────────────────────────

def test_schema_lead():
    schema = get_schema("Lead")
    assert_schema(schema, "Lead")
    # Lead-specific fields that must exist
    for field in ("LastName", "FirstName", "Status", "LeadSource", "Email"):
        assert field in schema["fields"], f"Expected '{field}' in Lead schema"


# ── [2] Schema — Opportunity ──────────────────────────────────────────────────

def test_schema_opportunity():
    schema = get_schema("Opportunity")
    assert_schema(schema, "Opportunity")
    for field in ("Name", "StageName", "CloseDate", "Amount"):
        assert field in schema["fields"], f"Expected '{field}' in Opportunity schema"


# ── [3] Schema — Account ──────────────────────────────────────────────────────

def test_schema_account():
    schema = get_schema("Account")
    assert_schema(schema, "Account")
    for field in ("Name", "Type", "Industry", "BillingCity"):
        assert field in schema["fields"], f"Expected '{field}' in Account schema"


# ── [4] SOQL — basic fetch with LIMIT ────────────────────────────────────────

def test_soql_basic_fetch():
    result = run_soql("SELECT Id, LastName, FirstName FROM Lead LIMIT 5")
    assert_soql_result(result)
    assert result["total_size"] >= 0
    for record in result["records"]:
        assert "Id" in record
        assert "LastName" in record


# ── [5] SOQL — WHERE filter ───────────────────────────────────────────────────

def test_soql_where_filter():
    result = run_soql(
        "SELECT Id, LastName, Status FROM Lead "
        "WHERE IsDeleted = false LIMIT 10"
    )
    assert_soql_result(result)
    # Every record must satisfy the filter
    for record in result["records"]:
        assert record.get("Status") is not None


# ── [6] SOQL — date literal ───────────────────────────────────────────────────

def test_soql_date_literal():
    result = run_soql(
        "SELECT Id, LastName, CreatedDate FROM Lead "
        "WHERE CreatedDate = THIS_YEAR LIMIT 10"
    )
    assert_soql_result(result)
    # All returned records must have a CreatedDate
    for record in result["records"]:
        assert "CreatedDate" in record


# ── [7] SOQL — Opportunity with multiple fields ───────────────────────────────

def test_soql_opportunity_multi_field():
    result = run_soql(
        "SELECT Id, Name, StageName, Amount, CloseDate "
        "FROM Opportunity LIMIT 10"
    )
    assert_soql_result(result)
    for record in result["records"]:
        assert "StageName" in record
        assert "CloseDate" in record


# ── [8] SOQL — aggregate GROUP BY ────────────────────────────────────────────

def test_soql_aggregate():
    result = run_soql(
        "SELECT Status, COUNT(Id) total FROM Lead GROUP BY Status LIMIT 10"
    )
    assert_soql_result(result)
    # Each group must have a Status and a total count
    for record in result["records"]:
        assert "Status" in record
        assert "total" in record
        assert isinstance(record["total"], int)


# ── [9] Error case — invalid object ──────────────────────────────────────────

def test_error_invalid_object():
    with pytest.raises(ValueError) as exc_info:
        get_schema("ThisObjectDoesNotExist_xyz")
    assert "not found" in str(exc_info.value).lower() or "not exist" in str(exc_info.value).lower()


# ── [10] Cache hit ────────────────────────────────────────────────────────────

def test_schema_cache_hit():
    # Warm the cache
    get_schema("Contact")

    # Second call must be a cache hit and near-instant
    t0 = time.perf_counter()
    schema = get_schema("Contact")
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert schema["cached"] is True, "Second call must be served from cache"
    assert elapsed_ms < 10, f"Cached call took {elapsed_ms:.1f}ms — expected < 10ms"
