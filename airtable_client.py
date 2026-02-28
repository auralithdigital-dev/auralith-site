"""
Airtable client for Auralith Prospect Machine.

Handles:
- One-time base creation via Airtable Meta API (--setup flag)
- CRUD operations on the Prospects table

Run once to create the base:
    python airtable_client.py --setup
Then paste the printed Base ID into your .env as AIRTABLE_BASE_ID.
"""

import os
import sys
import argparse
import requests
from datetime import date
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")
TABLE_NAME = "Prospects"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

# ─── Base setup ─────────────────────────────────────────────────────────────────

def setup_base(workspace_id: str = None):
    """
    Creates the 'Auralith Pipeline' Airtable base with all required fields.
    Prints the new Base ID — paste it into .env as AIRTABLE_BASE_ID.

    Requires AIRTABLE_API_KEY to have scopes:
        schema.bases:write, schema.bases:read
    """
    if not API_KEY:
        print("ERROR: AIRTABLE_API_KEY not set in .env")
        sys.exit(1)

    # Step 1: create the base
    payload = {
        "name": "Auralith Pipeline",
        "workspaceId": _get_first_workspace_id(workspace_id),
        "tables": [
            {
                "name": TABLE_NAME,
                "fields": [
                    {"name": "Business Name", "type": "singleLineText"},
                    {"name": "Address",       "type": "singleLineText"},
                    {"name": "Phone",         "type": "phoneNumber"},
                    {"name": "Email",         "type": "email"},
                    {"name": "Website",       "type": "url"},
                    {
                        "name": "County",
                        "type": "singleSelect",
                        "options": {
                            "choices": [
                                {"name": "Broward"},
                                {"name": "Palm Beach"},
                            ]
                        },
                    },
                    {
                        "name": "Status",
                        "type": "singleSelect",
                        "options": {
                            "choices": [
                                {"name": "New"},
                                {"name": "Contacted"},
                                {"name": "Followed Up"},
                                {"name": "Call Scheduled"},
                                {"name": "Closed"},
                                {"name": "Not Interested"},
                            ]
                        },
                    },
                    {"name": "Last Contact Date",  "type": "date",     "options": {"dateFormat": {"name": "iso"}}},
                    {"name": "Notes",              "type": "multilineText"},
                    {"name": "Email 1 Sent",       "type": "checkbox", "options": {"icon": "check", "color": "greenBright"}},
                    {"name": "Email 1 Sent Date",  "type": "date",     "options": {"dateFormat": {"name": "iso"}}},
                    {"name": "Email 2 Sent",       "type": "checkbox", "options": {"icon": "check", "color": "greenBright"}},
                    {"name": "Email 2 Sent Date",  "type": "date",     "options": {"dateFormat": {"name": "iso"}}},
                    {"name": "Call Done",          "type": "checkbox", "options": {"icon": "check", "color": "greenBright"}},
                    {"name": "Reply Received",     "type": "checkbox", "options": {"icon": "check", "color": "greenBright"}},
                    {"name": "Place ID",           "type": "singleLineText"},
                ],
            }
        ],
    }

    resp = requests.post(
        "https://api.airtable.com/v0/meta/bases",
        headers=HEADERS,
        json=payload,
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"ERROR creating base: {resp.status_code} — {resp.text}")
        sys.exit(1)

    base_id = resp.json()["id"]
    print(f"\n✓ Base created successfully!")
    print(f"\nPaste this into your .env file:")
    print(f"  AIRTABLE_BASE_ID={base_id}\n")
    return base_id


def _get_first_workspace_id(workspace_id: str = None):
    """Returns the workspace ID, from argument, env var, or by prompting."""
    # 1. Passed directly as argument
    if workspace_id:
        return workspace_id

    # 2. Stored in .env
    wid = os.getenv("AIRTABLE_WORKSPACE_ID", "").strip()
    if wid:
        return wid

    # 3. Interactive fallback
    print("\nTo create the base, we need your Airtable Workspace ID.")
    print("\nHow to find it:")
    print("  1. Go to airtable.com in your browser")
    print("  2. Click on your workspace name in the left sidebar")
    print("  3. Look at the browser URL — it will look like:")
    print("     https://airtable.com/wsp1234abcd5678/...")
    print("  4. Copy the part that starts with 'wsp'")
    print("\nOr re-run with:  python3 airtable_client.py --setup --workspace-id wspXXXXXX")
    try:
        wid = input("\nWorkspace ID: ").strip()
    except EOFError:
        print("\nERROR: Run this script directly in your terminal (not via another tool).")
        sys.exit(1)
    if not wid:
        print("ERROR: Workspace ID is required.")
        sys.exit(1)
    return wid


# ─── CRUD helpers ───────────────────────────────────────────────────────────────

def _base_url():
    if not BASE_ID:
        raise RuntimeError(
            "AIRTABLE_BASE_ID not set. Run: python airtable_client.py --setup"
        )
    return f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"


def get_all_records(filter_formula=None):
    """
    Returns all records from the Prospects table.
    Handles pagination automatically.
    Optional Airtable formula string for server-side filtering.
    """
    records = []
    params = {"pageSize": 100}
    if filter_formula:
        params["filterByFormula"] = filter_formula

    while True:
        resp = requests.get(_base_url(), headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        params["offset"] = offset

    return records


def get_existing_place_ids():
    """Returns a set of all Place IDs already in Airtable (for deduplication)."""
    records = get_all_records()
    ids = set()
    for r in records:
        pid = r.get("fields", {}).get("Place ID")
        if pid:
            ids.add(pid)
    return ids


def add_record(fields: dict) -> str:
    """Creates a new prospect record. Returns the new record ID."""
    payload = {"fields": fields}
    resp = requests.post(_base_url(), headers=HEADERS, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()["id"]


def update_record(record_id: str, fields: dict):
    """Patches an existing record by ID."""
    url = f"{_base_url()}/{record_id}"
    payload = {"fields": fields}
    resp = requests.patch(url, headers=HEADERS, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_records_needing_email1_queued():
    """
    New prospects with an email address that haven't had Email 1 queued yet.
    (Email 1 Status is blank — not yet written.)
    """
    formula = (
        "AND("
        "{Status}='New', "
        "{Email 1 Sent}=FALSE(), "
        "{Email 1 Status}='', "
        "{Email}!=''"
        ")"
    )
    return get_all_records(filter_formula=formula)


def get_approved_email1_records():
    """Records where Email 1 has been approved and is ready to send."""
    formula = "AND({Email 1 Status}='Approved', {Email 1 Sent}=FALSE())"
    return get_all_records(filter_formula=formula)


def get_approved_email2_records():
    """Records where Email 2 has been approved and is ready to send."""
    formula = "AND({Email 2 Status}='Approved', {Email 2 Sent}=FALSE())"
    return get_all_records(filter_formula=formula)


def get_sendable_email2_records(cutoff_date: str):
    """
    Records where Email 2 is approved AND safe to send:
      - Email 1 was sent (Email 1 Sent = TRUE)
      - Email 1 Sent Date is before cutoff_date (i.e. 3+ days ago)
      - No reply received
      - Email 2 approved but not yet sent

    cutoff_date: ISO date string, e.g. date 3 days before today.
    """
    formula = (
        f"AND("
        f"{{Email 1 Sent}}=TRUE(), "
        f"IS_BEFORE({{Email 1 Sent Date}}, '{cutoff_date}'), "
        f"{{Reply Received}}=FALSE(), "
        f"{{Email 2 Status}}='Approved', "
        f"{{Email 2 Sent}}=FALSE()"
        f")"
    )
    return get_all_records(filter_formula=formula)


def get_records_needing_followup_queued(cutoff_date: str):
    """
    Records where Email 1 was sent 3+ days ago, no reply, and
    Email 2 hasn't been queued yet.
    """
    formula = (
        f"AND("
        f"{{Email 1 Sent}}=TRUE(), "
        f"{{Email 2 Sent}}=FALSE(), "
        f"{{Email 2 Status}}='', "
        f"{{Reply Received}}=FALSE(), "
        f"{{Email}}!='', "
        f"IS_BEFORE({{Email 1 Sent Date}}, '{cutoff_date}')"
        f")"
    )
    return get_all_records(filter_formula=formula)


def get_records_needing_dm_prep(cutoff_date: str):
    """
    Records where Email 1 was sent 3+ days ago, no reply,
    and DM hasn't been prepped yet.
    """
    formula = (
        f"AND("
        f"{{Email 1 Sent}}=TRUE(), "
        f"{{Reply Received}}=FALSE(), "
        f"{{DM Status}}='', "
        f"IS_BEFORE({{Email 1 Sent Date}}, '{cutoff_date}')"
        f")"
    )
    return get_all_records(filter_formula=formula)


def get_records_needing_call_prep(cutoff_date: str):
    """
    Records where DM Date is 5+ days ago, no reply,
    call script not yet generated.
    """
    formula = (
        f"AND("
        f"{{DM Status}}='DM Ready', "
        f"{{Call Done}}=FALSE(), "
        f"{{Reply Received}}=FALSE(), "
        f"{{Status}}!='Call Ready', "
        f"{{Call Script}}='', "
        f"IS_BEFORE({{DM Date}}, '{cutoff_date}')"
        f")"
    )
    return get_all_records(filter_formula=formula)


def get_all_prospect_emails():
    """Returns a dict mapping email → record_id for all prospects with emails."""
    records = get_all_records()
    return {
        r["fields"]["Email"]: r["id"]
        for r in records
        if r.get("fields", {}).get("Email")
    }


def get_todays_summary_data():
    """Returns counts and lists needed for the daily summary email."""
    today = date.today().isoformat()
    all_records = get_all_records()

    new_today = [
        r for r in all_records
        if r["fields"].get("Email 1 Sent Date") == today
    ]
    followup_today = [
        r for r in all_records
        if r["fields"].get("Email 2 Sent Date") == today
    ]
    needs_call = [
        r for r in all_records
        if r["fields"].get("Status") in ("Call Scheduled", "Call Ready")
        and not r["fields"].get("Call Done", False)
    ]
    replied = [
        r for r in all_records
        if r["fields"].get("Reply Received", False)
    ]

    pending_review = [
        r for r in all_records
        if r["fields"].get("Email 1 Status") == "Pending Review"
        or r["fields"].get("Email 2 Status") == "Pending Review"
    ]
    dm_ready = [
        r for r in all_records
        if r["fields"].get("DM Status") == "DM Ready"
    ]

    return {
        "new_today": new_today,
        "followup_today": followup_today,
        "needs_call": needs_call,
        "replied": replied,
        "pending_review": pending_review,
        "dm_ready": dm_ready,
        "total_prospects": len(all_records),
    }


# ─── CLI entrypoint ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Airtable setup utility")
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Create the Auralith Pipeline base and print the Base ID",
    )
    parser.add_argument(
        "--workspace-id",
        metavar="WSP_ID",
        help="Your Airtable Workspace ID (starts with 'wsp'). Find it in the Airtable URL.",
    )
    args = parser.parse_args()

    if args.setup:
        setup_base(workspace_id=args.workspace_id)
    else:
        parser.print_help()
