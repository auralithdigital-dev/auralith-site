"""
One-time script: regenerate Email 1 Body, Email 2 Body, Subject Line Options,
DM Text, and Call Script for ALL 20 Airtable records using the current
templates in email_writer.py.

- Uses stored Contact Name (no new Claude API calls)
- Resets Email 1 Status and Email 2 Status to "Pending Review"
- Overwrites every record unconditionally

Run:
    python3 regenerate_all.py
    python3 regenerate_all.py --dry-run   # preview without writing to Airtable
"""

import sys
import os
import argparse

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

import airtable_client as at
from email_writer import (
    _build_subject_options,
    _parse_findings_for_call,
    write_followup_email,
    write_dm,
    write_call_script,
)


REGENERATE_STATUSES = {"Pending Review", "Do Not Send"}

def build_email1_body(business_name, owner_name, audit_notes, audit_page_url):
    """Assembles Email 1 body exactly as write_cold_email() does, using stored owner_name."""
    options = _build_subject_options(business_name)
    phrases = _parse_findings_for_call(audit_notes)
    url = audit_page_url if audit_page_url and audit_page_url.startswith("http") else "[AUDIT PAGE URL]"

    lines = []
    if owner_name:
        lines.append(owner_name + ",")
    lines.append(
        f"I was looking up grooming salons in the area. I actually bring my own dog to one around here and came across {business_name}."
    )
    if phrases:
        f1 = phrases[0]
        f2 = phrases[1] if len(phrases) > 1 else None
        if f2:
            finding_line = f"I got curious and took a look at your site. I noticed {f1} and {f2}. Small things, but that's usually where bookings slip through."
        else:
            finding_line = f"I got curious and took a look at your site. I noticed {f1}. Small things, but that's usually where bookings slip through."
        lines.append(finding_line)
    lines.append(f"I put together a quick breakdown: {url}")
    lines.append(
        "Free, takes 2 minutes. If it's useful there's a button at the bottom to get on a call with me."
    )
    lines.append("Pyetra")

    return "\n".join(lines), options


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview only — no Airtable writes")
    args = parser.parse_args()

    dry = args.dry_run
    if dry:
        print("DRY RUN — no changes will be written to Airtable\n")

    records = at.get_all_records()
    print(f"Fetched {len(records)} records.\n")

    updated = 0
    skipped = 0

    for r in records:
        fields = r.get("fields", {})
        rid = r["id"]

        business_name   = fields.get("Business Name", "").strip()
        audit_notes     = fields.get("Audit Notes", "")
        audit_page_url  = fields.get("Audit Page URL", "")
        owner_name      = fields.get("Contact Name", "").strip()
        instagram_handle = fields.get("Instagram Handle", "")

        if not business_name:
            print(f"  SKIP (no business name): record {rid}")
            skipped += 1
            continue

        email1_status = fields.get("Email 1 Status", "").strip()
        if email1_status not in REGENERATE_STATUSES:
            print(f"  SKIP ({email1_status or 'no status'}): {business_name}")
            skipped += 1
            continue

        # ── Email 1 ──────────────────────────────────────────────────────────
        email1_body, options = build_email1_body(
            business_name, owner_name, audit_notes, audit_page_url
        )
        email1_subject      = options[0]
        subject_options_str = ", ".join(options)

        # ── Email 2 ──────────────────────────────────────────────────────────
        e2 = write_followup_email(
            business_name,
            original_subject=email1_subject,
            audit_page_url=audit_page_url,
            owner_name=owner_name,
        )

        # ── DM ───────────────────────────────────────────────────────────────
        dm_text = write_dm(
            business_name,
            owner_name=owner_name,
            instagram_handle=instagram_handle,
        )

        # ── Call script ───────────────────────────────────────────────────────
        call_script = write_call_script(
            business_name,
            owner_name=owner_name,
            audit_notes=audit_notes,
        )

        update_fields = {
            "Email 1 Body":         email1_body,
            "Email 1 Subject":      email1_subject,
            "Subject Line Options": subject_options_str,
            "Email 1 Status":       "Pending Review",
            "Email 2 Body":         e2["body"],
            "Email 2 Subject":      e2["subject"],
            "Email 2 Status":       "Pending Review",
            "DM Text":              dm_text,
            "Call Script":          call_script,
        }

        if dry:
            print(f"  [{business_name}]")
            print(f"    Owner : {owner_name or '(none)'}")
            print(f"    E1 sub: {email1_subject}")
            print(f"    E1 body (first line): {email1_body.splitlines()[0]}")
            print(f"    E2 sub: {e2['subject']}")
            print(f"    DM    : {dm_text[:60]}...")
            print(f"    Call  : {call_script.splitlines()[0][:60]}...")
            print()
        else:
            at.update_record(rid, update_fields)
            name_label = f" ({owner_name})" if owner_name else ""
            print(f"  ✓ {business_name}{name_label}")

        updated += 1

    print()
    if dry:
        print(f"DRY RUN complete — {updated} records would be updated, {skipped} skipped.")
    else:
        print(f"Done — {updated} records updated, {skipped} skipped.")


if __name__ == "__main__":
    main()
