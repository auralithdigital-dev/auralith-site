"""
Google Maps Places API scraper for Auralith Prospect Machine.

Finds up to 10 new pet grooming salons per day across Broward and Palm Beach
Counties, deduplicates against Airtable, and returns structured prospect dicts.

Run standalone to preview results (does NOT write to Airtable):
    python scraper.py
"""

import os
import sys
import time
import logging
from typing import List, Optional, Set
import requests
from dotenv import load_dotenv

import config
import airtable_client

load_dotenv()
log = logging.getLogger(__name__)

GMAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

# Fields requested from Place Details API
DETAIL_FIELDS = "name,formatted_address,formatted_phone_number,website,place_id"


def search_places(query: str, existing_ids: set, page_token: str = None) -> dict:
    """
    Calls the Google Maps Text Search API.
    Returns the raw API response dict.
    """
    params = {"query": query, "key": GMAPS_API_KEY}
    if page_token:
        params["pagetoken"] = page_token

    resp = requests.get(TEXT_SEARCH_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_place_details(place_id: str) -> dict:
    """
    Fetches detailed information for a single Place ID.
    Returns fields: name, address, phone, website, place_id.
    """
    params = {
        "place_id": place_id,
        "fields": DETAIL_FIELDS,
        "key": GMAPS_API_KEY,
    }
    resp = requests.get(PLACE_DETAILS_URL, params=params, timeout=10)
    resp.raise_for_status()
    result = resp.json().get("result", {})

    return {
        "place_id": result.get("place_id", place_id),
        "name": result.get("name", ""),
        "address": result.get("formatted_address", ""),
        "phone": result.get("formatted_phone_number", ""),
        "website": result.get("website", ""),
    }


def find_new_prospects(existing_ids: Optional[Set] = None, dry_run: bool = False) -> List[dict]:
    """
    Searches Google Maps for pet grooming salons in Broward and Palm Beach
    Counties, filters out already-scraped places, and returns up to
    PROSPECTS_PER_DAY new prospect dicts.

    Each prospect dict:
        {place_id, name, address, phone, website, county}
    """
    if not GMAPS_API_KEY:
        log.error("GOOGLE_MAPS_API_KEY not set in .env")
        sys.exit(1)

    if existing_ids is None:
        log.info("Loading existing Place IDs from Airtable...")
        existing_ids = airtable_client.get_existing_place_ids()
        log.info(f"Found {len(existing_ids)} existing prospects in Airtable")

    prospects = []
    target = config.PROSPECTS_PER_DAY
    seen_this_run = set(existing_ids)  # avoid intra-run dupes too

    for query, county in config.SEARCH_QUERIES:
        if len(prospects) >= target:
            break

        log.info(f"Searching: {query}")
        page_token = None
        page = 0

        while len(prospects) < target:
            # Google requires a short delay before using a next_page_token
            if page_token and page > 0:
                time.sleep(2)

            try:
                data = search_places(query, seen_this_run, page_token)
            except requests.RequestException as e:
                log.warning(f"Search request failed: {e}")
                break

            status = data.get("status")
            if status not in ("OK", "ZERO_RESULTS"):
                log.warning(f"Unexpected API status '{status}' for query: {query}")
                break

            results = data.get("results", [])
            for place in results:
                if len(prospects) >= target:
                    break
                pid = place.get("place_id")
                if not pid or pid in seen_this_run:
                    continue

                # Fetch full details
                time.sleep(config.GMAPS_DELAY)
                try:
                    details = get_place_details(pid)
                except requests.RequestException as e:
                    log.warning(f"Details fetch failed for {pid}: {e}")
                    continue

                details["county"] = county
                prospects.append(details)
                seen_this_run.add(pid)
                log.info(f"  + {details['name']} ({county})")

            page_token = data.get("next_page_token")
            page += 1
            if not page_token:
                break  # no more pages for this query

        time.sleep(config.GMAPS_DELAY)

    log.info(f"Found {len(prospects)} new prospects")
    return prospects


# ─── Standalone test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("Running scraper in preview mode (not writing to Airtable)...\n")
    prospects = find_new_prospects(existing_ids=set(), dry_run=True)

    print(f"\n{'─'*60}")
    print(f"Found {len(prospects)} prospects:")
    print(f"{'─'*60}")
    for i, p in enumerate(prospects, 1):
        print(f"\n{i}. {p['name']} ({p['county']})")
        print(f"   Address : {p['address']}")
        print(f"   Phone   : {p['phone'] or 'N/A'}")
        print(f"   Website : {p['website'] or 'N/A'}")
        print(f"   Place ID: {p['place_id']}")
