#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Auralith Prospect Machine — macOS Cron Installer
#
# Installs two crontab entries, both Monday–Friday:
#   8:00 AM — main.py        (scrape, audit, queue emails, daily summary)
#   8:05 AM — send_followups.py  (Email 2 follow-ups, 3-day gate)
#
# Usage:
#   chmod +x setup_cron.sh
#   ./setup_cron.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

# Resolve the directory this script lives in (the project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/daily.log"
FOLLOWUP_LOG="$LOG_DIR/followup.log"

# Detect Python (prefer python3, fall back to python)
PYTHON_BIN="$(command -v python3 || command -v python)"
if [ -z "$PYTHON_BIN" ]; then
  echo "ERROR: Python not found. Install Python 3 first."
  exit 1
fi

# Create logs directory
mkdir -p "$LOG_DIR"
echo "✓ Log directory: $LOG_DIR"

# The two cron entries
CRON_MAIN="0 8 * * 1-5 cd \"$SCRIPT_DIR\" && \"$PYTHON_BIN\" main.py >> \"$LOG_FILE\" 2>&1"
CRON_FOLLOWUP="5 8 * * 1-5 cd /Users/pyetratoscano/auralith-prospect-machine && python3 send_followups.py >> logs/followup.log 2>&1"

CURRENT_CRONTAB="$(crontab -l 2>/dev/null || true)"

# ── main.py entry ─────────────────────────────────────────────────────────────
if echo "$CURRENT_CRONTAB" | grep -qF "main.py"; then
  echo ""
  echo "⚠  main.py cron entry already exists — skipping"
else
  CURRENT_CRONTAB="$(printf '%s\n%s' "$CURRENT_CRONTAB" "$CRON_MAIN")"
  echo "✓ main.py cron entry added (Mon–Fri 8:00 AM)"
fi

# ── send_followups.py entry ───────────────────────────────────────────────────
if echo "$CURRENT_CRONTAB" | grep -qF "send_followups.py"; then
  echo ""
  echo "⚠  send_followups.py cron entry already exists — skipping"
else
  CURRENT_CRONTAB="$(printf '%s\n%s' "$CURRENT_CRONTAB" "$CRON_FOLLOWUP")"
  echo "✓ send_followups.py cron entry added (Mon–Fri 8:05 AM)"
fi

# Write the updated crontab
echo "$CURRENT_CRONTAB" | crontab -

echo ""
echo "Schedule:"
echo "  0 8 * * 1-5  →  main.py          (logs: $LOG_FILE)"
echo "  5 8 * * 1-5  →  send_followups.py (logs: $FOLLOWUP_LOG)"
echo ""
echo "Current crontab:"
echo "────────────────"
crontab -l
echo ""
echo "To edit or remove entries, run: crontab -e"
echo "To view logs:"
echo "  tail -f $LOG_FILE"
echo "  tail -f $FOLLOWUP_LOG"
