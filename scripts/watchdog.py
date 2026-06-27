"""
watchdog.py - Stuck-task watchdog for the agent harness.

Scans tasks in 'locked' or 'running' state where updated_at is older than
STUCK_THRESHOLD_MINUTES. Resets them to 'pending' and creates an incident.

Usage:
  .venv/bin/python scripts/watchdog.py
  .venv/bin/python scripts/watchdog.py --dry-run
  .venv/bin/python scripts/watchdog.py --threshold 60   (minutes)
"""
import argparse
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "tasks.db"
STUCK_THRESHOLD_MINUTES = 30


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def find_stuck_tasks(conn: sqlite3.Connection, threshold_minutes: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)).isoformat()
    rows = conn.execute(
        """SELECT id, description, goal_id, status, attempts, updated_at, locked_at
           FROM tasks
           WHERE status IN ('locked', 'running')
             AND updated_at < ?
           ORDER BY updated_at ASC""",
        (cutoff,)
    ).fetchall()
    return [dict(r) for r in rows]


def reset_stuck_task(conn: sqlite3.Connection, task_id: str) -> None:
    conn.execute(
        """UPDATE tasks
           SET status = 'pending',
               updated_at = ?
           WHERE id = ? AND status IN ('locked', 'running')""",
        (utcnow(), task_id)
    )
    conn.commit()


def create_incident(conn: sqlite3.Connection, task: dict) -> str:
    incident_id = str(uuid.uuid4())
    now = utcnow()
    age_note = f"last updated at {task['updated_at'][:19]}"
    conn.execute(
        """INSERT INTO incidents (id, severity, title, description, task_id, goal_id, status, created_at)
           VALUES (?, 'medium', ?, ?, ?, ?, 'open', ?)""",
        (
            incident_id,
            f"Stuck task reset: {task['description'][:80]}",
            f"Task {task['id'][:8]} was in status '{task['status']}' ({age_note}). "
            f"Watchdog reset it to pending. Attempts: {task['attempts']}.",
            task["id"],
            task.get("goal_id"),
            now,
        )
    )
    conn.commit()
    return incident_id


def run_watchdog(threshold_minutes: int = STUCK_THRESHOLD_MINUTES,
                 dry_run: bool = False) -> list[dict]:
    """Check for stuck tasks and reset them. Returns list of affected task records."""
    if not DB_PATH.exists():
        print(f"[watchdog] ERROR: tasks.db not found at {DB_PATH}")
        return []

    conn = get_connection()
    stuck = find_stuck_tasks(conn, threshold_minutes)

    if not stuck:
        print(f"[watchdog] No stuck tasks (threshold: {threshold_minutes} min). All clear.")
        conn.close()
        return []

    print(f"[watchdog] Found {len(stuck)} stuck task(s) (>{threshold_minutes} min in locked/running):")
    for task in stuck:
        age_str = f"since {task['updated_at'][:19]}"
        print(f"  {task['id'][:8]}  status={task['status']}  {age_str}  {task['description'][:60]}")

    if dry_run:
        print("[watchdog] --dry-run: no changes made.")
        conn.close()
        return stuck

    reset_count = 0
    for task in stuck:
        reset_stuck_task(conn, task["id"])
        inc_id = create_incident(conn, task)
        print(f"  -> reset to pending, incident {inc_id[:8]} created")
        reset_count += 1

    print(f"[watchdog] Done: {reset_count} task(s) reset, {reset_count} incident(s) created.")
    conn.close()
    return stuck


def main():
    parser = argparse.ArgumentParser(description="Harness stuck-task watchdog")
    parser.add_argument(
        "--threshold", type=int, default=STUCK_THRESHOLD_MINUTES,
        help=f"Minutes before a locked/running task is considered stuck (default: {STUCK_THRESHOLD_MINUTES})"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report stuck tasks without resetting them"
    )
    args = parser.parse_args()
    run_watchdog(threshold_minutes=args.threshold, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
