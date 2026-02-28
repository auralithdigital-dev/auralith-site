"""
Follow-up email queuer for Auralith Prospect Machine.

Finds prospects where Email 1 was sent 3+ days ago with no reply,
generates a follow-up email, and queues it in Airtable as 'Pending Review'.
Nothing sends automatically — run send_approved.py to send approved emails.

Run standalone (dry-run preview):
    python3 follow_up.py --dry-run
"""

import logging
import argparse
from typing import List
from datetime import date, timedelta

import config
import airtable_client
import email_writer

log = logging.getLogger(__name__)


def queue_followups(dry_run: bool = False) -> List[str]:
    """
    Queues follow-up emails for eligible prospects.
    Returns a list of business names that were queued.
    """
    cutoff = (date.today() - timedelta(days=config.FOLLOW_UP_DAYS)).isoformat()
    candidates = airtable_client.get_records_needing_followup_queued(cutoff)

    if not candidates:
        log.info("Follow-up: no candidates today")
        return []

    log.info(f"Follow-up: {len(candidates)} candidate(s) found (Email 1 sent before {cutoff})")
    queued = []

    for record in candidates:
        fields = record.get("fields", {})
        record_id = record["id"]
        name = fields.get("Business Name", "your business")
        to_email = fields.get("Email", "")

        if not to_email:
            log.warning(f"No email for {name}, skipping")
            continue

        original_subject = fields.get("Email 1 Subject", "")
        audit_page_url = fields.get("Audit Page URL", "")
        owner_name = fields.get("Contact Name", "")

        email = email_writer.write_followup_email(
            name,
            original_subject=original_subject,
            audit_page_url=audit_page_url,
            owner_name=owner_name,
        )

        if dry_run:
            print(f"\n[DRY RUN] Would queue follow-up for {name} <{to_email}>")
            print(f"  Subject: {email['subject']}")
            print(f"  Preview: {email['body'][:150]}...")
            queued.append(name)
            continue

        airtable_client.update_record(record_id, {
            "Email 2 Subject": email["subject"],
            "Email 2 Body": email["body"],
            "Email 2 Status": "Pending Review",
        })
        queued.append(name)
        log.info(f"Follow-up queued for review: {name}")

    return queued


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without updating Airtable")
    args = parser.parse_args()

    results = queue_followups(dry_run=args.dry_run)
    print(f"\nFollow-ups queued for review: {len(results)}")
    for name in results:
        print(f"  - {name}")
