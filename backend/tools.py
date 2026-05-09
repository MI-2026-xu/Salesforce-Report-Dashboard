"""
Claude tool definitions for the Salesforce agent.

This module contains ONLY the JSON schema definitions that are passed to the
Anthropic API. No business logic lives here — all implementation is in
sf_connector.py. Claude reads these schemas to decide which tool to call,
in what order, and with what arguments.
"""

TOOLS: list[dict] = [
    {
        "name": "get_available_objects",
        "description": (
            "Returns a sorted list of all queryable Salesforce object names in this org "
            "(e.g. 'Lead', 'Opportunity', 'Account', 'Contact', 'Case'). "
            "Call this FIRST when the user's request is ambiguous about which Salesforce "
            "object to query, or when you need to confirm that an object exists before "
            "fetching its schema. Results are cached — repeated calls are instant."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_schema",
        "description": (
            "Returns the complete field schema for a single Salesforce object. "
            "Always call this before generating a SOQL query so you only use field "
            "names that actually exist in this org. "
            "The response includes a 'fields' dict mapping every field name to its "
            "data type (string, boolean, reference, picklist, currency, date, datetime, etc.). "
            "Results are cached for 1 hour — safe to call multiple times."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {
                    "type": "string",
                    "description": (
                        "The API name of the Salesforce object to describe. "
                        "Use exact casing (e.g. 'Lead', 'Opportunity', 'Account'). "
                        "Custom objects end in '__c' (e.g. 'MyObject__c')."
                    ),
                }
            },
            "required": ["object_name"],
        },
    },
    {
        "name": "run_soql",
        "description": (
            "Executes a SOQL query against Salesforce and returns matching records. "
            "Pagination is handled automatically — all records are returned regardless "
            "of result set size. "
            "\n\nMANDATORY rules you must follow when writing the query:\n"
            "- Only SELECT statements are allowed. Never use INSERT, UPDATE, DELETE, MERGE, or UPSERT.\n"
            "- Always include a LIMIT clause. Maximum allowed value is 200.\n"
            "- Only use field names that were returned by get_schema() for this object.\n"
            "- For date filters use SOQL date literals: TODAY, THIS_WEEK, THIS_MONTH, "
            "THIS_QUARTER, THIS_YEAR, LAST_N_DAYS:n, LAST_N_MONTHS:n.\n"
            "- For aggregate queries (COUNT, SUM, AVG) you must include a GROUP BY clause "
            "when selecting non-aggregate fields.\n"
            "\nThe response contains 'total_size' (int) and 'records' (list of dicts). "
            "Each record dict contains only the fields you selected — Salesforce metadata is stripped."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "A valid SOQL SELECT statement. "
                        "Example: \"SELECT Id, LastName, Status FROM Lead WHERE Status = 'Open - Not Contacted' LIMIT 50\""
                    ),
                }
            },
            "required": ["query"],
        },
    },
]


if __name__ == "__main__":
    import json

    print(f"Loaded {len(TOOLS)} tool definitions:\n")
    for tool in TOOLS:
        props = tool["input_schema"].get("properties", {})
        required = tool["input_schema"].get("required", [])
        print(f"  {tool['name']}")
        print(f"    Parameters : {list(props.keys()) or 'none'}")
        print(f"    Required   : {required or 'none'}")
        print()

    print("Full JSON schema (copy this to verify it's valid):")
    print(json.dumps(TOOLS, indent=2))
