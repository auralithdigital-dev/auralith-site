"""
Auralith Prospect Machine — Daily Orchestrator

Runs all pipeline steps in sequence every morning:
  1. Check for replies via Gmail IMAP → update Airtable
  2. Scrape 10 new prospects from Google Maps → add to Airtable
  3. Write + send Email 1 to each new prospect → mark sent in Airtable
  4. Send Email 2 (follow-up) to eligible prospects → update Airtable
  5. Generate call scripts for call-ready prospects → flag in Airtable
  6. Send daily summary email

Usage:
    python main.py             # Full run (live)
    python main.py --dry-run   # Preview all actions, no emails sent, no Airtable changes
    python main.py --step 2    # Run only step 2 (scraper)
"""

import sys
import os
import shutil
import time
import logging
import argparse
from datetime import date

from typing import List
from dotenv import load_dotenv

load_dotenv()

# Configure logging before importing modules that use it
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

import config
import airtable_client
import scraper
import website_scraper
import email_writer
import email_sender
import follow_up
import call_prep
import dm_prep
import audit
import generate_audit_page
import daily_summary


def step1_check_replies(dry_run: bool = False):
    """Check Gmail IMAP for replies from prospects. Update Airtable."""
    log.info("═" * 50)
    log.info("STEP 1: Checking for replies via Gmail IMAP")

    prospect_email_map = airtable_client.get_all_prospect_emails()
    if not prospect_email_map:
        log.info("No prospects with emails yet, skipping reply check")
        return

    replied = email_sender.check_for_replies(set(prospect_email_map.keys()))
    if not replied:
        log.info("No new replies found")
        return

    for email_addr in replied:
        record_id = prospect_email_map.get(email_addr)
        if not record_id:
            continue
        if dry_run:
            log.info(f"[DRY RUN] Would mark reply from {email_addr}")
        else:
            airtable_client.update_record(record_id, {
                "Reply Received": True,
                "Status": "Call Scheduled",
            })
            log.info(f"Marked reply from {email_addr}")


def step2_scrape_prospects(dry_run: bool = False) -> List[dict]:
    """Find 10 new pet grooming salons from Google Maps."""
    log.info("═" * 50)
    log.info("STEP 2: Scraping new prospects from Google Maps")

    existing_ids = airtable_client.get_existing_place_ids()
    prospects = scraper.find_new_prospects(existing_ids=existing_ids)

    if not prospects:
        log.info("No new prospects found today")
        return []

    for p in prospects:
        if dry_run:
            log.info(f"[DRY RUN] Would add: {p['name']} ({p['county']})")
        else:
            record_id = airtable_client.add_record({
                "Business Name": p["name"],
                "Address": p["address"],
                "Phone": p["phone"],
                "Website": p["website"],
                "County": p["county"],
                "Place ID": p["place_id"],
                "Status": "New",
            })
            p["record_id"] = record_id
            log.info(f"Added: {p['name']} (record {record_id})")

    log.info(f"Step 2 complete: {len(prospects)} prospects {'found (dry run)' if dry_run else 'added'}")
    return prospects


def step2b_audit_prospects(dry_run: bool = False):
    """Run pre-email audit for all new unaudited prospects."""
    log.info("═" * 50)
    log.info("STEP 2b: Auditing new prospects")
    results = audit.run_audit_for_new_prospects(dry_run=dry_run)
    log.info(f"Step 2b complete: {len(results)} prospect(s) audited")


def step2c_generate_audit_pages(dry_run: bool = False) -> List[str]:
    """Generate per-prospect HTML audit pages for newly audited prospects."""
    log.info("═" * 50)
    log.info("STEP 2c: Generating audit pages")
    pages = generate_audit_page.run(dry_run=dry_run)
    log.info(f"Step 2c complete: {len(pages)} audit page(s) generated")
    return pages


def step2d_publish_audit_pages(local_paths: List[str], dry_run: bool = False):
    """
    Copy newly generated audit pages from audits/ to docs/audits/ and
    update each Airtable record's Audit Page URL to the live public URL.
    Runs immediately after step 2c so emails always embed a working link.
    """
    if not local_paths:
        return

    log.info("═" * 50)
    log.info(f"STEP 2d: Publishing {len(local_paths)} audit page(s) to docs/audits/")

    docs_dir = os.path.join(os.path.dirname(__file__), config.DOCS_AUDITS_DIR)
    os.makedirs(docs_dir, exist_ok=True)

    all_records = airtable_client.get_all_records()
    # Build a slug → record_id map for fast lookup
    record_map = {}
    for r in all_records:
        url = r["fields"].get("Audit Page URL", "")
        if url:
            record_map[os.path.basename(url)] = r["id"]

    published = 0
    for local_path in local_paths:
        filename = os.path.basename(local_path)
        dest = os.path.join(docs_dir, filename)
        public_url = f"{config.AUDIT_BASE_URL}/{filename}"

        if dry_run:
            log.info(f"[DRY RUN] Would copy {filename} → docs/audits/ and set URL to {public_url}")
            continue

        shutil.copy2(local_path, dest)
        record_id = record_map.get(filename)
        if record_id:
            airtable_client.update_record(record_id, {"Audit Page URL": public_url})
        log.info(f"  Published: {filename} → {public_url}")
        published += 1

    if not dry_run:
        log.info(f"Step 2d complete: {published} page(s) published")


def step3_queue_email1(prospects: List[dict], dry_run: bool = False):
    """
    For each new prospect: scrape website, write Email 1 from the fixed template,
    and save to Airtable as 'Pending Review'.

    Requires audit notes (step 2b) and audit page URL (step 2c) to already be set.
    If the audit page URL is not a public HTTP URL, the email body will contain
    [AUDIT PAGE URL] as a placeholder — Pyetra must replace it before approving.

    Run send_approved.py to send approved emails.
    """
    log.info("═" * 50)
    log.info(f"STEP 3: Writing + queuing Email 1 for {len(prospects)} new prospect(s)")

    for p in prospects:
        name = p.get("name", "")
        website = p.get("website", "")
        record_id = p.get("record_id")

        # Scrape website for email address, Instagram handle, and content summary
        if website:
            site_data = website_scraper.scrape_website(website)
        else:
            site_data = {"email": None, "instagram": None, "content_summary": ""}

        prospect_email = site_data.get("email")
        instagram = site_data.get("instagram")
        content_summary = site_data.get("content_summary", "")

        if not prospect_email:
            log.info(f"No email found for {name} — cannot queue Email 1")
            continue

        # Fetch full Airtable record to get audit notes, audit page URL, contact name
        audit_notes = ""
        audit_page_url = ""
        contact_name = ""

        if record_id:
            try:
                recs = airtable_client.get_all_records(
                    filter_formula=f"RECORD_ID()='{record_id}'"
                )
                if recs:
                    fields = recs[0]["fields"]
                    audit_notes = fields.get("Audit Notes", "")
                    audit_page_url = fields.get("Audit Page URL", "")
                    contact_name = fields.get("Contact Name", "")
            except Exception:
                pass

        # Write Email 1 from the fixed template
        composed = email_writer.write_cold_email(
            name,
            audit_notes=audit_notes,
            audit_page_url=audit_page_url,
            website_content=content_summary,
            recipient_email=prospect_email,
        )

        if dry_run:
            log.info(f"[DRY RUN] Would queue Email 1 for {name} <{prospect_email}>")
            log.info(f"  Subject  : {composed['subject']}")
            log.info(f"  Owner    : {composed['owner_name'] or '(none found)'}")
            log.info(f"  Preview  : {composed['body'][:150]}...")
            if instagram:
                log.info(f"  Instagram: @{instagram}")
            continue

        # Build Airtable update
        update_fields = {
            "Email": prospect_email,
            "Email 1 Subject": composed["subject"],
            "Email 1 Body": composed["body"],
            "Email 1 Status": "Pending Review",
            "Subject Line Options": composed["subject_options"],
        }
        # Store extracted owner name if not already set
        if composed.get("owner_name") and not contact_name:
            update_fields["Contact Name"] = composed["owner_name"]
        if instagram:
            update_fields["Instagram Handle"] = instagram

        if record_id:
            airtable_client.update_record(record_id, update_fields)
            log.info(f"Queued for review: {name} → {prospect_email}")

        time.sleep(0.5)  # brief pause between Airtable writes


def step4_queue_followups(dry_run: bool = False):
    """Queue Email 2 (follow-up) for prospects who haven't replied after 3 days."""
    log.info("═" * 50)
    log.info("STEP 4: Queuing follow-up emails (Email 2) for review")
    results = follow_up.queue_followups(dry_run=dry_run)
    log.info(f"Step 4 complete: {len(results)} follow-up(s) queued for review")


def step5_dm_prep(dry_run: bool = False):
    """Create Instagram DM tasks for prospects 3 days after Email 1 was sent."""
    log.info("═" * 50)
    log.info("STEP 5: Creating Instagram DM tasks")
    results = dm_prep.run_dm_prep(dry_run=dry_run)
    log.info(f"Step 5 complete: {len(results)} DM task(s) created")


def step6_call_prep(dry_run: bool = False):
    """Flag prospects as Call Ready 5 days after DM task was created."""
    log.info("═" * 50)
    log.info("STEP 6: Generating call scripts for call-ready prospects")
    results = call_prep.run_call_prep(dry_run=dry_run)
    log.info(f"Step 6 complete: {len(results)} prospect(s) flagged as Call Ready")


def step7_daily_summary(dry_run: bool = False):
    """Send the daily summary email to support@auralithdigital.com."""
    log.info("═" * 50)
    log.info("STEP 7: Sending daily summary")
    if dry_run:
        data = airtable_client.get_todays_summary_data()
        body = daily_summary.build_summary_text(data)
        log.info("[DRY RUN] Summary that would be sent:\n\n" + body)
    else:
        daily_summary.send_daily_summary()


def run_all(dry_run: bool = False):
    log.info("=" * 50)
    log.info(f"Auralith Prospect Machine starting {'[DRY RUN]' if dry_run else '[LIVE]'}")
    log.info("=" * 50)

    step1_check_replies(dry_run)
    prospects = step2_scrape_prospects(dry_run)
    step2b_audit_prospects(dry_run)
    pages = step2c_generate_audit_pages(dry_run)
    step2d_publish_audit_pages(pages, dry_run)
    if prospects:
        step3_queue_email1(prospects, dry_run)
    step4_queue_followups(dry_run)
    step5_dm_prep(dry_run)
    step6_call_prep(dry_run)
    step7_daily_summary(dry_run)

    log.info("=" * 50)
    log.info("All steps complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auralith Prospect Machine")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview all actions without sending emails or modifying Airtable"
    )
    parser.add_argument(
        "--step", type=int, choices=[1, 2, 3, 4, 5, 6, 7],
        help="Run only a specific step (1–7)"
    )
    args = parser.parse_args()

    step_map = {
        1: lambda: step1_check_replies(args.dry_run),
        2: lambda: step2_scrape_prospects(args.dry_run),
        4: lambda: step4_queue_followups(args.dry_run),
        5: lambda: step5_dm_prep(args.dry_run),
        6: lambda: step6_call_prep(args.dry_run),
        7: lambda: step7_daily_summary(args.dry_run),
    }

    if args.step:
        if args.step == 3:
            log.info("Step 3 requires prospects from Step 2. Run steps 2+3 together by omitting --step.")
        elif args.step in step_map:
            step_map[args.step]()
        else:
            log.error(f"Step {args.step} not supported standalone")
    else:
        run_all(dry_run=args.dry_run)
