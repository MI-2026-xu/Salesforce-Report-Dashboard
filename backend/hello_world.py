"""
Sprint 1 · Day 1 — Salesforce connection smoke test.

Uses OAuth 2.0 Resource Owner Password Credentials flow via a Connected App.
simple_salesforce does not natively support consumer_key+secret for this flow,
so we call the Salesforce token endpoint directly, then hand the session_id
and instance_url to simple_salesforce.

Expected output:
    ✓  Connected to Salesforce
    ✓  Org: <your org name>  |  User: <your username>
    ✓  Lead count: <number>
    ✓  Day 1 complete — commit this and move to Day 2.
"""

import os
import sys
from pathlib import Path

# Load backend/.env regardless of which directory the script is run from
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import requests
from simple_salesforce import Salesforce

REQUIRED_VARS = ["SF_USERNAME", "SF_PASSWORD", "SF_CONSUMER_KEY", "SF_CONSUMER_SECRET", "SF_DOMAIN"]


def check_env() -> None:
    missing = [v for v in REQUIRED_VARS if not os.getenv(v, "").strip()]
    if missing:
        print(f"✗  Missing environment variables: {', '.join(missing)}")
        print("   Make sure backend/.env has all required values filled in.")
        sys.exit(1)


def connect() -> Salesforce:
    domain = os.environ["SF_DOMAIN"]
    base_url = f"https://{domain}.salesforce.com"

    # OAuth 2.0 Resource Owner Password Credentials Grant
    # Combines password + security_token as required by Salesforce
    password_with_token = os.environ["SF_PASSWORD"] + os.environ.get("SF_SECURITY_TOKEN", "")

    resp = requests.post(
        f"{base_url}/services/oauth2/token",
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
        error = resp.json()
        raise RuntimeError(
            f"{error.get('error', 'unknown')}: {error.get('error_description', resp.text)}"
        )

    token_data = resp.json()
    return Salesforce(
        session_id=token_data["access_token"],
        instance_url=token_data["instance_url"],
    )


def main() -> None:
    check_env()

    print("\nConnecting to Salesforce via OAuth 2.0…")

    try:
        sf = connect()
    except RuntimeError as exc:
        print(f"✗  Authentication failed: {exc}")
        print("\n   Common fixes:")
        print("   1. Setup → OAuth and OpenID Connect Settings → enable 'Allow OAuth Username-Password Flows'")
        print("   2. Check SF_CONSUMER_KEY and SF_CONSUMER_SECRET in backend/.env")
        print("   3. Wait 2–10 minutes after creating the Connected App before using it")
        sys.exit(1)
    except Exception as exc:
        print(f"✗  Unexpected error: {exc}")
        sys.exit(1)

    print("✓  Connected to Salesforce")

    identity = sf.restful("chatter/users/me")
    org_name = identity.get("companyName", "—")
    username = identity.get("username", os.environ["SF_USERNAME"])
    print(f"✓  Org: {org_name}  |  User: {username}")

    result = sf.query("SELECT COUNT() FROM Lead  ") 
    lead_count = result["totalSize"]
    print(f"✓  Lead count: {lead_count}")

    print("\n✓  Day 1 complete — commit this and move to Day 2.\n")


if __name__ == "__main__":
    main()
