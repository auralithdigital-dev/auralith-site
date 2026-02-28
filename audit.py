"""
Pre-email audit for Auralith Prospect Machine.

For each new prospect, visits their website and Google listing to gather
specific, actionable intelligence before Pyetra's email is written:

  - Online booking: does the site have a booking widget or link?
  - Google reviews: any complaints about missed calls / hard to reach?
  - Contact options: form, chat widget, phone only?
  - Instagram activity: last post date, comment engagement?

Findings are saved to the "Audit Notes" Airtable field and passed to
email_writer.py so every email references real, specific details.

Run standalone:
    python3 audit.py --dry-run
"""

import os
import re
import time
import logging
import argparse
from typing import Optional
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

import config
import airtable_client

load_dotenv()
log = logging.getLogger(__name__)

GMAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# ─── Booking platform fingerprints ──────────────────────────────────────────────
BOOKING_PLATFORMS = {
    "Vagaro":      ["vagaro.com"],
    "MoeGo":       ["moego.pet", "booking.moego"],
    "PetDesk":     ["petdesk.com"],
    "Booksy":      ["booksy.com"],
    "StyleSeat":   ["styleseat.com"],
    "GlossGenius": ["glossgenius.com"],
    "Square":      ["squareup.com/appointments", "square.site"],
    "Acuity":      ["acuityscheduling.com"],
    "Calendly":    ["calendly.com"],
    "boulevard":   ["boulevard.io", "joinblvd.com"],
}

# Booking-related keywords to look for if no known platform found
BOOKING_KEYWORDS = [
    "book now", "book online", "book appointment", "schedule online",
    "request appointment", "online booking",
]

# ─── Review pain-point keywords ─────────────────────────────────────────────────
PAIN_KEYWORDS = [
    "missed call", "no answer", "didn't call back", "never called back",
    "hard to reach", "couldn't reach", "no callback", "didn't return",
    "waiting on hold", "on hold", "voicemail", "didn't respond",
    "hard to get in touch", "couldn't get through", "unanswered",
    "lapsed", "haven't heard", "no follow up", "forgot about me",
    "lost client", "stopped going", "haven't been back",
]

# ─── Chat / contact widget fingerprints ─────────────────────────────────────────
CHAT_WIDGETS = {
    "Intercom":  ["intercomcdn.com", "widget.intercom.io"],
    "Drift":     ["drift.com", "js.driftt.com"],
    "Tidio":     ["tidio.com"],
    "Tawk":      ["tawk.to"],
    "Zendesk":   ["zdassets.com", "zendesk.com/embeddable"],
    "LiveChat":  ["livechatinc.com"],
    "HubSpot":   ["hs-scripts.com", "hubspot.com/conversations"],
}


# ─── Website checkers ───────────────────────────────────────────────────────────

def check_online_booking(html: str, raw_source: str) -> dict:
    """
    Returns {"has_booking": bool, "platform": str|None, "detail": str}
    """
    raw_lower = raw_source.lower()

    # Check for known platforms
    for platform, signals in BOOKING_PLATFORMS.items():
        if any(s in raw_lower for s in signals):
            return {
                "has_booking": True,
                "platform": platform,
                "detail": f"Online booking via {platform}",
            }

    # Check for generic booking keywords in visible text
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True).lower()
    for kw in BOOKING_KEYWORDS:
        if kw in text:
            return {
                "has_booking": True,
                "platform": None,
                "detail": "Online booking button/link found on site",
            }

    return {
        "has_booking": False,
        "platform": None,
        "detail": "No online booking found, likely phone-only",
    }


def check_contact_options(html: str, raw_source: str) -> dict:
    """
    Returns {"has_form": bool, "has_chat": bool, "chat_platform": str|None}
    """
    raw_lower = raw_source.lower()
    soup = BeautifulSoup(html, "html.parser")

    # Contact form: look for <form> tags with input fields
    forms = soup.find_all("form")
    has_form = any(f.find(["input", "textarea"]) for f in forms)

    # Chat widgets
    chat_platform = None
    for platform, signals in CHAT_WIDGETS.items():
        if any(s in raw_lower for s in signals):
            chat_platform = platform
            break

    return {
        "has_form": has_form,
        "has_chat": chat_platform is not None,
        "chat_platform": chat_platform,
    }


# ─── Google Places reviews ───────────────────────────────────────────────────────

def fetch_google_reviews(place_id: str) -> list[dict]:
    """
    Fetches up to 5 Google reviews for a place via Places Details API.
    Returns list of {"rating": int, "text": str, "time": str}
    """
    if not GMAPS_API_KEY or not place_id:
        return []

    params = {
        "place_id": place_id,
        "fields": "rating,reviews",
        "key": GMAPS_API_KEY,
    }
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params=params,
            timeout=10,
        )
        result = resp.json().get("result", {})
        reviews = result.get("reviews", [])
        return [
            {
                "rating": r.get("rating", 0),
                "text": r.get("text", ""),
                "time": r.get("relative_time_description", ""),
            }
            for r in reviews
        ]
    except Exception as e:
        log.debug(f"Reviews fetch failed for {place_id}: {e}")
        return []


def scan_reviews_for_pain_points(reviews: list[dict]) -> dict:
    """
    Scans review text for pain-point keywords.
    Returns {"found": bool, "complaint": str|None, "rating": int|None}
    """
    for review in reviews:
        text = review.get("text", "").lower()
        for kw in PAIN_KEYWORDS:
            if kw in text:
                # Return the original (non-lowered) sentence containing the keyword
                original = review.get("text", "")
                sentences = re.split(r"[.!?]", original)
                for sentence in sentences:
                    if kw in sentence.lower():
                        complaint = sentence.strip()
                        if complaint:
                            return {
                                "found": True,
                                "complaint": complaint,
                                "rating": review.get("rating"),
                            }

    return {"found": False, "complaint": None, "rating": None}


# ─── Instagram activity ──────────────────────────────────────────────────────────

def check_instagram_activity(handle: str) -> dict:
    """
    Attempts a lightweight check of a public Instagram page.
    Instagram is JS-heavy so we can only extract limited info from the meta tags.
    Returns {"reachable": bool, "detail": str}
    """
    if not handle:
        return {"reachable": False, "detail": "No Instagram handle found"}

    handle = handle.lstrip("@")
    url = f"https://www.instagram.com/{handle}/"

    try:
        resp = requests.get(
            url,
            headers={**config.REQUEST_HEADERS, "Accept-Language": "en-US,en;q=0.9"},
            timeout=8,
            allow_redirects=True,
        )
        if resp.status_code == 200:
            # Instagram blocks most scrapers but meta tags sometimes survive
            soup = BeautifulSoup(resp.text, "html.parser")
            desc = ""
            for tag in soup.find_all("meta"):
                if tag.get("property") in ("og:description", "description"):
                    desc = tag.get("content", "")
                    break

            if desc and ("posts" in desc.lower() or "followers" in desc.lower()):
                return {"reachable": True, "detail": f"Active profile found (@{handle}). {desc[:120]}"}
            return {"reachable": True, "detail": f"Profile exists at @{handle}, content not fully accessible"}
        elif resp.status_code == 404:
            return {"reachable": False, "detail": f"@{handle} not found on Instagram"}
        else:
            return {"reachable": False, "detail": f"Instagram returned {resp.status_code} for @{handle}"}
    except Exception as e:
        log.debug(f"Instagram check failed for @{handle}: {e}")
        return {"reachable": False, "detail": f"Could not reach Instagram for @{handle}"}


# ─── Main audit function ─────────────────────────────────────────────────────────

def audit_prospect(
    name: str,
    website: str,
    place_id: str,
    instagram_handle: str = "",
) -> dict:
    """
    Runs a full audit for one prospect. Returns a structured findings dict
    and a human-readable "Audit Notes" string for Airtable.
    """
    findings = {
        "booking": {},
        "contact": {},
        "reviews": {},
        "instagram": {},
    }
    notes_lines = [f"Audit for {name} — {date.today().isoformat()}"]

    # ── Website audit ────────────────────────────────────────────────────────────
    if website:
        if not website.startswith(("http://", "https://")):
            website = "https://" + website
        try:
            resp = requests.get(
                website,
                headers=config.REQUEST_HEADERS,
                timeout=config.REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            html = resp.text
            raw = resp.text  # same, used for substring checks
        except Exception as e:
            log.debug(f"Website fetch failed for {name}: {e}")
            html = ""
            raw = ""

        if html:
            booking = check_online_booking(html, raw)
            contact = check_contact_options(html, raw)
            findings["booking"] = booking
            findings["contact"] = contact

            notes_lines.append(f"BOOKING: {booking['detail']}")

            contact_parts = []
            if contact["has_form"]:
                contact_parts.append("contact form")
            if contact["has_chat"]:
                contact_parts.append(f"live chat ({contact['chat_platform']})")
            if not contact_parts:
                contact_parts.append("no form or chat found")
            notes_lines.append(f"CONTACT: {', '.join(contact_parts)}")
        else:
            notes_lines.append("WEBSITE: Could not load")
    else:
        notes_lines.append("WEBSITE: No website on file")

    # ── Google reviews ───────────────────────────────────────────────────────────
    if place_id:
        reviews = fetch_google_reviews(place_id)
        pain = scan_reviews_for_pain_points(reviews)
        findings["reviews"] = pain

        if pain["found"]:
            notes_lines.append(f"REVIEWS: Pain point found (rated {pain['rating']}/5): \"{pain['complaint']}\"")
        elif reviews:
            avg = round(sum(r["rating"] for r in reviews) / len(reviews), 1)
            notes_lines.append(f"REVIEWS: {len(reviews)} reviews checked, avg {avg}/5, no pain-point complaints found")
        else:
            notes_lines.append("REVIEWS: No reviews returned by API")
    else:
        notes_lines.append("REVIEWS: No Place ID, skipped")

    # ── Instagram ────────────────────────────────────────────────────────────────
    if instagram_handle:
        ig = check_instagram_activity(instagram_handle)
        findings["instagram"] = ig
        notes_lines.append(f"INSTAGRAM: {ig['detail']}")
    else:
        notes_lines.append("INSTAGRAM: No handle found")

    audit_notes = "\n".join(notes_lines)
    return {"findings": findings, "audit_notes": audit_notes}


def build_email_context(findings: dict, website_content: str) -> str:
    """
    Combines website content with structured audit findings into a rich
    context string for email_writer.py.
    """
    parts = [website_content] if website_content else []

    booking = findings.get("booking", {})
    if not booking.get("has_booking"):
        parts.append("AUDIT: No online booking detected, likely phone-only bookings.")

    pain = findings.get("reviews", {})
    if pain.get("found"):
        parts.append(f"AUDIT: Google review complaint about: \"{pain['complaint']}\"")

    contact = findings.get("contact", {})
    if not contact.get("has_form") and not contact.get("has_chat"):
        parts.append("AUDIT: No contact form or chat widget on website.")

    ig = findings.get("instagram", {})
    if ig.get("reachable"):
        parts.append(f"AUDIT: Instagram active. {ig.get('detail', '')}")

    return " ".join(parts)


# ─── Batch runner ────────────────────────────────────────────────────────────────

def run_audit_for_new_prospects(dry_run: bool = False) -> list[str]:
    """
    Audits all prospects that have no Audit Notes yet.
    Returns list of business names audited.
    """
    all_records = airtable_client.get_all_records()
    to_audit = [
        r for r in all_records
        if not r["fields"].get("Audit Notes")
        and r["fields"].get("Status") == "New"
    ]

    if not to_audit:
        log.info("Audit: no prospects need auditing")
        return []

    log.info(f"Audit: running for {len(to_audit)} prospect(s)")
    audited = []

    for record in to_audit:
        f = record["fields"]
        record_id = record["id"]
        name = f.get("Business Name", "")
        website = f.get("Website", "")
        place_id = f.get("Place ID", "")
        instagram = f.get("Instagram Handle", "")

        log.info(f"Auditing: {name}")
        result = audit_prospect(name, website, place_id, instagram)

        if dry_run:
            print(f"\n[DRY RUN] Audit for {name}:")
            print(result["audit_notes"])
        else:
            airtable_client.update_record(record_id, {
                "Audit Notes": result["audit_notes"],
            })
            log.info(f"Audit saved: {name}")

        audited.append(name)
        time.sleep(config.GMAPS_DELAY)

    return audited


# ─── Standalone test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("Running audit for all unaudited New prospects...\n")
    results = run_audit_for_new_prospects(dry_run=args.dry_run)
    print(f"\nAudited: {len(results)}")
    for n in results:
        print(f"  - {n}")
