"""
Layer 3 — Claude AI agent.

Receives a plain-English query, runs the agentic tool-use loop with Claude,
dispatches tool calls to sf_connector, and returns a structured response.

Days 8–11 complete:
  Day 8  — core agentic loop + tool dispatcher
  Day 9  — intent parser + full system prompt
  Day 10 — schema injection before first message
  Day 11 — SOQL validator + max-2 retry logic   ← current
"""

import json
import os
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

from prompts import SYSTEM_PROMPT, validate_intent
from sf_connector import get_available_objects, get_schema, run_soql
from synthesizer import synthesize
from tools import TOOLS
from validator import inject_schema_context, validate_soql

load_dotenv(Path(__file__).parent / ".env")

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
MAX_TOOL_ROUNDS = 10   # hard ceiling on total Claude ↔ tool round-trips
MAX_SOQL_RETRIES = 2   # how many times Claude gets to fix a bad SOQL query


# ── Tool dispatcher ────────────────────────────────────────────────────────────

def _dispatch(tool_name: str, tool_input: dict, soql_retry_count: list[int]) -> Any:
    """
    Route a Claude tool call to the correct sf_connector function.

    soql_retry_count is a mutable 1-element list used as a shared counter
    so the caller can track retries without global state.
    """
    if tool_name == "get_available_objects":
        return get_available_objects()

    if tool_name == "get_schema":
        return get_schema(tool_input["object_name"])

    if tool_name == "run_soql":
        query = tool_input["query"]
        validation = validate_soql(query)

        if not validation["valid"]:
            soql_retry_count[0] += 1

            if soql_retry_count[0] > MAX_SOQL_RETRIES:
                return {
                    "error": "max_retries_exceeded",
                    "message": (
                        "This query has failed validation twice. "
                        "Please tell the user you were unable to generate a valid query "
                        "and explain the issue."
                    ),
                    "last_errors": validation["errors"],
                }

            # Return error with correction instruction so Claude self-corrects
            return {
                "error": "invalid_soql",
                "attempt": soql_retry_count[0],
                "remaining_retries": MAX_SOQL_RETRIES - soql_retry_count[0],
                "errors": validation["errors"],
                "instruction": (
                    "Your SOQL query failed validation. Fix ALL the errors listed above "
                    "and call run_soql() again with the corrected query. "
                    "Do not explain the error to the user — just fix and retry."
                ),
            }

        # Validation passed — hit Salesforce
        soql_retry_count[0] = 0  # reset counter on success
        return run_soql(query)

    raise ValueError(f"Unknown tool: {tool_name}")


# ── Agent loop ─────────────────────────────────────────────────────────────────

def run_agent(user_query: str, conversation_history: list | None = None) -> dict[str, Any]:
    """
    Run the Claude agentic loop for a single user query.

    Args:
        user_query:           Plain-English question about Salesforce data.
        conversation_history: Optional prior messages for multi-turn context.

    Returns:
        {
          "response":   str,
          "tool_calls": list,
          "soql":       str | None   — last successful SOQL query (for debug panel),
          "error":      str | None,
        }
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # ── Schema injection ───────────────────────────────────────────────────────
    # If intent is clear, pre-fetch schema and inject the exact field list so
    # Claude never hallucinates field names.
    intent = validate_intent(user_query)
    if intent["valid"] and intent["object"]:
        try:
            schema = get_schema(intent["object"])
            first_message = inject_schema_context(user_query, schema)
        except Exception:
            first_message = user_query
    else:
        first_message = user_query

    messages: list[dict] = list(conversation_history or [])
    messages.append({"role": "user", "content": first_message})

    tool_call_log: list[dict] = []
    soql_retry_count = [0]   # mutable counter passed into _dispatch
    last_soql: str | None = None
    last_records: list[dict] = []
    last_total_size: int = 0

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        # ── End turn ───────────────────────────────────────────────────────
        if response.stop_reason == "end_turn":
            final_text = " ".join(
                block.text for block in response.content
                if hasattr(block, "text")
            ).strip()
            return synthesize(
                records=last_records,
                total_size=last_total_size,
                user_query=user_query,
                claude_text=final_text,
                soql=last_soql,
            ) | {"tool_calls": tool_call_log, "error": None}

        # ── Tool use ───────────────────────────────────────────────────────
        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_log = {"tool": block.name, "input": block.input}

                try:
                    result = _dispatch(block.name, block.input, soql_retry_count)
                    tool_log["status"] = "ok"

                    # Capture records + SOQL for synthesizer
                    if block.name == "run_soql" and isinstance(result, dict) and "records" in result:
                        last_soql = block.input.get("query")
                        last_records = result["records"]
                        last_total_size = result["total_size"]

                except Exception as exc:
                    result = {"error": str(exc)}
                    tool_log["status"] = "error"

                # Summarise result for the log
                if isinstance(result, list):
                    tool_log["result_summary"] = f"{len(result)} objects"
                elif isinstance(result, dict) and "records" in result:
                    tool_log["result_summary"] = f"{result['total_size']} records"
                elif isinstance(result, dict) and "fields" in result:
                    tool_log["result_summary"] = "schema fetched"
                elif isinstance(result, dict) and result.get("error") == "invalid_soql":
                    tool_log["result_summary"] = (
                        f"validation failed (attempt {result['attempt']}, "
                        f"{result['remaining_retries']} retries left)"
                    )
                    tool_log["status"] = "retry"
                else:
                    tool_log["result_summary"] = str(result)[:120]

                tool_call_log.append(tool_log)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                })

            messages.append({"role": "user", "content": tool_results})
            continue

        break  # unexpected stop reason

    return {
        "response": "Agent reached the maximum number of steps without completing.",
        "tool_calls": tool_call_log,
        "soql": last_soql,
        "error": "max_rounds_exceeded",
    }


# ── Manual test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_queries = [
        "How many leads do we have in total?",
        "Show me the top 5 leads by name",
    ]

    for query in test_queries:
        print(f"\n{'=' * 60}")
        print(f"Query: {query}")
        print("=" * 60)

        result = run_agent(query)

        print("\nTool calls made:")
        for i, call in enumerate(result["tool_calls"], 1):
            status = call.get("status", "")
            print(f"  {i}. [{status}] {call['tool']}() → {call['result_summary']}")

        if result.get("soql"):
            print(f"\nSOQL executed: {result['soql']}")

        print(f"\nAgent's response:\n  {result['response']}")

        if result["error"]:
            print(f"\n  ✗ Error: {result['error']}")
        else:
            print(f"\n  ✓ Done in {len(result['tool_calls'])} tool call(s)")
