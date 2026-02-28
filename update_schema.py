"""
Adds new fields to the existing Auralith Pipeline Airtable table.

Run once after updating the system:
    python3 update_schema.py
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

NEW_FIELDS = [
    # ── Email review queue ──────────────────────────────────────────────────────
    {"name": "Email 1 Subject", "type": "singleLineText"},
    {"name": "Email 1 Body",    "type": "multilineText"},
    {
        "name": "Email 1 Status",
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "Pending Review", "color": "yellowLight2"},
                {"name": "Approved",       "color": "blueLight2"},
                {"name": "Sent",           "color": "greenLight2"},
                {"name": "Rejected",       "color": "redLight2"},
            ]
        },
    },
    {"name": "Email 2 Subject", "type": "singleLineText"},
    {"name": "Email 2 Body",    "type": "multilineText"},
    {
        "name": "Email 2 Status",
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "Pending Review", "color": "yellowLight2"},
                {"name": "Approved",       "color": "blueLight2"},
                {"name": "Sent",           "color": "greenLight2"},
                {"name": "Rejected",       "color": "redLight2"},
            ]
        },
    },
    # ── Instagram DM prep ───────────────────────────────────────────────────────
    {"name": "Instagram Handle", "type": "singleLineText"},
    {"name": "DM Text",          "type": "multilineText"},
    {
        "name": "DM Status",
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "DM Ready", "color": "purpleLight2"},
                {"name": "DM Sent",  "color": "greenLight2"},
            ]
        },
    },
    {"name": "DM Date", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
    # ── Call ready ──────────────────────────────────────────────────────────────
    {"name": "Call Script", "type": "multilineText"},
    # ── Audit page ──────────────────────────────────────────────────────────────
    {"name": "Audit Notes",    "type": "multilineText"},
    {"name": "Audit Page URL", "type": "url"},
    # ── Contact info + email copy ────────────────────────────────────────────────
    {"name": "Contact Name",       "type": "singleLineText"},
    {"name": "Subject Line Options", "type": "singleLineText"},
]


def get_table_id():
    """Fetches the table ID for the Prospects table in the base."""
    resp = requests.get(
        f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables",
        headers=HEADERS,
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"ERROR fetching tables: {resp.status_code} — {resp.text}")
        sys.exit(1)

    tables = resp.json().get("tables", [])
    for t in tables:
        if t["name"] == "Prospects":
            return t["id"]

    print("ERROR: 'Prospects' table not found. Did you run airtable_client.py --setup?")
    sys.exit(1)


def get_existing_field_names(table_id):
    """Returns a set of field names already in the table."""
    resp = requests.get(
        f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables",
        headers=HEADERS,
        timeout=10,
    )
    tables = resp.json().get("tables", [])
    for t in tables:
        if t["id"] == table_id:
            return {f["name"] for f in t.get("fields", [])}
    return set()


def add_field(table_id, field_def):
    """Adds a single field to the table. Skips if it already exists."""
    resp = requests.post(
        f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables/{table_id}/fields",
        headers=HEADERS,
        json=field_def,
        timeout=10,
    )
    return resp.status_code in (200, 201)


def run():
    if not API_KEY or not BASE_ID:
        print("ERROR: AIRTABLE_API_KEY or AIRTABLE_BASE_ID not set in .env")
        sys.exit(1)

    print("Fetching table info...")
    table_id = get_table_id()
    existing = get_existing_field_names(table_id)
    print(f"Found table ID: {table_id}")
    print(f"Existing fields: {len(existing)}\n")

    added = 0
    skipped = 0
    for field in NEW_FIELDS:
        name = field["name"]
        if name in existing:
            print(f"  SKIP  {name} (already exists)")
            skipped += 1
        else:
            ok = add_field(table_id, field)
            if ok:
                print(f"  ✓ ADD  {name}")
                added += 1
            else:
                print(f"  ✗ FAIL {name}")

    print(f"\nDone — {added} added, {skipped} skipped.")


if __name__ == "__main__":
    run()
