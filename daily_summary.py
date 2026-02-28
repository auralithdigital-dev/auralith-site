"""
Daily summary emailer for Auralith Prospect Machine.

Sends a morning briefing to support@auralithdigital.com with:
- How many new prospects were added
- Who was contacted (Email 1)
- Who received a follow-up (Email 2)
- Who needs a call today (Status = Call Scheduled, Call Done = false)
- Any replies received

Run standalone:
    python daily_summary.py
"""

import os
import logging
from datetime import date
from dotenv import load_dotenv

import airtable_client
import email_sender

load_dotenv()
log = logging.getLogger(__name__)

SUMMARY_EMAIL = os.getenv("SUMMARY_EMAIL", "support@auralithdigital.com")


def build_summary_text(data: dict) -> str:
    """Formats the summary data dict into a readable plain-text email."""
    today = date.today().strftime("%A, %B %d, %Y")

    def names(records):
        return [r.get("fields", {}).get("Business Name", "Unknown") for r in records]

    new = data["new_today"]
    followups = data["followup_today"]
    calls = data["needs_call"]
    replies = data["replied"]
    pending = data.get("pending_review", [])
    dm_ready = data.get("dm_ready", [])
    total = data["total_prospects"]

    lines = [
        f"Auralith Daily Pipeline Report — {today}",
        "=" * 50,
        "",
        f"TOTAL PROSPECTS IN PIPELINE: {total}",
        "",
        f"⚠  EMAILS AWAITING YOUR REVIEW: {len(pending)}",
    ]
    if pending:
        for r in pending:
            f = r.get("fields", {})
            n = f.get("Business Name", "Unknown")
            s1 = f.get("Email 1 Status", "")
            s2 = f.get("Email 2 Status", "")
            tag = "Email 1" if s1 == "Pending Review" else "Email 2"
            lines.append(f"  • {n}  [{tag}]")
        lines.append("  → Open Airtable, review, change status to 'Approved', then run: python3 send_approved.py")
    else:
        lines.append("  (none — inbox is clear)")

    lines += [
        "",
        f"INSTAGRAM DMs READY TO SEND: {len(dm_ready)}",
    ]
    if dm_ready:
        for r in dm_ready:
            f = r.get("fields", {})
            n = f.get("Business Name", "Unknown")
            handle = f.get("Instagram Handle", "")
            display = f"@{handle}" if handle else "(no handle)"
            lines.append(f"  • {n}  {display}")
        lines.append("  → Send manually from Instagram, then mark 'DM Sent' in Airtable")
    else:
        lines.append("  (none)")

    lines += [
        "",
        f"EMAILS SENT TODAY (Email 1): {len(new)}",
    ]
    if new:
        for name in names(new):
            lines.append(f"  • {name}")
    else:
        lines.append("  (none)")

    lines += [
        "",
        f"FOLLOW-UPS SENT TODAY (Email 2): {len(followups)}",
    ]
    if followups:
        for name in names(followups):
            lines.append(f"  • {name}")
    else:
        lines.append("  (none)")

    lines += [
        "",
        f"NEEDS A CALL TODAY ({len(calls)} total):",
    ]
    if calls:
        for r in calls:
            f = r.get("fields", {})
            name = f.get("Business Name", "Unknown")
            phone = f.get("Phone", "no phone")
            lines.append(f"  • {name}  |  {phone}")
    else:
        lines.append("  (none)")

    lines += [
        "",
        f"REPLIES RECEIVED ({len(replies)} total):",
    ]
    if replies:
        for r in replies:
            f = r.get("fields", {})
            name = f.get("Business Name", "Unknown")
            email = f.get("Email", "no email")
            lines.append(f"  • {name}  |  {email}")
    else:
        lines.append("  (none — check your inbox manually)")

    lines += [
        "",
        "─" * 50,
        "Sent by Auralith Prospect Machine",
    ]

    return "\n".join(lines)


def send_daily_summary() -> bool:
    """Fetches data from Airtable and sends the summary email."""
    log.info("Building daily summary...")
    data = airtable_client.get_todays_summary_data()
    body = build_summary_text(data)
    today = date.today().strftime("%b %d")
    subject = f"Auralith Pipeline — Daily Report {today}"

    ok = email_sender.send_internal_email(SUMMARY_EMAIL, subject, body)
    if ok:
        log.info(f"Daily summary sent to {SUMMARY_EMAIL}")
    else:
        log.error("Failed to send daily summary")
    return ok


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    print("Sending daily summary...\n")
    ok = send_daily_summary()
    if ok:
        print(f"✓ Summary sent to {SUMMARY_EMAIL}")
    else:
        print("✗ Failed — check logs above")
