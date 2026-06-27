"""
escalate_incidents.py - Auto-escalate open incidents based on age.

Escalation ladder (configurable via --low-hours and --medium-hours):
  low severity, open > 1 hour  -> medium
  medium severity, open > 2 hours -> high

Adds 'escalated_at' and 'escalation_count' columns to incidents table if absent.

Usage:
  .venv/bin/python scripts/escalate_incidents.py
  .venv/bin/python scripts/escalate_incidents.py --dry-run
  .venv/bin/python scripts/escalate_incidents.py --low-hours 2 --medium-hours 4
"""
import argparse
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "tasks.db"

LOW_ESCALATE_HOURS = 1
MEDIUM_ESCALATE_HOURS = 2


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_escalation_columns(conn: sqlite3.Connection) -> None:
    """Add escalation tracking columns if they don't exist yet."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(incidents)")}
    if "escalated_at" not in existing:
        conn.execute("ALTER TABLE incidents ADD COLUMN escalated_at TEXT")
    if "escalation_count" not in existing:
        conn.execute("ALTER TABLE incidents ADD COLUMN escalation_count INTEGER DEFAULT 0")
    conn.commit()


def find_escalatable(conn: sqlite3.Connection,
                     low_hours: int, medium_hours: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    low_cutoff = (now - timedelta(hours=low_hours)).isoformat()
    medium_cutoff = (now - timedelta(hours=medium_hours)).isoformat()

    rows = conn.execute(
        """SELECT id, severity, title, created_at, escalation_count
           FROM incidents
           WHERE status = 'open'
             AND (
               (severity = 'low' AND created_at < ?)
               OR (severity = 'medium' AND created_at < ?)
             )
           ORDER BY created_at ASC""",
        (low_cutoff, medium_cutoff)
    ).fetchall()
    return [dict(r) for r in rows]


NEXT_SEVERITY = {"low": "medium", "medium": "high"}


def escalate_incident(conn: sqlite3.Connection, incident_id: str,
                      current_severity: str) -> str:
    new_severity = NEXT_SEVERITY[current_severity]
    conn.execute(
        """UPDATE incidents
           SET severity = ?,
               escalated_at = ?,
               escalation_count = COALESCE(escalation_count, 0) + 1
           WHERE id = ?""",
        (new_severity, utcnow(), incident_id)
    )
    conn.commit()
    return new_severity


def run_escalation(low_hours: int = LOW_ESCALATE_HOURS,
                   medium_hours: int = MEDIUM_ESCALATE_HOURS,
                   dry_run: bool = False) -> list[dict]:
    """Escalate aged open incidents. Returns list of escalated incident records."""
    if not DB_PATH.exists():
        print(f"[escalate] ERROR: tasks.db not found at {DB_PATH}")
        return []

    conn = get_connection()
    ensure_escalation_columns(conn)

    candidates = find_escalatable(conn, low_hours, medium_hours)

    if not candidates:
        print(f"[escalate] No incidents to escalate (low>{low_hours}h, medium>{medium_hours}h).")
        conn.close()
        return []

    print(f"[escalate] Found {len(candidates)} incident(s) to escalate:")
    for inc in candidates:
        age_str = f"since {inc['created_at'][:19]}"
        print(f"  {inc['id'][:8]}  {inc['severity']:<8} {age_str}  {inc['title'][:55]}")

    if dry_run:
        print("[escalate] --dry-run: no changes made.")
        conn.close()
        return candidates

    escalated = []
    for inc in candidates:
        if inc["severity"] not in NEXT_SEVERITY:
            continue
        new_sev = escalate_incident(conn, inc["id"], inc["severity"])
        print(f"  -> {inc['id'][:8]}: {inc['severity']} -> {new_sev}")
        escalated.append({**inc, "new_severity": new_sev})

    print(f"[escalate] Done: {len(escalated)} incident(s) escalated.")
    conn.close()
    return escalated


def main():
    parser = argparse.ArgumentParser(description="Escalate aged open incidents")
    parser.add_argument(
        "--low-hours", type=int, default=LOW_ESCALATE_HOURS,
        help=f"Hours before a low-severity incident escalates to medium (default: {LOW_ESCALATE_HOURS})"
    )
    parser.add_argument(
        "--medium-hours", type=int, default=MEDIUM_ESCALATE_HOURS,
        help=f"Hours before a medium-severity incident escalates to high (default: {MEDIUM_ESCALATE_HOURS})"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report escalatable incidents without making changes"
    )
    args = parser.parse_args()
    run_escalation(low_hours=args.low_hours, medium_hours=args.medium_hours, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
