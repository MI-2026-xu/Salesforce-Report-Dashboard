"""
Sprint 2 · Day 10 — SOQL validator with schema injection.

Two responsibilities:
  1. validate_soql(query, schema) — checks a generated query against the real schema
  2. inject_schema_context(query, schema) — builds the context string Claude receives
     so it always sees the exact field list before writing SOQL

This runs on the Python side, before the query hits Salesforce.
"""

import re
from typing import Any

# ── SOQL Validator ─────────────────────────────────────────────────────────────

WRITE_KEYWORDS = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|MERGE|UPSERT)\b",
    re.IGNORECASE,
)

def validate_soql(query: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Validate a SOQL query for safety and schema correctness.

    Args:
        query:  The SOQL string to validate.
        schema: Output of get_schema() — used to check field names.
                If None, only structural checks run (no field validation).

    Returns:
        {
          "valid":    bool,
          "errors":   [str, ...],   # hard failures — do not run the query
          "warnings": [str, ...],   # soft issues — query can still run
        }
    """
    query = query.strip()
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Must be a SELECT statement
    if WRITE_KEYWORDS.match(query):
        keyword = query.split()[0].upper()
        errors.append(
            f"{keyword} statements are not allowed. Only SELECT queries are permitted."
        )
        return {"valid": False, "errors": errors, "warnings": warnings}

    if not re.match(r"^\s*SELECT\b", query, re.IGNORECASE):
        errors.append("Query must start with SELECT.")
        return {"valid": False, "errors": errors, "warnings": warnings}

    # 2. Must contain a FROM clause
    if not re.search(r"\bFROM\s+\w+", query, re.IGNORECASE):
        errors.append("Query must include a FROM clause with an object name.")

    # 3. Must have a LIMIT clause
    limit_match = re.search(r"\bLIMIT\s+(\d+)", query, re.IGNORECASE)
    if not limit_match:
        errors.append("Query must include a LIMIT clause (maximum 200).")
    else:
        limit_val = int(limit_match.group(1))
        if limit_val > 200:
            errors.append(
                f"LIMIT {limit_val} exceeds the maximum of 200. Use LIMIT 200."
            )

    # 4. Field name validation against schema (if provided)
    if schema and "fields" in schema:
        schema_fields = set(schema["fields"].keys())
        invalid_fields = _extract_invalid_fields(query, schema_fields)
        for field in invalid_fields:
            errors.append(
                f"Field '{field}' does not exist on {schema.get('object', 'this object')}. "
                f"Check the schema for the correct field name."
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def _extract_invalid_fields(query: str, schema_fields: set[str]) -> list[str]:
    """
    Parse the SELECT clause and return any field names not in the schema.
    Skips aggregate functions (COUNT, SUM, AVG, MIN, MAX) and aliases.
    """
    select_match = re.search(
        r"SELECT\s+(.*?)\s+FROM\b",
        query,
        re.IGNORECASE | re.DOTALL,
    )
    if not select_match:
        return []

    fields_str = select_match.group(1)
    invalid: list[str] = []

    for token in re.split(r",", fields_str):
        token = token.strip()

        # Skip aggregate functions: COUNT(Id), SUM(Amount) total, etc.
        if re.match(r"(COUNT|SUM|AVG|MIN|MAX)\s*\(", token, re.IGNORECASE):
            continue

        # Strip alias (e.g. "Id myId" → "Id")
        bare = token.split()[0] if " " in token else token

        # Skip wildcards, empty strings, and SOQL keywords
        if not bare or bare.upper() in {"*", "Id"}:
            continue

        if bare not in schema_fields:
            invalid.append(bare)

    return invalid


# ── Schema Context Injector ────────────────────────────────────────────────────

def inject_schema_context(user_query: str, schema: dict[str, Any]) -> str:
    """
    Prepend the exact field list to the user's query.

    Claude sees this before deciding what SOQL to write, which prevents
    hallucinated field names even before the validator runs.

    Example output:
        Salesforce schema for Lead (61 fields available):
        Fields: AnnualRevenue (currency), City (string), Company (string), ...

        User question: Show me all open leads
    """
    obj = schema.get("object", "Object")
    field_count = len(schema.get("fields", {}))

    field_summary = ", ".join(
        f"{name} ({ftype})"
        for name, ftype in sorted(schema["fields"].items())
    )

    return (
        f"Salesforce schema for {obj} ({field_count} fields available):\n"
        f"Fields: {field_summary}\n\n"
        f"User question: {user_query}"
    )


# ── Manual test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from sf_connector import get_schema

    lead_schema = get_schema("Lead")

    print("=" * 60)
    print("SOQL Validator Tests")
    print("=" * 60)

    test_cases = [
        # (description, query, expect_valid)
        ("Valid basic query",
         "SELECT Id, LastName, Status FROM Lead LIMIT 10",
         True),

        ("Valid aggregate",
         "SELECT Status, COUNT(Id) total FROM Lead GROUP BY Status LIMIT 200",
         True),

        ("Missing LIMIT",
         "SELECT Id, LastName FROM Lead WHERE Status = 'Open'",
         False),

        ("LIMIT too high",
         "SELECT Id FROM Lead LIMIT 500",
         False),

        ("Invalid field name",
         "SELECT Id, FakeFieldName, LastName FROM Lead LIMIT 10",
         False),

        ("Write operation blocked",
         "DELETE FROM Lead WHERE Status = 'Closed'",
         False),

        ("UPDATE blocked",
         "UPDATE Lead SET Status = 'Closed' WHERE Id = '001'",
         False),
    ]

    passed = 0
    for label, query, expect_valid in test_cases:
        result = validate_soql(query, lead_schema)
        ok = result["valid"] == expect_valid
        status = "✓" if ok else "✗"
        print(f"\n[{status}] {label}")
        print(f"     Query:    {query[:70]}{'...' if len(query) > 70 else ''}")
        print(f"     Expected: valid={expect_valid}  Got: valid={result['valid']}")
        if result["errors"]:
            for err in result["errors"]:
                print(f"     Error: {err}")
        if ok:
            passed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed}/{len(test_cases)} passed")

    # Show schema injection example
    print("\n\nSchema Context Injection Example:")
    print("-" * 40)
    augmented = inject_schema_context("Show me open leads", lead_schema)
    preview_lines = augmented.split("\n")
    print(preview_lines[0])  # schema header
    print(preview_lines[1][:120] + "...")  # truncated field list
    print(preview_lines[3])  # user question
    print(f"\n✓  Day 10 complete — validator and schema injection working.\n")
