#!/usr/bin/env bash
# run_scan.sh - Run the proactive monitoring scan and update status.md.
#
# Designed to be called manually or from OS cron:
#   crontab -e
#   0 9 * * * /path/to/repo/scripts/run_scan.sh >> /path/to/repo/logs/scan_cron.log 2>&1
#
# Usage:
#   ./scripts/run_scan.sh           # live scan (creates goals from flags)
#   ./scripts/run_scan.sh --dry-run # report only, no goal creation

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "[run_scan] ERROR: venv not found at $REPO_ROOT/.venv. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

echo "[run_scan] $(date -u +%Y-%m-%dT%H:%M:%SZ) Starting scan..."
"$PYTHON" "$REPO_ROOT/scripts/scan.py" "$@"

echo "[run_scan] Updating status.md..."
"$PYTHON" "$REPO_ROOT/scripts/update_status.py"

echo "[run_scan] Done."
