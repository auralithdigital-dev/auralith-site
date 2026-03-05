"""
Auralith Digital — Daily Report Generator
Generates 30 audit report HTML files from MedSpaOutreach_v3.xlsx
Usage: python generate_reports.py
Output: /reports/ folder ready to push to GitHub Pages
"""

import openpyxl
import os
import re
import math
from datetime import date

TEMPLATE_PATH = 'report_template.html'
OUTPUT_DIR = 'docs/medspa'
REPORTS_PER_DAY = 30

def slugify(name):
    name = name.lower()
    name = re.sub(r'[^a-z0-9\s-]', '', name)
    name = re.sub(r'\s+', '-', name.strip())
    name = re.sub(r'-+', '-', name)
    return name[:60]

def format_followers(n):
    if not n or n == 0:
        return 'Not found'
    if n >= 1000:
        return f'{n/1000:.1f}K'
    return str(n)

def review_signal(count):
    if count > 500: return 'Strong social proof'
    if count > 150: return 'Good trust baseline'
    if count > 50: return 'Building credibility'
    if count > 0: return 'Low visibility risk'
    return 'No reviews found'

def rating_signal(r):
    if not r: return 'No rating'
    r = float(r)
    if r >= 4.8: return 'Excellent reputation'
    if r >= 4.5: return 'Strong reputation'
    if r >= 4.0: return 'Average reputation'
    return 'Reputation risk'

def followers_signal(n):
    if not n or n == 0: return 'No Instagram data'
    if n > 10000: return 'Strong social presence'
    if n > 2000: return 'Growing audience'
    if n > 500: return 'Limited reach'
    return 'Very low reach'

def load_businesses(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path)
    lt = wb['Lead Tracker']
    businesses = []

    for r in range(4, 800):
        name = lt.cell(row=r, column=1).value
        if not name:
            break

        reviews_raw = lt.cell(row=r, column=12).value
        rating_raw = lt.cell(row=r, column=13).value
        followers_raw = lt.cell(row=r, column=6).value
        ig_handle = lt.cell(row=r, column=5).value or ''

        try: reviews = int(reviews_raw)
        except: reviews = 0
        try: rating = float(rating_raw)
        except: rating = 0.0
        try: followers = int(followers_raw)
        except: followers = 0

        # Priority score: weight reviews + ig presence + rating
        priority = (reviews * 0.5) + (followers * 0.3) + (rating * 10)
        # Bonus for having both IG handle and website
        if ig_handle and ig_handle != '': priority += 50
        website = lt.cell(row=r, column=3).value or ''
        if website: priority += 30

        # Skip if already has Date First DM filled (col 31)
        already_contacted = lt.cell(row=r, column=31).value
        if already_contacted:
            continue

        businesses.append({
            'row': r,
            'name': str(name).strip(),
            'city': str(lt.cell(row=r, column=2).value or '').strip(),
            'website': str(website).strip(),
            'phone': str(lt.cell(row=r, column=4).value or '').strip(),
            'ig_handle': str(ig_handle).strip(),
            'followers': followers,
            'reviews': reviews,
            'rating': rating,
            'priority': priority,
        })

    # Sort by priority descending
    businesses.sort(key=lambda x: x['priority'], reverse=True)
    return businesses

def generate_report(business, template):
    b = business
    today = date.today().strftime('%B %d, %Y')
    slug = slugify(b['name'])

    ig_display = b['ig_handle'] if b['ig_handle'] else 'Not found'
    followers_display = format_followers(b['followers'])
    rating_display = str(b['rating']) if b['rating'] else 'N/A'
    reviews_display = str(b['reviews']) if b['reviews'] else '0'

    html = template
    html = html.replace('{{BUSINESS_NAME}}', b['name'])
    html = html.replace('{{BUSINESS_NAME_URL}}', b['name'].replace(' ', '%20'))
    html = html.replace('{{CITY}}', b['city'])
    html = html.replace('{{WEBSITE}}', b['website'])
    html = html.replace('{{IG_HANDLE}}', ig_display)
    html = html.replace('{{IG_FOLLOWERS}}', followers_display)
    html = html.replace('{{IG_FOLLOWERS_DISPLAY}}', followers_display)
    html = html.replace('{{IG_FOLLOWERS_RAW}}', str(b['followers']) if b['followers'] else '0')
    html = html.replace('{{GOOGLE_REVIEWS}}', reviews_display)
    html = html.replace('{{GOOGLE_REVIEWS_RAW}}', str(b['reviews']))
    html = html.replace('{{GOOGLE_RATING}}', rating_display)
    html = html.replace('{{GOOGLE_RATING_RAW}}', str(b['rating']))
    html = html.replace('{{AUDIT_DATE}}', today)
    html = html.replace('{{REVIEW_SIGNAL}}', review_signal(b['reviews']))
    html = html.replace('{{RATING_SIGNAL}}', rating_signal(b['rating']))
    html = html.replace('{{FOLLOWERS_SIGNAL}}', followers_signal(b['followers']))

    return slug, html

def main():
    xlsx_path = 'MedSpaOutreach_v3.xlsx'
    if not os.path.exists(xlsx_path):
        xlsx_path = '/mnt/user-data/outputs/MedSpaOutreach_v3.xlsx'

    print(f"Loading businesses from {xlsx_path}...")
    businesses = load_businesses(xlsx_path)
    print(f"Found {len(businesses)} uncontacted businesses, sorted by priority")

    with open(TEMPLATE_PATH, 'r') as f:
        template = f.read()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    batch = businesses[:REPORTS_PER_DAY]
    index_rows = []

    for b in batch:
        slug, html = generate_report(b, template)
        filepath = os.path.join(OUTPUT_DIR, f'{slug}.html')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)

        url = f'https://reports.auralithdigital.com/medspa/{slug}.html'
        index_rows.append({
            'name': b['name'],
            'city': b['city'],
            'ig': b['ig_handle'],
            'reviews': b['reviews'],
            'slug': slug,
            'url': url
        })
        print(f"  ✓ {b['name'][:45]} → {slug}.html")

    # Write outreach index (CSV you can copy handles + URLs from)
    import csv
    with open('todays_outreach.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['name','city','ig','reviews','url'])
        writer.writeheader()
        for row in index_rows:
            writer.writerow({k: row[k] for k in ['name','city','ig','reviews','url']})

    print(f"\n✅ Generated {len(batch)} reports in /{OUTPUT_DIR}/")
    print(f"✅ Outreach list saved to todays_outreach.csv")
    print(f"\nNext step: push to GitHub Pages")
    print(f"  bash push_medspa.sh")

if __name__ == '__main__':
    main()
