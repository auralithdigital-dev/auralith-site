"""
Sends all emails marked 'Approved' in Airtable.

Review emails in Airtable first:
  - Open the Prospects table
  - Find rows where 'Email 1 Status' or 'Email 2 Status' = 'Pending Review'
  - Read the Email 1 Subject / Email 1 Body fields
  - Change status to 'Approved' to send, or 'Rejected' to skip

Then run:
    python3 send_approved.py

To preview what would send without actually sending:
    python3 send_approved.py --dry-run
"""

import time
import logging
import argparse
from datetime import date

import config
import airtable_client
import email_sender

log = logging.getLogger(__name__)


def send_approved(dry_run: bool = False):
    e1_sent, e1_skipped = _process_approved(
        records=airtable_client.get_approved_email1_records(),
        email_num=1,
        dry_run=dry_run,
    )
    return e1_sent, e1_skipped


def _process_approved(records: list, email_num: int, dry_run: bool):
    """
    Sends all approved emails for a given email number (1 or 2).
    Returns (sent: list[str], skipped: list[tuple[str, str]]).
    """
    subject_field = f"Email {email_num} Subject"
    body_field = f"Email {email_num} Body"
    status_field = f"Email {email_num} Status"
    sent_field = f"Email {email_num} Sent"
    sent_date_field = f"Email {email_num} Sent Date"

    if not records:
        log.info(f"Email {email_num}: no approved emails to send")
        return [], []

    log.info(f"Email {email_num}: {len(records)} candidate record(s) to process")
    sent = []
    skipped = []  # list of (business_name, reason) tuples

    for record in records:
        fields = record.get("fields", {})
        record_id = record["id"]
        name = fields.get("Business Name", "Unknown")
        to_email = fields.get("Email", "")
        subject = fields.get(subject_field, "")
        body = fields.get(body_field, "")

        # Safety check: status must be exactly the string "Approved" —
        # no leading/trailing spaces, no case variation, no other value.
        actual_status = fields.get(status_field, "")
        if actual_status != "Approved":
            reason = f'status is {repr(actual_status)}, expected exactly "Approved"'
            log.warning(f"SKIP {name}: {reason}")
            skipped.append((name, reason))
            continue

        if not to_email:
            reason = "no email address on record"
            log.warning(f"SKIP {name}: {reason}")
            skipped.append((name, reason))
            continue
        if not subject or not body:
            reason = "missing subject or body"
            log.warning(f"SKIP {name}: {reason}")
            skipped.append((name, reason))
            continue

        if dry_run:
            print(f"\n[DRY RUN] Would send Email {email_num} to {name} <{to_email}>")
            print(f"  Subject : {subject}")
            print(f"  Preview : {body[:150]}...")
            sent.append(name)
            continue

        ok = email_sender.send_email(to_email, subject, body)
        if ok:
            today = date.today().isoformat()
            update = {
                status_field: "Sent",
                sent_field: True,
                sent_date_field: today,
                "Last Contact Date": today,
            }
            # Email 1 sending → update Status to Contacted
            if email_num == 1:
                update["Status"] = "Contacted"
            # Email 2 sending → update Status to Followed Up
            elif email_num == 2:
                update["Status"] = "Followed Up"

            airtable_client.update_record(record_id, update)
            sent.append(name)
            log.info(f"Email {email_num} sent: {name} → {to_email}")
        else:
            reason = "SMTP send failed"
            log.warning(f"SKIP {name}: {reason}")
            skipped.append((name, reason))

        time.sleep(config.EMAIL_SEND_DELAY)

    return sent, skipped


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Send all Approved emails from the Airtable review queue"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would send without actually sending anything"
    )
    args = parser.parse_args()

    print(f"\n{'─'*50}")
    print(f"Auralith — Send Approved Emails {'[DRY RUN]' if args.dry_run else '[LIVE]'}")
    print(f"{'─'*50}\n")

    e1, e1_skip = send_approved(dry_run=args.dry_run)

    verb = "previewed" if args.dry_run else "sent"

    print(f"\n{'─'*50}")
    print(f"Email 1 {verb}: {len(e1)}  |  skipped: {len(e1_skip)}")
    for n in e1:
        print(f"  ✓ {n}")
    for name, reason in e1_skip:
        print(f"  ✗ {name}  ({reason})")

    if e1_skip:
        print(f"\nSkip log ({len(e1_skip)} total):")
        for name, reason in e1_skip:
            print(f"  ! {name}: {reason}")

    if not args.dry_run and e1:
        print(f"\nAirtable has been updated. Check your Sent folder to confirm delivery.")
        print(f"Email 2 follow-ups are handled separately by send_followups.py (3-day wait).")
