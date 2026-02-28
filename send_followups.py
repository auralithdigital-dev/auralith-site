"""
Sends Email 2 (follow-up) only to prospects that meet ALL of the following:
  1. Email 1 was sent (Email 1 Sent = TRUE)
  2. Email 1 Sent Date is 3 or more days ago
  3. Reply Received is empty or False
  4. Email 2 Status is exactly "Approved"
  5. Email 2 not yet sent (Email 2 Sent = FALSE)

This script is intentionally separate from send_approved.py.
send_approved.py handles Email 1 only.
This script handles Email 2 only, with the 3-day gate enforced.

Run:
    python3 send_followups.py
    python3 send_followups.py --dry-run   # preview without sending
"""

import time
import logging
import argparse
from datetime import date, timedelta

import config
import airtable_client
import email_sender

log = logging.getLogger(__name__)

FOLLOWUP_DAYS = config.FOLLOW_UP_DAYS   # 3


def send_followups(dry_run: bool = False):
    cutoff = (date.today() - timedelta(days=FOLLOWUP_DAYS)).isoformat()
    records = airtable_client.get_sendable_email2_records(cutoff_date=cutoff)

    if not records:
        log.info("Email 2: no records eligible for follow-up send today")
        return [], []

    log.info(f"Email 2: {len(records)} candidate record(s) to process (Email 1 sent before {cutoff})")
    sent = []
    skipped = []

    for record in records:
        fields = record.get("fields", {})
        record_id = record["id"]
        name = fields.get("Business Name", "Unknown")
        to_email = fields.get("Email", "")
        subject = fields.get("Email 2 Subject", "")
        body = fields.get("Email 2 Body", "")
        e1_sent_date = fields.get("Email 1 Sent Date", "")

        # Safety check: Email 2 Status must be exactly "Approved"
        actual_status = fields.get("Email 2 Status", "")
        if actual_status != "Approved":
            reason = f'Email 2 Status is {repr(actual_status)}, expected exactly "Approved"'
            log.warning(f"SKIP {name}: {reason}")
            skipped.append((name, reason))
            continue

        # Safety check: Email 1 must have a sent date
        if not e1_sent_date:
            reason = "Email 1 Sent Date is missing"
            log.warning(f"SKIP {name}: {reason}")
            skipped.append((name, reason))
            continue

        # Safety check: enforce 3-day gap in Python as well (belt-and-suspenders)
        try:
            days_since = (date.today() - date.fromisoformat(e1_sent_date)).days
        except ValueError:
            reason = f"Email 1 Sent Date is not a valid date: {repr(e1_sent_date)}"
            log.warning(f"SKIP {name}: {reason}")
            skipped.append((name, reason))
            continue

        if days_since < FOLLOWUP_DAYS:
            reason = f"only {days_since} day(s) since Email 1 (need {FOLLOWUP_DAYS})"
            log.warning(f"SKIP {name}: {reason}")
            skipped.append((name, reason))
            continue

        if not to_email:
            reason = "no email address on record"
            log.warning(f"SKIP {name}: {reason}")
            skipped.append((name, reason))
            continue

        if not subject or not body:
            reason = "missing Email 2 subject or body"
            log.warning(f"SKIP {name}: {reason}")
            skipped.append((name, reason))
            continue

        if dry_run:
            print(f"\n[DRY RUN] Would send Email 2 to {name} <{to_email}>")
            print(f"  Days since Email 1 : {days_since}")
            print(f"  Subject            : {subject}")
            print(f"  Preview            : {body[:150]}...")
            sent.append(name)
            continue

        ok = email_sender.send_email(to_email, subject, body)
        if ok:
            today = date.today().isoformat()
            airtable_client.update_record(record_id, {
                "Email 2 Status":    "Sent",
                "Email 2 Sent":      True,
                "Email 2 Sent Date": today,
                "Last Contact Date": today,
                "Status":            "Followed Up",
            })
            sent.append(name)
            log.info(f"Email 2 sent: {name} → {to_email} ({days_since}d after Email 1)")
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
        description="Send Email 2 follow-ups — only to prospects 3+ days after Email 1 with no reply"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would send without actually sending anything"
    )
    args = parser.parse_args()

    cutoff = (date.today() - timedelta(days=FOLLOWUP_DAYS)).isoformat()

    print(f"\n{'─'*55}")
    print(f"Auralith — Send Email 2 Follow-ups {'[DRY RUN]' if args.dry_run else '[LIVE]'}")
    print(f"3-day cutoff: Email 1 must have been sent before {cutoff}")
    print(f"{'─'*55}\n")

    sent, skipped = send_followups(dry_run=args.dry_run)

    verb = "previewed" if args.dry_run else "sent"

    print(f"\n{'─'*55}")
    print(f"Email 2 {verb}: {len(sent)}  |  skipped: {len(skipped)}")
    for n in sent:
        print(f"  ✓ {n}")
    for name, reason in skipped:
        print(f"  ✗ {name}  ({reason})")

    if skipped:
        print(f"\nSkip log ({len(skipped)} total):")
        for name, reason in skipped:
            print(f"  ! {name}: {reason}")

    if not args.dry_run and sent:
        print(f"\nAirtable has been updated. Check your Sent folder to confirm delivery.")
