# Auralith Prospect Machine — Project Status

**Last updated:** 2026-02-28
**Owner:** Pyetra / Auralith Digital
**Working directory:** `/Users/pyetratoscano/auralith-prospect-machine/`

---

## Overview

Automated outreach pipeline targeting pet grooming salons in Broward and Palm Beach Counties, FL. Runs Monday–Friday via macOS cron at 8am. All scripts are Python 3.9. Nothing sends without Pyetra manually approving in Airtable first.

---

## Credentials & Config

`.env` (never committed):

| Variable | Value |
|----------|-------|
| `GOOGLE_MAPS_API_KEY` | live |
| `AIRTABLE_API_KEY` | live (`patP5Ek0V0foEuKdG...`) |
| `AIRTABLE_BASE_ID` | `app3n2A2hC7xQsmZT` ("Auralith Pipeline") |
| `ANTHROPIC_API_KEY` | live |
| `GMAIL_ADDRESS` | auralithdigital@gmail.com |
| `GMAIL_APP_PASSWORD` | live |
| `SUMMARY_EMAIL` | support@auralithdigital.com |

`config.py` constants:

```
PROSPECTS_PER_DAY = 10
FOLLOW_UP_DAYS    = 3
DM_PREP_DAYS      = 3
CALL_PREP_DAYS    = 5
CALENDLY_URL      = https://calendly.com/auralithdigital/grooming-automation
AIRTABLE_TABLE_NAME = "Prospects"
```

---

## Airtable Base

**Base:** "Auralith Pipeline" (`app3n2A2hC7xQsmZT`) — table: "Prospects" — 31 fields:

```
Business Name, Address, Phone, Email, Website, County, Status,
Last Contact Date, Notes, Place ID,
Email 1 Sent, Email 1 Sent Date, Email 1 Subject, Email 1 Body,
Email 1 Status  (Pending Review / Approved / Sent / Rejected)
Subject Line Options  (5 comma-separated subject lines — Pyetra picks one)
Email 2 Sent, Email 2 Sent Date, Email 2 Subject, Email 2 Body,
Email 2 Status  (same options as Email 1 Status)
Instagram Handle, DM Text, DM Status (DM Ready / DM Sent), DM Date,
Call Script, Call Done, Reply Received,
Audit Notes, Audit Page URL, Contact Name
```

**Current data:** 20 prospects (10 Broward + 10 Palm Beach), all audited, 8 emails queued as "Pending Review" using the current fixed-template format.

---

## Daily Pipeline — `main.py`

```
python3 main.py            # live run
python3 main.py --dry-run  # preview, no sends or Airtable writes
python3 main.py --step N   # run one step only (1–7)
```

| Step | What it does |
|------|-------------|
| 1 | Check Gmail IMAP for replies → mark Reply Received in Airtable |
| 2 | Scrape 10 new prospects from Google Maps → add to Airtable |
| 2b | Audit each new prospect (website, Google reviews, Instagram) → save Audit Notes |
| 2c | Generate HTML audit page for each audited prospect → save to `docs/audits/[slug].html`, write URL to Airtable |
| 3 | Write Email 1 from fixed template → queue as Pending Review |
| 4 | Queue Email 2 (follow-up) for prospects 3+ days after Email 1, no reply |
| 5 | Create Instagram DM tasks for prospects 3+ days after Email 1 |
| 6 | Generate call scripts for prospects 5+ days after DM created |
| 7 | Send daily summary email to support@auralithdigital.com |

---

## All Scripts

### `main.py`
Daily orchestrator. Runs all 7 steps in sequence. Supports `--dry-run` and `--step N`.

### `config.py`
All constants: timing thresholds, search queries, Calendly URL, table name.

### `airtable_client.py`
Airtable REST wrapper. All CRUD, filters, and summary data queries.
Run `python3 airtable_client.py --setup --workspace-id wspXXX` to recreate the base from scratch.

### `scraper.py`
Google Maps Text Search + Place Details API. Deduplicates by Place ID. Returns up to 10 new prospects per run.

### `website_scraper.py`
Fetches homepage + `/contact` page. Extracts email address, Instagram handle (regex on `instagram.com/HANDLE`), and ~500-char content summary.

### `audit.py`
Pre-email intelligence for each new prospect:
- Detects online booking platform (Vagaro, MoeGo, PetDesk, Booksy, StyleSeat, GlossGenius, Square, Acuity, Calendly, Boulevard)
- Scans Google reviews for pain-point keywords (missed call, hard to reach, didn't respond, etc.)
- Checks for contact form and chat widget (Intercom, Drift, Tidio, Tawk, Zendesk, LiveChat, HubSpot)
- Checks Instagram profile reachability via meta tags

Saves structured "Audit Notes" to Airtable field. Run standalone: `python3 audit.py --dry-run`

### `email_writer.py`
All templates are fixed — no AI-generated body copy. Claude (Haiku, max 15 tokens) is used only to extract the owner's first name from website content. If no name found, greeting line is omitted entirely — no "Hi team", no fallback. Audit findings are rewritten as direct declarative statements ("There is no online booking on your site", not "It looks like there might not be a booking form"). If Audit Page URL is not a public HTTP URL, body contains `[AUDIT PAGE URL]` as a placeholder.

**EMAIL 1 body:**
```
[Owner Name],
I ran an audit on [Salon Name]'s website and online presence this morning.
[FINDING 1]. [FINDING 2]. [FINDING 3].
Each one is a spot where a potential client lands, can't book, and leaves.
I put the full breakdown here: [AUDIT PAGE URL]
Takes 2 minutes to read. If it's relevant, there's a button at the bottom to get on a call.
— Pyetra
Auralith Digital
```

**5 subject options** (stored comma-separated in "Subject Line Options", Pyetra picks one before approving):
```
[Salon] — I found something on your site
your website is losing you appointments
I audited [Salon] this morning
quick question about [Salon]'s bookings
[Salon] — 3 things I noticed
```

**EMAIL 2 body** (follow-up, 3 days, no reply):
```
Subject: Re: [original subject line]

[Owner Name],
Sending this once more in case it got buried.
The audit for [Salon] is still live: [AUDIT PAGE URL]
If the timing is off, no problem. If you're losing bookings and want to know where, it's worth 2 minutes.
— Pyetra
```

**Instagram DM** (sent manually by Pyetra):
```
Hey [Owner Name] — I sent you an email about [Salon] earlier this week.
Ran a quick audit on your site and found a few booking gaps. Left the
breakdown in your inbox if you want to take a look. No pitch, just the findings.
```

**Call script** (4 lines, stored in Airtable "Call Script" field):
```
Line 1: "Hi, is this [Owner]? This is Pyetra — I sent you an email and a DM about [Salon] earlier this week."
Line 2: "I ran a quick audit on your site and found [FINDING 1] and [FINDING 2]. I put it all in a report I sent over."
Line 3: "I'm not calling to pitch you anything — I just wanted to make sure you saw it and answer any questions if you had them."
Line 4: "Do you have 20 minutes this week to go through it together?"
```

### `email_sender.py`
Gmail SMTP (SSL port 465) for outbound sends. Gmail IMAP for reply detection.
Functions: `send_email()`, `send_internal_email()`, `check_for_replies()`

### `send_approved.py`
Sends all "Approved" emails (Email 1 and Email 2) from Airtable. On send: sets `Email N Status = "Sent"`, `Email N Sent = True`, `Email N Sent Date = today`, `Status = "Contacted"` or `"Followed Up"`.
Run: `python3 send_approved.py` (or `--dry-run`)

### `follow_up.py`
Finds prospects where Email 1 was sent 3+ days ago, no reply, Email 2 not yet queued. Writes Email 2 from fixed template. Reads `Email 1 Subject` for the Re: subject, `Audit Page URL` and `Contact Name` from Airtable. Queues as Pending Review.

### `dm_prep.py`
Day 3 after Email 1: generates DM from fixed template using `Contact Name` from Airtable. Stores DM Text + `DM Status = "DM Ready"`. Scrapes Instagram handle if not already stored.

### `call_prep.py`
Day 5 after DM Date: generates 4-line call script from fixed template using `Contact Name` + `Audit Notes` from Airtable. Sets `Status = "Call Ready"`, stores script in `Call Script` field. No Claude used — fully deterministic.

### `generate_audit_page.py`
Generates per-prospect HTML audit report pages. Pulls Audit Notes from Airtable, parses findings, renders HTML to `docs/audits/[slug].html`, writes public URL back to Airtable `Audit Page URL` field. Tries to scrape `og:image` from prospect's website for logo. Each page: finding cards (problem + cost + fix) + Calendly embed at bottom.

```
python3 generate_audit_page.py           # generate for all missing pages
python3 generate_audit_page.py --all     # regenerate all pages
python3 generate_audit_page.py --dry-run # preview only
```

### `daily_summary.py`
Sends morning briefing to `support@auralithdigital.com` with: emails awaiting review, DMs ready to send, emails sent today, follow-ups sent today, prospects needing a call, replies received.

### `update_schema.py`
One-time script to add new fields to existing Airtable base. Safe to re-run — skips fields that already exist. Run whenever new fields are added.

### `setup_cron.sh`
One-time macOS cron installer. Adds a crontab entry to run `main.py` **Monday–Friday at 8:00 AM** (`0 8 * * 1-5`). Creates `logs/` directory.

```
chmod +x setup_cron.sh && ./setup_cron.sh
```

---

## Static Site Files

### `auralith-landing.html`
Business conversion landing page. 5 sections: The Problem, What We Do, How It Works (3-step horizontal), Who This Is For, Book a Call (Calendly embed). Dark navy header/footer, mobile responsive, no frameworks, signed by Pyetra Founder. Also served as `docs/index.html`.

### `booking.html`
Free 20-minute audit call landing page with Calendly inline embed. Local only — not deployed to GitHub Pages.

### `docs/` — GitHub Pages source folder
```
docs/index.html              ← copy of auralith-landing.html
docs/auralith-landing.html
docs/CNAME                   ← reports.auralithdigital.com
docs/audits/                 ← 19 HTML audit pages, one per prospect
```

---

## Deployment

| Item | Status |
|------|--------|
| GitHub repo | `https://github.com/auralithdigital-dev/auralith-site` |
| GitHub Pages | Enabled — source: `main` branch, `/docs` folder |
| Custom domain (in repo) | `reports.auralithdigital.com` |
| HTTPS | Not yet enforced — pending DNS propagation |
| GitHub CLI (`gh`) | Installed at `~/bin/gh` |
| GitHub account | `auralithdigital-dev` |
| Token scopes | `repo`, `workflow` (`read:org` missing — not needed) |

**DNS record still to add in IONOS:**
```
Type:  CNAME
Name:  reports
Value: auralithdigital-dev.github.io
TTL:   3600
```

Once DNS propagates:
- `https://reports.auralithdigital.com` → landing page
- `https://reports.auralithdigital.com/audits/[slug].html` → audit pages
- All 20 Airtable `Audit Page URL` fields already set to public URLs

---

## Daily Workflow (what Pyetra does each morning)

1. Cron runs `main.py` at 8am automatically (Mon–Fri)
2. Pyetra receives daily summary email at `support@auralithdigital.com`
3. Open Airtable → find records with `Email 1 Status = Pending Review`
4. For each: copy a subject line from the `Subject Line Options` field into `Email 1 Subject`, change status to `Approved`
5. Run: `python3 send_approved.py`
6. For `DM Ready` prospects: send DM manually from Instagram, then set `DM Status = DM Sent` in Airtable
7. For `Call Ready` prospects: use the `Call Script` field to make the call, mark `Call Done` when done

---

## Current Status

### Complete
- Full pipeline: scrape → audit → audit page → email → follow-up → DM → call script → daily summary
- Human-review queue — nothing sends without Pyetra approving
- Fixed email/DM/call templates (exact copy locked in, no AI-generated prose)
- Audit page generator — 19 pages in `docs/audits/`, all Airtable URLs updated
- Business landing page deployed as `docs/index.html`
- GitHub repo created, Pages enabled, CNAME set
- All 20 `Audit Page URL` fields updated to `https://reports.auralithdigital.com/audits/...`
- Airtable schema: 31 fields including `Contact Name`, `Subject Line Options`
- Cron schedule set to Monday–Friday 8am (`0 8 * * 1-5`) in `setup_cron.sh`

### Pending
- Add CNAME DNS record in IONOS (`reports` → `auralithdigital-dev.github.io`)
- Once DNS propagates: enable HTTPS in GitHub Pages → Settings → Pages
- Run `./setup_cron.sh` to activate the Monday–Friday 8am cron job
- 8 existing emails in Airtable are `Pending Review` — review, pick subject lines, approve, run `send_approved.py`
- Optional: regenerate those 8 emails with fresh data by clearing their `Email 1 Status` and re-running `python3 main.py --step 3`
