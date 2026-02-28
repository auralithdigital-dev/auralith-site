"""
Email, DM, and call script generator for Auralith Prospect Machine.

All copy is templated exactly — no AI-generated prose for the body, DM, or call script.
Claude is used only for one small task: extracting the owner's first name from website text.

Templates:
  EMAIL 1  — First touch, 5 subject line options stored in Airtable
  EMAIL 2  — Follow-up (Re: original subject), 3 days, no reply
  DM       — Instagram DM sent manually by Pyetra
  CALL     — 4-line call script stored in Airtable

Run standalone to preview:
    python3 email_writer.py
"""

import os
import re
import logging
from typing import Optional, List
from dotenv import load_dotenv
import anthropic

import config

load_dotenv()
log = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"   # smallest model — only used for name extraction

CALENDLY = config.CALENDLY_URL


# ─── Owner name extraction ────────────────────────────────────────────────────────

def _extract_first_name(website_content: str, audit_notes: str = "") -> Optional[str]:
    """
    Uses Claude to find the owner's first name from website text.
    Returns the first name as a string, or None if not found.
    """
    if not website_content and not audit_notes:
        return None

    context = f"{website_content[:500]}\n\n{audit_notes}".strip()

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=15,
            system=(
                "Extract the business owner's first name from the text. "
                "Reply with only the first name, nothing else. "
                "If no clear personal first name is present, reply with: NONE"
            ),
            messages=[{"role": "user", "content": context}],
        )
        result = message.content[0].text.strip().split()[0]
        if not result or result.upper() == "NONE" or not result.isalpha():
            return None
        return result.capitalize()
    except Exception as e:
        log.debug(f"Name extraction failed: {e}")
        return None


# ─── Audit findings parsers ───────────────────────────────────────────────────────

def _parse_findings_to_statements(audit_notes: str) -> List[str]:
    """
    Converts Audit Notes lines into direct, declarative statements.
    Only negative findings are returned. Up to 3.

    Good: "There is no online booking on your site."
    Bad:  "It looks like there might not be a booking form."
    """
    statements = []

    for line in audit_notes.splitlines():
        line = line.strip()

        if line.startswith("BOOKING:"):
            val = line[8:].strip()
            if "no online booking" in val.lower() or "phone-only" in val.lower():
                statements.append("There is no online booking on your site")

        elif line.startswith("CONTACT:"):
            val = line[8:].strip()
            if "no form or chat found" in val.lower():
                statements.append("There is no contact form or chat option on your website")

        elif line.startswith("REVIEWS:"):
            val = line[8:].strip()
            if "pain point found" in val.lower():
                match = re.search(r'"([^"]+)"', val)
                if match:
                    complaint = match.group(1).rstrip(".")
                    statements.append(f'A Google reviewer said "{complaint}"')
                else:
                    statements.append("Your Google reviews mention communication problems")

        elif line.startswith("INSTAGRAM:"):
            val = line[10:].strip()
            if any(x in val for x in [
                "No handle found", "not found on Instagram", "Could not reach",
            ]):
                statements.append("You have no Instagram presence we could find")

        elif line.startswith("WEBSITE:"):
            val = line[8:].strip()
            if "could not load" in val.lower():
                statements.append("Your website did not load when we checked")
            elif "no website" in val.lower():
                statements.append("You have no website we could find")

    return statements[:3]


def _parse_findings_for_call(audit_notes: str) -> List[str]:
    """
    Short phrases for use in the call script: "found X and Y".
    Returns up to 2 phrases.
    """
    phrases = []

    for line in audit_notes.splitlines():
        line = line.strip()

        if line.startswith("BOOKING:"):
            val = line[8:].strip()
            if "no online booking" in val.lower() or "phone-only" in val.lower():
                phrases.append("no online booking on your site")

        elif line.startswith("CONTACT:"):
            val = line[8:].strip()
            if "no form or chat found" in val.lower():
                phrases.append("no contact form or chat on your website")

        elif line.startswith("REVIEWS:"):
            val = line[8:].strip()
            if "pain point found" in val.lower():
                phrases.append("a communication complaint in your Google reviews")

        elif line.startswith("INSTAGRAM:"):
            val = line[10:].strip()
            if any(x in val for x in [
                "No handle found", "not found on Instagram", "Could not reach",
            ]):
                phrases.append("no Instagram presence")

        elif line.startswith("WEBSITE:"):
            val = line[8:].strip()
            if "could not load" in val.lower() or "no website" in val.lower():
                phrases.append("an issue with your website")

    return phrases[:2]


# ─── Subject line options ─────────────────────────────────────────────────────────

def _build_subject_options(salon_name: str) -> List[str]:
    """Returns the 5 fixed subject line options for Email 1."""
    return [
        f"{salon_name} I found something on your site",
        "your website is losing you appointments",
        f"I audited {salon_name} this morning",
        f"quick question about {salon_name}'s bookings",
        f"{salon_name} 3 things I noticed",
    ]


# ─── Email 1 — First touch ────────────────────────────────────────────────────────

def write_cold_email(
    business_name: str,
    audit_notes: str = "",
    audit_page_url: str = "",
    website_content: str = "",
    recipient_email: str = "",
) -> dict:
    """
    Generates Email 1 from the fixed template.

    Returns:
        subject          — first subject option (default)
        subject_options  — all 5, comma-separated (store in Airtable)
        body             — plain-text email body
        owner_name       — first name found, or "" (store in Airtable if found)
    """
    # 1. Owner name
    owner_name = _extract_first_name(website_content, audit_notes) or ""

    # 2. Subject options
    options = _build_subject_options(business_name)
    subject_options_str = ", ".join(options)

    # 3. Audit findings as inline phrases for "I noticed X and Y"
    phrases = _parse_findings_for_call(audit_notes)

    # 4. Audit page URL — must be a public HTTP URL to be usable
    if audit_page_url and audit_page_url.startswith("http"):
        url = audit_page_url
    else:
        url = "[AUDIT PAGE URL]"

    # 5. Compose body
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

    return {
        "subject": options[0],
        "subject_options": subject_options_str,
        "body": "\n".join(lines),
        "owner_name": owner_name,
    }


# ─── Email 2 — Follow-up ─────────────────────────────────────────────────────────

def write_followup_email(
    business_name: str,
    original_subject: str = "",
    audit_page_url: str = "",
    owner_name: str = "",
) -> dict:
    """
    Generates Email 2 (follow-up) from the fixed template.
    Subject is always "Re: [original subject line]".

    Returns {subject, body}
    """
    subject = (
        f"Re: {original_subject}"
        if original_subject
        else f"Re: {business_name} — I found something on your site"
    )

    if audit_page_url and audit_page_url.startswith("http"):
        url = audit_page_url
    else:
        url = "[AUDIT PAGE URL]"

    lines = []
    if owner_name:
        lines.append(owner_name + ",")
    lines.append("Just bumping this up in case it got buried.")
    lines.append(f"The breakdown I put together for {business_name} is still here: {url}")
    lines.append("No pressure, just didn't want it to go unseen.")
    lines.append("Pyetra")

    return {
        "subject": subject,
        "body": "\n".join(lines),
    }


# ─── Instagram DM ─────────────────────────────────────────────────────────────────

def write_dm(
    business_name: str,
    owner_name: str = "",
    instagram_handle: str = "",
    website_content: str = "",   # kept for call-site compatibility, unused
) -> str:
    """
    Returns the Instagram DM text from the fixed template.
    Sent manually by Pyetra from Instagram.
    """
    greeting = f"Hey {owner_name}, " if owner_name else "Hey, "
    return (
        f"{greeting}I sent you an email about {business_name} earlier this week. "
        "Ran a quick audit on your site and found a few booking gaps. "
        "Left the breakdown in your inbox if you want to take a look. No pitch, just the findings."
    )


# ─── Call script ──────────────────────────────────────────────────────────────────

def write_call_script(
    business_name: str,
    owner_name: str = "",
    audit_notes: str = "",
) -> str:
    """
    Returns the 4-line call script from the fixed template.
    Stored in the Call Script field in Airtable.
    """
    phrases = _parse_findings_for_call(audit_notes)
    finding1 = phrases[0] if phrases else "some gaps in your booking setup"
    finding2 = phrases[1] if len(phrases) > 1 else "your online contact options"

    name_check = f"is this {owner_name}? " if owner_name else ""

    lines = [
        f'Line 1: "Hi, {name_check}This is Pyetra — I sent you an email and a DM about {business_name} earlier this week."',
        f'Line 2: "I ran a quick audit on your site and found {finding1} and {finding2}. I put it all in a report I sent over."',
        'Line 3: "I\'m not calling to pitch you anything — I just wanted to make sure you saw it and answer any questions if you had them."',
        'Line 4: "Do you have 20 minutes this week to go through it together?"',
    ]
    return "\n".join(lines)


# ─── Standalone preview ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    sample_audit = (
        "Audit for Pawfect Paws Grooming — 2026-02-27\n"
        "BOOKING: No online booking found, likely phone-only\n"
        "CONTACT: no form or chat found\n"
        "REVIEWS: Pain point found (rated 3.4/5): \"hard to reach\"\n"
        "INSTAGRAM: No handle found"
    )
    sample_website = (
        "Pawfect Paws Grooming — Owner Lisa has been grooming dogs in Fort Lauderdale "
        "since 2012. Full grooming, baths, nail trims, breed cuts. Book by phone."
    )
    sample_url = "https://auralithdigital.netlify.app/audits/pawfect-paws-grooming.html"

    print("═" * 60)
    print("EMAIL 1 — COLD EMAIL")
    print("═" * 60)
    e1 = write_cold_email(
        "Pawfect Paws Grooming",
        audit_notes=sample_audit,
        audit_page_url=sample_url,
        website_content=sample_website,
    )
    print(f"SUBJECT: {e1['subject']}")
    print(f"\nSUBJECT OPTIONS:\n{e1['subject_options']}")
    print(f"\nOWNER NAME: {e1['owner_name'] or '(none found)'}")
    print(f"\nBODY:\n{e1['body']}")

    print("\n" + "═" * 60)
    print("EMAIL 2 — FOLLOW-UP")
    print("═" * 60)
    e2 = write_followup_email(
        "Pawfect Paws Grooming",
        original_subject=e1["subject"],
        audit_page_url=sample_url,
        owner_name=e1["owner_name"],
    )
    print(f"SUBJECT: {e2['subject']}")
    print(f"\nBODY:\n{e2['body']}")

    print("\n" + "═" * 60)
    print("INSTAGRAM DM")
    print("═" * 60)
    dm = write_dm("Pawfect Paws Grooming", owner_name=e1["owner_name"])
    print(dm)

    print("\n" + "═" * 60)
    print("CALL SCRIPT")
    print("═" * 60)
    cs = write_call_script(
        "Pawfect Paws Grooming",
        owner_name=e1["owner_name"],
        audit_notes=sample_audit,
    )
    print(cs)
