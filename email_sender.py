"""
Gmail SMTP sender and IMAP reply checker for Auralith Prospect Machine.

SMTP: Sends cold emails and follow-ups via Gmail SSL (port 465).
IMAP: Scans the inbox for replies from known prospect email addresses.

Run standalone to test SMTP:
    python email_sender.py --test-smtp your@email.com

Run standalone to test IMAP reply check:
    python email_sender.py --test-imap
"""

import os
import sys
import imaplib
import email as email_lib
import smtplib
import argparse
import logging
from typing import Optional, Set
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


# ─── SMTP sender ────────────────────────────────────────────────────────────────

def send_email(
    to_address: str,
    subject: str,
    body: str,
    from_name: str = "Jordan | Auralith Digital",
) -> bool:
    """
    Sends a plain-text email via Gmail SMTP (SSL).

    Returns True on success, False on failure.
    """
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        log.error("GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set in .env")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{GMAIL_ADDRESS}>"
    msg["To"] = to_address
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, [to_address], msg.as_string())
        log.info(f"Email sent → {to_address} | Subject: {subject}")
        return True
    except smtplib.SMTPException as e:
        log.error(f"SMTP error sending to {to_address}: {e}")
        return False


def send_internal_email(to_address: str, subject: str, body: str) -> bool:
    """Alias for internal emails (daily summary, alerts). Same sender."""
    return send_email(to_address, subject, body, from_name="Auralith Bot")


# ─── IMAP reply checker ─────────────────────────────────────────────────────────

def check_for_replies(prospect_emails: Set[str]) -> Set[str]:
    """
    Scans the Gmail INBOX for messages FROM any address in prospect_emails.

    Returns a set of prospect email addresses that have sent a reply.
    These should be marked as Reply Received = True in Airtable.
    """
    if not prospect_emails:
        return set()

    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        log.error("Gmail credentials not set in .env")
        return set()

    replied = set()

    try:
        conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        conn.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        conn.select("INBOX")

        # Search for any unseen messages (or all — we check sender address)
        # We search ALL so we don't miss older replies, and filter by known prospects
        status, data = conn.search(None, "ALL")
        if status != "OK":
            log.warning("IMAP search returned non-OK status")
            conn.logout()
            return set()

        message_ids = data[0].split()
        log.info(f"IMAP: checking {len(message_ids)} inbox messages against {len(prospect_emails)} prospect emails")

        # Build a lowercase set for case-insensitive matching
        prospect_lower = {e.lower() for e in prospect_emails}

        for msg_id in message_ids:
            status, msg_data = conn.fetch(msg_id, "(RFC822.HEADER)")
            if status != "OK":
                continue

            raw_header = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw_header)
            from_header = msg.get("From", "")

            # Extract just the email address from the From header
            sender_email = _extract_email_from_header(from_header)
            if sender_email and sender_email.lower() in prospect_lower:
                replied.add(sender_email.lower())
                log.info(f"Reply detected from: {sender_email}")

        conn.logout()

    except imaplib.IMAP4.error as e:
        log.error(f"IMAP error: {e}")

    return replied


def _extract_email_from_header(from_header: str) -> Optional[str]:
    """Extracts the email address from a From: header like 'Name <email@domain.com>'."""
    import re
    # Try angle-bracket form first: Name <email>
    match = re.search(r"<([^>]+)>", from_header)
    if match:
        return match.group(1).strip()
    # Bare address
    match = re.search(r"[\w.\-+]+@[\w.\-]+\.[a-zA-Z]{2,}", from_header)
    if match:
        return match.group(0).strip()
    return None


# ─── Standalone tests ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--test-smtp", metavar="TO_EMAIL",
                        help="Send a test email to this address")
    parser.add_argument("--test-imap", action="store_true",
                        help="Test IMAP connection and list recent senders")
    args = parser.parse_args()

    if args.test_smtp:
        print(f"\nSending test email to {args.test_smtp}...")
        ok = send_email(
            to_address=args.test_smtp,
            subject="Auralith test email",
            body=(
                "This is a test email from the Auralith Prospect Machine.\n\n"
                "If you received this, SMTP is working correctly.\n\n"
                "Jordan | Auralith Digital"
            ),
        )
        print("✓ Sent successfully!" if ok else "✗ Send failed — check logs above")

    elif args.test_imap:
        print("\nConnecting to Gmail IMAP...")
        # Pass a dummy set to see the connection works
        test_emails = {"test@example.com"}
        replies = check_for_replies(test_emails)
        print(f"IMAP connection successful. Replies found: {replies or 'none'}")

    else:
        parser.print_help()
