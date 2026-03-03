"""
Central configuration for Auralith Prospect Machine.
Edit constants here — no need to touch individual modules.
"""

# ─── Scraper ────────────────────────────────────────────────────────────────────
PROSPECTS_PER_DAY = 10

# Alternating search queries ensure broad coverage across both counties.
# The scraper cycles through these, stopping once 10 new prospects are found.
SEARCH_QUERIES = [
    ("pet grooming salon Broward County Florida", "Broward"),
    ("pet grooming salon Palm Beach County Florida", "Palm Beach"),
    ("dog groomer Broward County Florida", "Broward"),
    ("dog groomer Palm Beach County Florida", "Palm Beach"),
    ("cat groomer Broward County Florida", "Broward"),
    ("cat groomer Palm Beach County Florida", "Palm Beach"),
    ("mobile pet grooming Broward County Florida", "Broward"),
    ("mobile pet grooming Palm Beach County Florida", "Palm Beach"),
    ("pet spa Broward County Florida", "Broward"),
    ("pet spa Palm Beach County Florida", "Palm Beach"),
]

# ─── Timing ─────────────────────────────────────────────────────────────────────
FOLLOW_UP_DAYS = 3   # Days after Email 1 sent before queuing Email 2
DM_PREP_DAYS   = 3   # Days after Email 1 sent before creating Instagram DM task
CALL_PREP_DAYS = 5   # Days after DM Date before flagging as Call Ready

# ─── Audit pages ────────────────────────────────────────────────────────────────
AUDIT_BASE_URL  = "https://reports.auralithdigital.com/audits"
DOCS_AUDITS_DIR = "docs/audits"   # relative to project root; served via GitHub Pages

# ─── Offer & links ──────────────────────────────────────────────────────────────
CALENDLY_URL = "https://calendly.com/auralithdigital/grooming-automation"
OFFER = "free 20-minute audit call"

# ─── Airtable ───────────────────────────────────────────────────────────────────
AIRTABLE_BASE_NAME = "Auralith Pipeline"
AIRTABLE_TABLE_NAME = "Prospects"

# ─── HTTP Request settings ──────────────────────────────────────────────────────
REQUEST_TIMEOUT = 10       # seconds for website scraping requests
GMAPS_DELAY = 1.0          # seconds between Google Maps API calls
EMAIL_SEND_DELAY = 2.0     # seconds between outbound emails

# User-agent for website scraping (polite, identifiable)
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AuralithBot/1.0; "
        "+https://auralithdigital.com)"
    )
}
