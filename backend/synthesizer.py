"""
Sprint 2 · Day 12 — Response synthesizer.

Takes raw SOQL results and produces the structured payload the frontend
needs: summary, rows, total_size, chart_type, insight, soql.

All logic is Python-side — no extra LLM call needed.
chartType is determined by the shape of the data, not by guessing.
"""

import re
from typing import Any

# Field names that indicate a COUNT/SUM aggregate result
_AGGREGATE_FIELD_NAMES = {"total", "count", "cnt", "num", "n", "sum", "avg", "average", "max", "min"}


# ── Chart type detection ───────────────────────────────────────────────────────

def _detect_chart_type(records: list[dict]) -> str:
    """
    Decide the best visualization based on data shape.

    Rules (in order of precedence):
      1. Empty or single record           → table
      2. Exactly 2 fields: 1 string + 1 number
           ≤ 6 distinct categories        → pie
           > 6 distinct categories        → bar
      3. More than 2 fields               → table
    """
    if not records or len(records) == 1:
        return "table"

    fields = list(records[0].keys())

    if len(fields) != 2:
        return "table"

    # Classify the two fields
    str_fields  = [f for f in fields if isinstance(records[0][f], str)]
    num_fields  = [f for f in fields if isinstance(records[0][f], (int, float))]

    if len(str_fields) == 1 and len(num_fields) == 1:
        # Looks like a GROUP BY aggregate — bar or pie
        return "pie" if len(records) <= 6 else "bar"

    return "table"


# ── Insight generator ──────────────────────────────────────────────────────────

def _generate_insight(records: list[dict], chart_type: str) -> str | None:
    """
    Generate a one-line business insight from the data.
    Returns None if no meaningful insight can be derived.
    """
    if not records:
        return None

    fields = list(records[0].keys())

    # Aggregate result (2 fields: category + count/sum)
    if len(fields) == 2 and chart_type in ("bar", "pie"):
        str_field = next((f for f in fields if isinstance(records[0][f], str)), None)
        num_field = next((f for f in fields if isinstance(records[0][f], (int, float))), None)

        if str_field and num_field:
            sorted_records = sorted(records, key=lambda r: r[num_field] or 0, reverse=True)
            top = sorted_records[0]
            total = sum(r[num_field] or 0 for r in records)
            pct = round((top[num_field] / total) * 100) if total else 0
            return (
                f"{top[str_field]} is the top category at "
                f"{top[num_field]:,} ({pct}% of total)."
            )

    # Amount field present → show range
    if "Amount" in records[0]:
        amounts = [r["Amount"] for r in records if r.get("Amount") is not None]
        if amounts:
            return (
                f"Deal amounts range from "
                f"${min(amounts):,.0f} to ${max(amounts):,.0f}."
            )

    return None


# ── Summary generator ──────────────────────────────────────────────────────────

def _generate_summary(
    records: list[dict],
    total_size: int,
    user_query: str,
    claude_text: str,
    soql: str | None = None,
) -> str:
    """
    Build a one-sentence summary.
    Prefers Claude's text if it's short; falls back to a generated sentence.
    Handles aggregate single-row results naturally (e.g. COUNT → "You have 122 leads total.").
    """
    if not records:
        return "No records found matching your query."

    # ── Aggregate single-row detection ────────────────────────────────────────
    # e.g. SELECT COUNT(Id) total FROM Lead → [{total: 122}]
    # Give a natural "You have N X total." sentence instead of "Found 1 record."
    if len(records) == 1:
        fields = list(records[0].keys())
        agg_fields = [f for f in fields if f.lower() in _AGGREGATE_FIELD_NAMES]
        if agg_fields and len(fields) <= 2:
            val = records[0][agg_fields[0]]
            if isinstance(val, (int, float)):
                # Try to extract object name from SOQL for natural phrasing
                obj_label = ""
                if soql:
                    m = re.search(r"\bFROM\s+(\w+)", soql, re.IGNORECASE)
                    if m:
                        obj_label = f" {m.group(1).lower()}s"
                # Currency / sum values
                if agg_fields[0].lower() in {"sum", "total"} and val > 1000:
                    return f"Total{obj_label}: ${val:,.0f}."
                return f"You have {int(val):,}{obj_label} in total."

    # ── Claude's text is concise (≤ 2 sentences) — use it directly ───────────
    sentences = [s.strip() for s in claude_text.split(".") if s.strip()]
    if 1 <= len(sentences) <= 2:
        return claude_text.strip()

    # ── Fallback: record count sentence ──────────────────────────────────────
    count_str = f"{total_size:,}" if total_size > len(records) else str(len(records))
    return f"Found {count_str} record{'s' if total_size != 1 else ''}."


# ── Public API ─────────────────────────────────────────────────────────────────

def synthesize(
    records: list[dict],
    total_size: int,
    user_query: str,
    claude_text: str,
    soql: str | None = None,
) -> dict[str, Any]:
    """
    Build the complete structured response payload.

    Returns:
        {
          "summary":    str,
          "rows":       list[dict],
          "total_size": int,
          "row_count":  int,
          "chart_type": "table" | "bar" | "pie",
          "insight":    str | None,
          "soql":       str | None,
          "response":   str   — Claude's full text (kept for display)
        }
    """
    chart_type = _detect_chart_type(records)
    insight    = _generate_insight(records, chart_type)
    summary    = _generate_summary(records, total_size, user_query, claude_text, soql)

    return {
        "summary":    summary,
        "rows":       records,
        "total_size": total_size,
        "row_count":  len(records),
        "chart_type": chart_type,
        "insight":    insight,
        "soql":       soql,
        "response":   claude_text,
    }


# ── Manual test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    test_cases = [
        {
            "label": "Empty result",
            "records": [],
            "total_size": 0,
            "query": "Show me leads from Mars",
            "claude_text": "",
            "expect_chart": "table",
        },
        {
            "label": "Flat list (many fields)",
            "records": [
                {"Id": "001", "LastName": "Boxer", "Status": "Open", "LeadSource": "Web"},
                {"Id": "002", "LastName": "Bair",  "Status": "Working", "LeadSource": "Email"},
            ],
            "total_size": 50,
            "query": "Show me open leads",
            "claude_text": "Found 50 open leads in your org.",
            "expect_chart": "table",
        },
        {
            "label": "Aggregate ≤ 6 groups → pie",
            "records": [
                {"Status": "Open",    "total": 32},
                {"Status": "Working", "total": 40},
                {"Status": "Closed",  "total":  5},
            ],
            "total_size": 3,
            "query": "Lead count by status",
            "claude_text": "Here is the lead breakdown by status.",
            "expect_chart": "pie",
        },
        {
            "label": "Aggregate > 6 groups → bar",
            "records": [
                {"LeadSource": s, "total": i * 10}
                for i, s in enumerate(
                    ["Web", "Email", "LinkedIn", "Phone", "Partner", "Other", "Cold Call"],
                    1,
                )
            ],
            "total_size": 7,
            "query": "Leads by source",
            "claude_text": "Lead distribution across all sources.",
            "expect_chart": "bar",
        },
        {
            "label": "Opportunity with Amount → insight",
            "records": [
                {"Id": "1", "Name": "Deal A", "Amount": 50000.0,  "StageName": "Closed Won"},
                {"Id": "2", "Name": "Deal B", "Amount": 120000.0, "StageName": "Negotiation"},
                {"Id": "3", "Name": "Deal C", "Amount": 15000.0,  "StageName": "Proposal"},
            ],
            "total_size": 3,
            "query": "Show opportunities with amounts",
            "claude_text": "Here are your opportunities.",
            "expect_chart": "table",
        },
    ]

    print("=" * 60)
    print("Synthesizer Tests")
    print("=" * 60)

    passed = 0
    for tc in test_cases:
        result = synthesize(
            records=tc["records"],
            total_size=tc["total_size"],
            user_query=tc["query"],
            claude_text=tc["claude_text"],
            soql=f"SELECT ... FROM Lead LIMIT 100",
        )
        ok = result["chart_type"] == tc["expect_chart"]
        icon = "✓" if ok else "✗"
        print(f"\n[{icon}] {tc['label']}")
        print(f"     chart_type : {result['chart_type']}  (expected {tc['expect_chart']})")
        print(f"     summary    : {result['summary']}")
        print(f"     row_count  : {result['row_count']}")
        if result["insight"]:
            print(f"     insight    : {result['insight']}")
        if ok:
            passed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed}/{len(test_cases)} passed")
    if passed == len(test_cases):
        print("✓  Day 12 complete — synthesizer working.\n")
