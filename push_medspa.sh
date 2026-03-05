#!/bin/bash
# Daily med spa report generator + publisher
# Usage: bash push_medspa.sh
# Requires: MedSpaOutreach_v3.xlsx in the same directory

set -e
cd "$(dirname "$0")"

echo "Generating med spa reports..."
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY python3 generate_reports.py

echo ""
echo "Pushing to GitHub Pages..."
git add docs/medspa/
git commit -m "Med spa batch $(date +%Y-%m-%d)"
git push origin main

echo ""
echo "Live at https://reports.auralithdigital.com/medspa/"
echo "Outreach list: todays_outreach.csv"
