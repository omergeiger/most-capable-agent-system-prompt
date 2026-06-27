"""
sweep_artifacts.py - Delete task artifact directories older than N days.

Scans artifacts/ for UUID-named subdirectories whose mtime is older than
--days (default 7). Skips non-UUID directories (dashboard.html, launchd/, etc.)
and anything referenced by an active (non-done/failed) task in tasks.db.

Usage:
  .venv/bin/python scripts/sweep_artifacts.py
  .venv/bin/python scripts/sweep_artifacts.py --days 3
  .venv/bin/python scripts/sweep_artifacts.py --dry-run
"""
import argparse
import re
import shutil
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "tasks.db"
ARTIFACTS_DIR = REPO_ROOT / "artifacts"
DEFAULT_DAYS = 7
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_active_task_ids() -> set[str]:
    """Return IDs of tasks that are not done or failed (still in-flight)."""
    if not DB_PATH.exists():
        return set()
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT id FROM tasks WHERE status NOT IN ('done', 'failed', 'cancelled')"
    ).fetchall()
    conn.close()
    return {r[0] for r in rows}


def find_sweepable(days: int) -> list[Path]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    active_ids = get_active_task_ids()
    sweepable = []

    for entry in sorted(ARTIFACTS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        if not UUID_RE.match(entry.name):
            continue
        if entry.name in active_ids:
            continue
        mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            sweepable.append(entry)

    return sweepable


def human_size(path: Path) -> str:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    if total < 1024:
        return f"{total}B"
    if total < 1024 ** 2:
        return f"{total // 1024}KB"
    return f"{total // 1024 ** 2}MB"


def run_sweep(days: int = DEFAULT_DAYS, dry_run: bool = False) -> list[Path]:
    """Delete artifact dirs older than `days`. Returns list of paths removed (or would remove)."""
    if not ARTIFACTS_DIR.exists():
        print(f"[sweep] artifacts/ not found at {ARTIFACTS_DIR}")
        return []

    targets = find_sweepable(days)

    if not targets:
        print(f"[sweep] Nothing to sweep (threshold: {days} days). All clear.")
        return []

    total_size = sum(
        sum(f.stat().st_size for f in t.rglob("*") if f.is_file())
        for t in targets
    )
    size_str = f"{total_size // 1024}KB" if total_size < 1024 ** 2 else f"{total_size // 1024 ** 2}MB"
    print(f"[sweep] Found {len(targets)} artifact dir(s) older than {days} days ({size_str} total):")
    for t in targets:
        mtime = datetime.fromtimestamp(t.stat().st_mtime, tz=timezone.utc)
        print(f"  {t.name[:8]}...  {mtime.strftime('%Y-%m-%d')}  {human_size(t)}")

    if dry_run:
        print("[sweep] --dry-run: no files deleted.")
        return targets

    removed = []
    for t in targets:
        shutil.rmtree(t)
        removed.append(t)
        print(f"  -> deleted {t.name[:8]}...")

    print(f"[sweep] Done: {len(removed)} director{'y' if len(removed) == 1 else 'ies'} removed ({size_str} freed).")
    return removed


def main():
    parser = argparse.ArgumentParser(description="Sweep old task artifact directories")
    parser.add_argument(
        "--days", type=int, default=DEFAULT_DAYS,
        help=f"Delete artifact dirs older than this many days (default: {DEFAULT_DAYS})"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would be deleted without deleting"
    )
    args = parser.parse_args()
    run_sweep(days=args.days, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
