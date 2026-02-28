"""
Website scraper for Auralith Prospect Machine.

For each prospect's website:
- Fetches the homepage and /contact page
- Extracts email addresses, Instagram handles, and content summary

Run standalone:
    python3 website_scraper.py https://example.com
"""

import re
import sys
import logging
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

import config

log = logging.getLogger(__name__)

EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# instagram.com/HANDLE — capture handle (letters, digits, dots, underscores)
INSTAGRAM_URL_PATTERN = re.compile(
    r"instagram\.com/([A-Za-z0-9_.]{1,30})/?",
    re.IGNORECASE,
)

# Accounts to ignore (platform pages, not business accounts)
INSTAGRAM_EXCLUDED = {"p", "reel", "explore", "stories", "accounts", "shoppingbag", ""}

# Emails that are noise / not real business contacts
EXCLUDED_EMAIL_DOMAINS = {
    "example.com", "sentry.io", "wixpress.com", "squarespace.com",
    "godaddy.com", "wordpress.com", "googleapis.com",
}


def _fetch(url: str, timeout: int = None) -> Optional[str]:
    """Fetches a URL and returns the HTML source, or None on failure."""
    timeout = timeout or config.REQUEST_TIMEOUT
    try:
        resp = requests.get(
            url,
            headers=config.REQUEST_HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        log.debug(f"Could not fetch {url}: {e}")
        return None


def extract_email_from_html(html: str) -> Optional[str]:
    """
    Scans raw HTML for email addresses.
    Prioritises mailto: links, then plain-text regex matches.
    Returns the best candidate or None.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Priority: mailto: hrefs
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("mailto:"):
            email = href[7:].split("?")[0].strip().lower()
            if _is_valid_email(email):
                return email

    # Fallback: regex scan the visible text
    text = soup.get_text(" ", strip=True)
    matches = EMAIL_PATTERN.findall(text)
    for email in matches:
        email = email.lower()
        if _is_valid_email(email):
            return email

    return None


def extract_instagram_handle(html: str) -> Optional[str]:
    """
    Scans HTML for an Instagram profile link.
    Returns the handle (without @) or None.
    """
    # Priority: <a href="https://instagram.com/handle">
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = INSTAGRAM_URL_PATTERN.search(href)
        if m:
            handle = m.group(1).rstrip("/").lower()
            if handle not in INSTAGRAM_EXCLUDED:
                return handle

    # Fallback: scan raw HTML text for any instagram.com/handle pattern
    for m in INSTAGRAM_URL_PATTERN.finditer(html):
        handle = m.group(1).rstrip("/").lower()
        if handle not in INSTAGRAM_EXCLUDED:
            return handle

    return None


def _is_valid_email(email: str) -> bool:
    if not EMAIL_PATTERN.fullmatch(email):
        return False
    domain = email.split("@")[-1]
    if domain in EXCLUDED_EMAIL_DOMAINS:
        return False
    # Skip image file extensions accidentally matched
    if email.endswith((".png", ".jpg", ".gif", ".jpeg", ".webp")):
        return False
    return True


def extract_content_summary(html: str, max_chars: int = 600) -> str:
    """
    Extracts meaningful visible text from a page for use as Claude context.
    Strips nav/footer/script noise, returns up to max_chars characters.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove clutter
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def scrape_website(url: str) -> dict:
    """
    Main entry point. Scrapes homepage + /contact page.

    Returns:
        {
            "email": str | None,
            "instagram": str | None,   # handle without @
            "content_summary": str,    # up to 600 chars of page text
        }
    """
    if not url:
        return {"email": None, "instagram": None, "content_summary": ""}

    # Normalise URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Fetch homepage
    homepage_html = _fetch(url)
    if not homepage_html:
        # Try http fallback
        http_url = url.replace("https://", "http://", 1)
        homepage_html = _fetch(http_url)
        if homepage_html:
            url = http_url

    if not homepage_html:
        log.warning(f"Could not reach website: {url}")
        return {"email": None, "instagram": None, "content_summary": ""}

    email = extract_email_from_html(homepage_html)
    instagram = extract_instagram_handle(homepage_html)
    content_summary = extract_content_summary(homepage_html)

    # Also check /contact page for anything still missing
    if not email or not instagram:
        parsed = urlparse(url)
        contact_url = f"{parsed.scheme}://{parsed.netloc}/contact"
        contact_html = _fetch(contact_url)
        if contact_html:
            if not email:
                email = extract_email_from_html(contact_html)
            if not instagram:
                instagram = extract_instagram_handle(contact_html)
            if not content_summary:
                content_summary = extract_content_summary(contact_html)

    return {
        "email": email,
        "instagram": instagram,
        "content_summary": content_summary,
    }


# ─── Standalone test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    print(f"\nScraping: {url}\n")
    result = scrape_website(url)
    print(f"Email found     : {result['email'] or 'None'}")
    print(f"Instagram handle: {result['instagram'] or 'None'}")
    print(f"\nContent summary ({len(result['content_summary'])} chars):")
    print(result["content_summary"])
