"""
Call prep generator for Auralith Prospect Machine.

On day 5 after the DM task was created, this script:
- Generates a personalized 4-line call script using Claude
- Flags the prospect as 'Call Ready' in Airtable
- Stores the script in the 'Call Script' field

You make the call manually. Mark 'Call Done' in Airtable when done.

Run standalone (dry-run):
    python3 call_prep.py --dry-run
"""

import logging
import argparse
from typing import List
from datetime import date, timedelta

import config
import airtable_client
import email_writer

log = logging.getLogger(__name__)


def run_call_prep(dry_run: bool = False) -> List[str]:
    """
    Flags prospects as Call Ready and generates call scripts.
    Returns list of business names flagged.
    """
    cutoff = (date.today() - timedelta(days=config.CALL_PREP_DAYS)).isoformat()
    candidates = airtable_client.get_records_needing_call_prep(cutoff)

    if not candidates:
        log.info("Call prep: no candidates today")
        return []

    log.info(f"Call prep: {len(candidates)} candidate(s) found (DM created before {cutoff})")
    flagged = []

    for record in candidates:
        fields = record.get("fields", {})
        record_id = record["id"]
        name = fields.get("Business Name", "this business")
        owner_name = fields.get("Contact Name", "")
        audit_notes = fields.get("Audit Notes", "")

        script = email_writer.write_call_script(name, owner_name=owner_name, audit_notes=audit_notes)

        if dry_run:
            print(f"\n[DRY RUN] Would flag {name} as Call Ready")
            print(f"Call script:\n{script}\n")
            flagged.append(name)
            continue

        airtable_client.update_record(record_id, {
            "Call Script": script,
            "Status": "Call Ready",
        })
        flagged.append(name)
        log.info(f"Call script added + flagged Call Ready: {name}")

    return flagged


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without updating Airtable")
    args = parser.parse_args()

    results = run_call_prep(dry_run=args.dry_run)
    print(f"\nProspects flagged as Call Ready: {len(results)}")
    for name in results:
        print(f"  - {name}")
