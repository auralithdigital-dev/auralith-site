"""
Per-prospect HTML audit report generator for Auralith Prospect Machine.

For each prospect with Audit Notes in Airtable, generates a personalized
HTML page at audits/[slug].html and writes the file path back to Airtable.

Run:
    python3 generate_audit_page.py           # Generate for all prospects missing a page
    python3 generate_audit_page.py --all     # Regenerate all pages
    python3 generate_audit_page.py --dry-run # Preview findings, no files written

Host the audits/ folder on Netlify Drop, GitHub Pages, or any static host.
Once hosted, update the Audit Page URL records to reflect the public URL.
"""

import os
import re
import sys
import time
import logging
import argparse
from datetime import date
from typing import Optional, List

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

import config
import airtable_client

load_dotenv()
log = logging.getLogger(__name__)

CALENDLY = config.CALENDLY_URL
AUDITS_DIR = os.path.join(os.path.dirname(__file__), "audits")


# ─── Slug helper ────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Converts a business name to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


# ─── Audit notes parser ─────────────────────────────────────────────────────────

def parse_audit_notes(audit_notes: str) -> dict:
    """
    Parses the structured Audit Notes text into a dict.
    Keys: booking, contact, reviews, instagram, website
    """
    findings = {}
    for line in audit_notes.splitlines():
        stripped = line.strip()
        if stripped.startswith("BOOKING:"):
            findings["booking"] = stripped[8:].strip()
        elif stripped.startswith("CONTACT:"):
            findings["contact"] = stripped[8:].strip()
        elif stripped.startswith("REVIEWS:"):
            findings["reviews"] = stripped[8:].strip()
        elif stripped.startswith("INSTAGRAM:"):
            findings["instagram"] = stripped[10:].strip()
        elif stripped.startswith("WEBSITE:"):
            findings["website"] = stripped[8:].strip()
    return findings


def findings_to_problems(findings: dict) -> List[dict]:
    """
    Maps parsed audit findings to a list of problem dicts.
    Each dict has: title, found, cost, fix
    Only negative findings become problems.
    """
    problems = []

    # ── Booking ──────────────────────────────────────────────────────────────────
    booking = findings.get("booking", "")
    if booking and ("no online booking" in booking.lower() or "phone-only" in booking.lower()):
        problems.append({
            "title": "No online booking",
            "found": booking,
            "cost": (
                "Calls come in during grooms. If no one picks up, that booking is gone. "
                "Phone-only salons lose an estimated 2 to 5 bookings a week to missed calls alone."
            ),
            "fix": (
                "An automated missed-call text replies within 60 seconds and includes a direct "
                "booking link, so owners can schedule without ever calling back."
            ),
        })

    # ── Contact options ──────────────────────────────────────────────────────────
    contact = findings.get("contact", "")
    if contact and "no form or chat found" in contact.lower():
        problems.append({
            "title": "No after-hours contact option on your website",
            "found": contact,
            "cost": (
                "Most people decide to book between 7pm and 10pm. Without a form or chat widget, "
                "there is no way to capture that interest while you are closed."
            ),
            "fix": (
                "A simple contact capture form routes after-hours inquiries straight to your inbox "
                "or phone, so every lead gets a response by morning."
            ),
        })

    # ── Reviews ──────────────────────────────────────────────────────────────────
    reviews = findings.get("reviews", "")
    if reviews and "pain point found" in reviews.lower():
        match = re.search(r'"([^"]+)"', reviews)
        complaint_quote = match.group(1) if match else ""
        found_text = (
            f'A reviewer wrote: "{complaint_quote}"' if complaint_quote else reviews
        )
        problems.append({
            "title": "Public complaint in Google reviews",
            "found": found_text,
            "cost": (
                "Negative reviews about communication are the first thing new clients read. "
                "One missed-call complaint costs an estimated 3 to 5 bookings per month."
            ),
            "fix": (
                "Faster response times eliminate the source of these complaints. "
                "Automated follow-up means no call ever goes unanswered again."
            ),
        })

    # ── Instagram ────────────────────────────────────────────────────────────────
    instagram = findings.get("instagram", "")
    if instagram and any(x in instagram for x in [
        "No handle found",
        "not found on Instagram",
        "Could not reach",
    ]):
        problems.append({
            "title": "No Instagram presence found",
            "found": instagram,
            "cost": (
                "Instagram is where South Florida pet owners discover local groomers. "
                "With no presence, you are invisible to a growing segment of the market."
            ),
            "fix": (
                "Our automation gives you hours back each week, so you have time to post "
                "consistently without it coming at the cost of your clients."
            ),
        })

    # ── Website not loading ──────────────────────────────────────────────────────
    website = findings.get("website", "")
    if website and ("could not load" in website.lower() or "no website" in website.lower()):
        problems.append({
            "title": "Website issue detected",
            "found": website,
            "cost": (
                "A missing or unreachable website sends potential clients straight to a competitor. "
                "Google also lowers rankings for sites with technical problems."
            ),
            "fix": (
                "We flag technical gaps so you know exactly what to fix. "
                "Our tools work alongside any website, old or new."
            ),
        })

    return problems


# ─── Logo scraper ────────────────────────────────────────────────────────────────

def try_get_logo(website_url: str) -> Optional[str]:
    """
    Attempts to find a logo URL from og:image or apple-touch-icon.
    Returns a URL string or None if nothing found.
    """
    if not website_url:
        return None
    if not website_url.startswith(("http://", "https://")):
        website_url = "https://" + website_url
    try:
        resp = requests.get(
            website_url,
            headers=config.REQUEST_HEADERS,
            timeout=6,
            allow_redirects=True,
        )
        soup = BeautifulSoup(resp.text, "html.parser")

        # og:image
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            return og["content"]

        # apple-touch-icon
        icon = soup.find("link", rel=lambda r: r and "apple-touch-icon" in r)
        if icon and icon.get("href"):
            href = icon["href"]
            if href.startswith("http"):
                return href

    except Exception:
        pass
    return None


# ─── HTML renderer ───────────────────────────────────────────────────────────────

def _problem_card(p: dict, index: int) -> str:
    return f"""
    <div class="finding">
      <div class="finding-header">
        <span class="finding-num">{index}</span>
        <h3 class="finding-title">{p['title']}</h3>
      </div>
      <div class="finding-body">
        <p class="finding-label">What we found</p>
        <p class="finding-text">{p['found']}</p>
        <p class="finding-label">What it costs you</p>
        <p class="finding-text">{p['cost']}</p>
        <div class="fixable">
          <p class="fixable-heading">This is fixable. Here's how we do it.</p>
          <p class="fixable-text">{p['fix']}</p>
        </div>
      </div>
    </div>"""


def render_html(
    salon_name: str,
    problems: List[dict],
    audit_date: str,
    logo_url: Optional[str] = None,
) -> str:
    """Renders the full HTML audit page for one prospect."""

    problems_html = ""
    if problems:
        for i, p in enumerate(problems, 1):
            problems_html += _problem_card(p, i)
        intro_text = (
            f"We found <strong>{len(problems)} thing{'s' if len(problems) != 1 else ''}</strong> "
            f"on your digital setup that are likely costing you bookings every week."
        )
    else:
        problems_html = """
    <div class="finding positive">
      <div class="finding-header">
        <span class="finding-num" style="background:#16a34a">✓</span>
        <h3 class="finding-title">Your digital presence looks solid</h3>
      </div>
      <div class="finding-body">
        <p class="finding-text">
          We didn't find obvious gaps in your online setup. That said, most salons still
          have room to improve how they handle lapsed clients and after-hours bookings.
          Happy to show you what that looks like on the call.
        </p>
      </div>
    </div>"""
        intro_text = "Here is what we found when we looked at your business online."

    logo_html = ""
    if logo_url:
        logo_html = f'<img src="{logo_url}" alt="{salon_name} logo" class="salon-logo" onerror="this.style.display=\'none\'">'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Audit Report — {salon_name}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      background: #f8f7f5;
      color: #1a1a1a;
      line-height: 1.65;
    }}

    /* ── Header ──────────────────────────────────────────────────────── */
    .site-header {{
      background: #0f172a;
      padding: 18px 24px;
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .site-header .brand {{
      font-size: 0.95rem;
      font-weight: 700;
      letter-spacing: -0.01em;
      color: #fff;
    }}
    .site-header .brand span {{ color: #818cf8; }}
    .header-divider {{
      width: 1px;
      height: 18px;
      background: #334155;
    }}
    .report-label {{
      font-size: 0.78rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #94a3b8;
    }}

    /* ── Hero ────────────────────────────────────────────────────────── */
    .hero {{
      background: #0f172a;
      padding: 48px 24px 56px;
      text-align: center;
    }}
    .salon-logo {{
      max-height: 64px;
      max-width: 200px;
      margin-bottom: 20px;
      border-radius: 8px;
      display: block;
      margin-left: auto;
      margin-right: auto;
    }}
    .salon-initial {{
      width: 64px;
      height: 64px;
      background: #1e293b;
      border: 2px solid #334155;
      border-radius: 12px;
      font-size: 1.8rem;
      font-weight: 800;
      color: #818cf8;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 20px;
    }}
    .hero-tag {{
      display: inline-block;
      background: #1e293b;
      color: #818cf8;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      padding: 4px 14px;
      border-radius: 100px;
      margin-bottom: 16px;
    }}
    .hero h1 {{
      font-size: clamp(1.6rem, 5vw, 2.2rem);
      font-weight: 800;
      letter-spacing: -0.03em;
      line-height: 1.2;
      color: #fff;
      margin-bottom: 12px;
    }}
    .hero h1 em {{
      font-style: normal;
      color: #818cf8;
    }}
    .hero-meta {{
      font-size: 0.85rem;
      color: #64748b;
      margin-top: 12px;
    }}

    /* ── Main content ────────────────────────────────────────────────── */
    .main {{
      max-width: 720px;
      margin: 0 auto;
      padding: 48px 24px;
    }}

    .intro {{
      font-size: 1.05rem;
      color: #444;
      margin-bottom: 36px;
      padding-bottom: 36px;
      border-bottom: 1px solid #e5e5e5;
    }}

    /* ── Finding cards ───────────────────────────────────────────────── */
    .finding {{
      background: #fff;
      border: 1px solid #e5e5e5;
      border-radius: 16px;
      margin-bottom: 20px;
      overflow: hidden;
    }}
    .finding.positive .finding-header {{ background: #f0fdf4; }}

    .finding-header {{
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 20px 24px;
      background: #fef9ec;
      border-bottom: 1px solid #e5e5e5;
    }}
    .finding-num {{
      flex-shrink: 0;
      width: 30px;
      height: 30px;
      background: #f59e0b;
      color: #fff;
      font-weight: 800;
      font-size: 0.85rem;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .finding-title {{
      font-size: 1rem;
      font-weight: 700;
      color: #111;
    }}
    .finding-body {{
      padding: 24px;
    }}
    .finding-label {{
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #888;
      margin-bottom: 4px;
      margin-top: 16px;
    }}
    .finding-label:first-child {{ margin-top: 0; }}
    .finding-text {{
      font-size: 0.95rem;
      color: #333;
    }}
    .fixable {{
      background: #f0f9ff;
      border: 1px solid #bae6fd;
      border-radius: 10px;
      padding: 16px 18px;
      margin-top: 20px;
    }}
    .fixable-heading {{
      font-size: 0.9rem;
      font-weight: 700;
      color: #0369a1;
      margin-bottom: 6px;
    }}
    .fixable-text {{
      font-size: 0.9rem;
      color: #0c4a6e;
    }}

    /* ── CTA section ─────────────────────────────────────────────────── */
    .cta-section {{
      margin-top: 48px;
      padding-top: 40px;
      border-top: 1px solid #e5e5e5;
      text-align: center;
    }}
    .cta-section h2 {{
      font-size: clamp(1.4rem, 4vw, 1.8rem);
      font-weight: 800;
      letter-spacing: -0.02em;
      color: #111;
      margin-bottom: 12px;
    }}
    .cta-section p {{
      font-size: 1rem;
      color: #555;
      max-width: 500px;
      margin: 0 auto 32px;
    }}
    .calendly-wrapper {{
      background: #fff;
      border: 1px solid #e5e5e5;
      border-radius: 16px;
      overflow: hidden;
    }}
    .calendly-inline-widget {{
      min-width: 320px;
      height: 700px;
    }}

    /* ── Footer ──────────────────────────────────────────────────────── */
    footer {{
      text-align: center;
      padding: 32px 24px;
      font-size: 0.82rem;
      color: #aaa;
      border-top: 1px solid #ebebeb;
    }}
    footer a {{ color: #4f46e5; text-decoration: none; }}
  </style>
</head>
<body>

<header class="site-header">
  <div class="brand">Auralith<span>Digital</span></div>
  <div class="header-divider"></div>
  <div class="report-label">Grooming Salon Audit</div>
</header>

<div class="hero">
  {logo_html if logo_url else f'<div class="salon-initial">{salon_name[0].upper()}</div>'}
  <div class="hero-tag">Prepared for {salon_name}</div>
  <h1>Here's what we found on<br><em>{salon_name}'s</em> digital presence</h1>
  <div class="hero-meta">Audit date: {audit_date}</div>
</div>

<main class="main">

  <p class="intro">{intro_text}</p>

  {problems_html}

  <div class="cta-section">
    <h2>If any of this looks familiar, let's talk.</h2>
    <p>
      This call is free and takes 20 minutes. I'll walk you through exactly what I found
      and show you what fixing it would look like for your salon specifically. No pitch.
    </p>
    <div class="calendly-wrapper">
      <div
        class="calendly-inline-widget"
        data-url="{CALENDLY}"
      ></div>
    </div>
  </div>

</main>

<footer>
  <p>Prepared by <a href="mailto:auralithdigital@gmail.com">Pyetra at Auralith Digital</a></p>
  <p style="margin-top:4px">Business automation for pet grooming salons in South Florida</p>
</footer>

<script src="https://assets.calendly.com/assets/external/widget.js" async></script>
</body>
</html>"""


# ─── Main generator ──────────────────────────────────────────────────────────────

def generate_for_prospect(record: dict, dry_run: bool = False) -> Optional[str]:
    """
    Generates the audit page for one prospect record.
    Returns the output file path (or None on skip).
    """
    fields = record.get("fields", {})
    record_id = record["id"]
    name = fields.get("Business Name", "")
    audit_notes = fields.get("Audit Notes", "")
    website = fields.get("Website", "")
    audit_date = date.today().isoformat()

    if not name:
        log.warning(f"Skipping record {record_id}: no business name")
        return None

    if not audit_notes:
        log.info(f"Skipping {name}: no audit notes yet (run audit.py first)")
        return None

    slug = slugify(name)
    filename = f"{slug}.html"
    filepath = os.path.join(AUDITS_DIR, filename)

    # Parse audit notes into problems
    findings = parse_audit_notes(audit_notes)
    problems = findings_to_problems(findings)

    log.info(f"{name}: {len(problems)} problem(s) found")
    for p in problems:
        log.info(f"  - {p['title']}")

    if dry_run:
        print(f"\n[DRY RUN] {name}")
        print(f"  File would be: audits/{filename}")
        print(f"  Problems ({len(problems)}):")
        for p in problems:
            print(f"    • {p['title']}")
        return filepath

    # Try to get logo
    logo_url = try_get_logo(website)
    if logo_url:
        log.info(f"  Logo found: {logo_url[:60]}...")

    # Render HTML
    html = render_html(name, problems, audit_date, logo_url)

    # Write file
    os.makedirs(AUDITS_DIR, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    log.info(f"  Saved: {filepath}")

    # Write path back to Airtable
    airtable_client.update_record(record_id, {"Audit Page URL": filepath})

    return filepath


def run(regenerate_all: bool = False, dry_run: bool = False) -> List[str]:
    """
    Generates audit pages for prospects.
    By default, skips prospects that already have an Audit Page URL.
    Pass regenerate_all=True to rebuild all pages.
    """
    all_records = airtable_client.get_all_records()

    if regenerate_all:
        to_process = [r for r in all_records if r["fields"].get("Audit Notes")]
    else:
        to_process = [
            r for r in all_records
            if r["fields"].get("Audit Notes")
            and not r["fields"].get("Audit Page URL")
        ]

    if not to_process:
        log.info("No prospects need audit pages generated.")
        return []

    log.info(f"Generating audit pages for {len(to_process)} prospect(s)...")
    generated = []

    for record in to_process:
        path = generate_for_prospect(record, dry_run=dry_run)
        if path:
            generated.append(path)
        time.sleep(0.3)

    return generated


# ─── Standalone entry ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    parser = argparse.ArgumentParser(
        description="Generate per-prospect HTML audit pages"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Regenerate all audit pages, even if they already exist",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing files or updating Airtable",
    )
    args = parser.parse_args()

    pages = run(regenerate_all=args.all, dry_run=args.dry_run)

    if not args.dry_run:
        print(f"\n{'='*50}")
        print(f"Generated {len(pages)} audit page(s):")
        for p in pages:
            print(f"  {p}")
        if pages:
            print(f"\nNext step: host the audits/ folder on Netlify Drop or GitHub Pages,")
            print(f"then update the Audit Page URL fields in Airtable to the public URLs.")
