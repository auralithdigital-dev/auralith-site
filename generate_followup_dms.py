"""
Parse dm-scripts-30-final.docx and email-scripts-150.docx (which also contains handles),
generate follow-up DMs, and write a CSV with columns: Handle, Follow Up Message.
Contacts with no Instagram handle (Google / direct) go to a separate section.
"""

import re
import csv
import os
from docx import Document

DM30_PATH    = "/Users/pyetratoscano/Downloads/dm-scripts-30-final.docx"
DM150_PATH   = "dm-scripts-150.docx"
OUTPUT_CSV   = "followup-dms.csv"

# ── Words that are NOT person first names ─────────────────────────────────────
NOT_NAMES = {
    # business / service words
    'spa', 'med', 'medspa', 'medispa', 'skin', 'beauty', 'laser', 'health',
    'wellness', 'aesthetic', 'aesthetics', 'clinic', 'center', 'centre',
    'studio', 'lounge', 'medical', 'face', 'body', 'glo', 'glow', 'lux',
    'luxe', 'derm', 'derma', 'salon', 'anti', 'pure', 'elite', 'prime',
    'care', 'renew', 'restore', 'revive', 'tox', 'infusion', 'drip',
    'hyper', 'cryo', 'labs', 'lab', 'club', 'group', 'rhw', 'pac',
    'inject', 'filler', 'botox', 'hydra', 'image', 'ideal', 'icon',
    'glam', 'chic', 'zen', 'bliss', 'vibrant', 'refresh', 'bright',
    'laser', 'diva', 'allure', 'prestige', 'signature', 'unique', 'royal',
    'company', 'boutique', 'collective', 'institute', 'partners',
    # brand names that look like names but aren't personal first names
    'galore', 'basis', 'kibali', 'zentox', 'auramed', 'luminos',
    'vivid', 'radiance', 'essence', 'essential', 'verde', 'kirra',
    # common English words
    'the', 'and', 'for', 'by', 'de', 'my', 'us', 'your', 'our', 'new',
    'inspire', 'explore', 'create', 'evolve', 'emerge', 'thrive', 'live',
    'love', 'life', 'core', 'best', 'nice', 'fresh', 'calm', 'free',
    'real', 'bold', 'lotus', 'olive', 'sage', 'aurora', 'nova', 'luna',
    'star', 'bloom', 'serene', 'grace', 'eden', 'oasis', 'haven',
    'green', 'blue', 'pink', 'gold', 'silver', 'rose', 'white', 'black',
    'forever', 'always', 'simply', 'truly', 'purely', 'only', 'just',
    'usa', 'llc', 'inc', 'md', 'pga', 'fl', 'rn',
    # South Florida location fragments
    'boca', 'raton', 'delray', 'coral', 'palm', 'west', 'miami',
    'bocaraton', 'westpalm', 'deerfield', 'parkland', 'coconut', 'creek',
    'plantation', 'lauderdale', 'broward', 'pompano',
}

# Business word substrings that disqualify a compound token
BIZ_SUBSTRINGS = {
    'medspa', 'medispa', 'aesthetic', 'wellness', 'medical', 'beauty',
    'skin', 'laser', 'health', 'clinic', 'studio', 'salon', 'lounge',
    'derm', 'botox', 'infus', 'cryo', 'hyper', 'diva', 'tox', 'company',
}

# Prefixes that signal the token is not a personal name
FILLER_STARTS = ('the', 'my', 'new', 'all', 'get', 'pro', 'top', 'max',
                 'best', 'our', 'by', 'de', 'for', 'its')

def is_likely_name(token: str) -> bool:
    """True if token looks like a person's first name."""
    if not token or not token.isalpha():
        return False
    if len(token) < 3 or len(token) > 12:
        return False
    if token in NOT_NAMES:
        return False
    for start in FILLER_STARTS:
        if token.startswith(start) and len(token) > len(start):
            return False
    if any(bz in token for bz in BIZ_SUBSTRINGS):
        return False
    # reject tokens that contain a South-FL city fragment
    for loc in ('boca', 'raton', 'coral', 'palm', 'miami', 'delray',
                'deerfield', 'parkland', 'coconut'):
        if loc in token:
            return False
    return True


def extract_first_name(handle: str):
    """
    Try to extract a person's first name from an Instagram handle.
    Returns the capitalised first name, or None if no clear personal name found.
    """
    if not handle:
        return None
    h = handle.lstrip('@').lower().rstrip('_').rstrip('.')

    # Bail out early if handle starts with a digit (brand handle, not a person)
    if h and h[0].isdigit():
        return None

    # 1. "by[name]" pattern — e.g. @facebyjacquie -> Jacquie
    by_match = re.search(r'by([a-z]{3,12})$', h)
    if by_match:
        candidate = by_match.group(1)
        if is_likely_name(candidate):
            return candidate.capitalize()

    # 2. Handles with _ or . separators — first non-trivial token is often the name
    if '_' in h or '.' in h:
        parts = re.split(r'[_.\-]+', h)
        for part in parts:
            part = re.sub(r'[^a-z]', '', part)
            if is_likely_name(part):
                return part.capitalize()
        return None  # separated but no name found — don't fall through to compound

    # 3. "dr[name]..." pattern — e.g. @drmylissasmedicalboutique -> Mylissa
    if h.startswith('dr') and len(h) > 5:
        rest = h[2:]
        earliest_idx = len(rest)
        for bz in BIZ_SUBSTRINGS:
            idx = rest.find(bz)
            if 0 < idx < earliest_idx:
                earliest_idx = idx
        if earliest_idx < len(rest):
            candidate = rest[:earliest_idx]
            if is_likely_name(candidate):
                return candidate.capitalize()

    # 4. No separators: find a name prefix before a trailing business word.
    #    Be conservative: trust prefix only if it's ≤ 8 chars (typical first name).
    sorted_biz = sorted(NOT_NAMES, key=len, reverse=True)
    for bw in sorted_biz:
        if len(bw) < 3:
            continue
        if h.endswith(bw):
            prefix = h[: len(h) - len(bw)]
            if is_likely_name(prefix) and len(prefix) <= 8:
                return prefix.capitalize()

    return None


def short_biz_name(name: str) -> str:
    """Strip location suffixes and parentheticals for a clean business name."""
    name = re.sub(r'\s*\(.*?\)', '', name).strip()
    for suffix in [
        " - Boca Raton", " - Delray Beach", " - West Palm Beach",
        " - Palm Beach Gardens", " - Coral Springs", " - Deerfield Beach",
        " - Parkland", " Boca Raton", " Delray Beach", " West Palm Beach",
        " Palm Beach Gardens", " Coral Springs", " Deerfield Beach", " - PGA",
    ]:
        if name.lower().endswith(suffix.lower()):
            name = name[: -len(suffix)].strip()
    if ":" in name:
        name = name.split(":")[0].strip()
    return name


def make_dm(greeting_name: str, biz_name: str) -> str:
    return (
        f"Hey {greeting_name} \u2014 just wanted to follow up on what I sent over. "
        f"Quick question: is getting inactive clients to rebook something "
        f"{biz_name} is actively focused on right now?"
    )


# ── Parser: extract (business_name, handle) pairs from a docx ────────────────

def parse_docx(path: str):
    doc = Document(path)
    entries = []
    current_name = None

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # Numbered entry: "12. Business Name" or "12. Business Name"
        m = re.match(r'^\d+\.\s+(.+)$', text)
        if m:
            current_name = m.group(1).strip()
            continue

        # Handle line
        if text.startswith("Handle:") and current_name:
            raw_handle = text[len("Handle:"):].strip()
            entries.append((current_name, raw_handle))
            current_name = None

    return entries


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Parse both files, deduplicate by business name (case-insensitive)
    raw = parse_docx(DM30_PATH) + parse_docx(DM150_PATH)

    seen = {}
    for biz, handle in raw:
        key = biz.lower().strip()
        if key not in seen:
            seen[key] = (biz, handle)

    all_entries = list(seen.values())
    print(f"Total unique contacts: {len(all_entries)}")

    ig_rows    = []  # has Instagram handle
    email_rows = []  # Google / direct only

    for biz, raw_handle in all_entries:
        is_direct = (
            not raw_handle
            or 'google' in raw_handle.lower()
            or 'direct' in raw_handle.lower()
        )

        clean_biz = short_biz_name(biz)
        clean_biz_nodot = re.sub(r'\s*,?\s*\b(inc\.?|llc\.?|corp\.?|ltd\.?)\s*$', '',
                                 clean_biz, flags=re.IGNORECASE).strip()

        if is_direct:
            email_rows.append((biz, ""))
        else:
            handle = raw_handle if raw_handle.startswith('@') else f"@{raw_handle}"
            first  = extract_first_name(handle)
            greeting = first if first else clean_biz_nodot
            dm = make_dm(greeting, clean_biz_nodot)
            ig_rows.append((handle, dm, biz))

    # Write CSV
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Handle", "Follow Up Message"])

        for handle, dm, biz in ig_rows:
            writer.writerow([handle, dm])

        # Separator
        writer.writerow([])
        writer.writerow(["--- FOLLOW UP BY EMAIL (no Instagram handle) ---", ""])

        for biz, _ in email_rows:
            writer.writerow([biz, ""])

    print(f"\nInstagram DMs:    {len(ig_rows)}")
    print(f"Email follow-ups: {len(email_rows)}")
    print(f"Saved: {OUTPUT_CSV}")

    # Preview — show first name detection results
    print("\nSample — greeting name used:")
    for handle, dm, biz in ig_rows[:20]:
        greeting = re.match(r'Hey (.+?) \u2014', dm).group(1)
        first = extract_first_name(handle)
        flag = " <-- name" if first else ""
        print(f"  {handle:<35} -> '{greeting}'{flag}")


if __name__ == "__main__":
    main()
