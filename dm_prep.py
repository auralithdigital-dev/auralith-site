"""
Instagram DM task creator for Auralith Prospect Machine.

On day 3 after Email 1 is sent, this script:
- Looks up the prospect's Instagram handle (scraped from website, or already stored)
- Generates a casual 2–3 sentence DM using Claude
- Saves the DM text and Instagram handle to Airtable with status 'DM Ready'

You send the DM manually from your Instagram account.
Mark it as 'DM Sent' in Airtable when done.

Run standalone (dry-run):
    python3 dm_prep.py --dry-run
"""

import logging
import argparse
from typing import List
from datetime import date, timedelta

import config
import airtable_client
import website_scraper
import email_writer

log = logging.getLogger(__name__)


def run_dm_prep(dry_run: bool = False) -> List[str]:
    """
    Creates DM tasks for eligible prospects.
    Returns list of business names that got a DM task.
    """
    cutoff = (date.today() - timedelta(days=config.DM_PREP_DAYS)).isoformat()
    candidates = airtable_client.get_records_needing_dm_prep(cutoff)

    if not candidates:
        log.info("DM prep: no candidates today")
        return []

    log.info(f"DM prep: {len(candidates)} candidate(s) found (Email 1 sent before {cutoff})")
    prepped = []

    for record in candidates:
        fields = record.get("fields", {})
        record_id = record["id"]
        name = fields.get("Business Name", "")
        website = fields.get("Website", "")
        content_summary = ""

        # Try to get Instagram handle — may already be stored from initial scrape
        instagram = fields.get("Instagram Handle", "")

        if not instagram and website:
            log.info(f"Scraping Instagram handle for {name}...")
            site_data = website_scraper.scrape_website(website)
            instagram = site_data.get("instagram", "")
            content_summary = site_data.get("content_summary", "")

        # Get owner name (stored from Email 1 step)
        owner_name = fields.get("Contact Name", "")

        # Generate DM from fixed template
        dm_text = email_writer.write_dm(name, owner_name=owner_name, instagram_handle=instagram)

        if dry_run:
            handle_display = f"@{instagram}" if instagram else "(no handle found)"
            print(f"\n[DRY RUN] DM task for {name}")
            print(f"  Instagram: {handle_display}")
            print(f"  DM text  : {dm_text}")
            prepped.append(name)
            continue

        today = date.today().isoformat()
        update_fields = {
            "DM Text": dm_text,
            "DM Status": "DM Ready",
            "DM Date": today,
        }
        if instagram:
            update_fields["Instagram Handle"] = instagram

        airtable_client.update_record(record_id, update_fields)
        prepped.append(name)

        handle_display = f"@{instagram}" if instagram else "(no handle found)"
        log.info(f"DM task created: {name} — {handle_display}")

    return prepped


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without updating Airtable")
    args = parser.parse_args()

    results = run_dm_prep(dry_run=args.dry_run)
    print(f"\nDM tasks created: {len(results)}")
    for name in results:
        print(f"  - {name}")
