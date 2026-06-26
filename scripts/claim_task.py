"""
claim_task.py - CLI tool to inspect and manage tasks.db.

Usage:
  .venv/bin/python scripts/claim_task.py list [--status STATUS]
  .venv/bin/python scripts/claim_task.py show TASK_ID
  .venv/bin/python scripts/claim_task.py unlock TASK_ID
  .venv/bin/python scripts/claim_task.py add --desc "description" [--goal GOAL_ID] [--priority N] [--risk LEVEL]
  .venv/bin/python scripts/claim_task.py stuck     # show locked tasks older than 30min
"""
import argparse
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "tasks.db"
LOCK_TIMEOUT_MINUTES = 30


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def cmd_list(args: argparse.Namespace) -> None:
    conn = get_conn()
    status_filter = args.status or None
    if status_filter:
        rows = conn.execute(
            "SELECT id, status, priority, risk_level, description FROM tasks WHERE status=? ORDER BY priority DESC, created_at ASC",
            (status_filter,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, status, priority, risk_level, description FROM tasks ORDER BY priority DESC, created_at ASC"
        ).fetchall()

    if not rows:
        print("No tasks found.")
        return
    print(f"{'ID':<10} {'STATUS':<10} {'PRI':>3} {'RISK':<8} DESCRIPTION")
    print("-" * 80)
    for r in rows:
        print(f"{r['id'][:8]:<10} {r['status']:<10} {r['priority']:>3} {r['risk_level']:<8} {r['description'][:50]}")
    print(f"\n{len(rows)} task(s)")


def cmd_show(args: argparse.Namespace) -> None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM tasks WHERE id LIKE ?", (args.task_id + "%",)).fetchone()
    if not row:
        print(f"Task not found: {args.task_id}")
        return
    for key in row.keys():
        val = row[key]
        if val and key in ("evidence", "artifacts", "depends_on", "skill_tags"):
            try:
                val = json.dumps(json.loads(val), indent=2)
            except Exception:
                pass
        if val:
            print(f"{key}: {val}")


def cmd_unlock(args: argparse.Namespace) -> None:
    conn = get_conn()
    result = conn.execute(
        "UPDATE tasks SET status='pending', locked_at=NULL, updated_at=? WHERE id LIKE ? AND status='locked'",
        (utcnow(), args.task_id + "%")
    )
    conn.commit()
    if result.rowcount:
        print(f"Unlocked task {args.task_id}")
    else:
        print(f"No locked task found matching {args.task_id}")


def cmd_add(args: argparse.Namespace) -> None:
    conn = get_conn()
    tid = str(uuid.uuid4())
    now = utcnow()
    conn.execute("""
        INSERT INTO tasks (id, goal_id, description, priority, risk_level,
                           skill_tags, status, depends_on, attempts, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (tid, args.goal, args.desc, args.priority, args.risk,
          "[]", "pending", "[]", 0, now, now))
    conn.commit()
    print(f"Added task {tid[:8]}: {args.desc}")


def cmd_stuck(args: argparse.Namespace) -> None:
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, locked_at, description FROM tasks
        WHERE status = 'locked'
          AND locked_at < datetime('now', ? || ' minutes')
    """, (f"-{LOCK_TIMEOUT_MINUTES}",)).fetchall()

    if not rows:
        print("No stuck tasks.")
        return
    print(f"Stuck tasks (locked > {LOCK_TIMEOUT_MINUTES}min):")
    for r in rows:
        print(f"  {r['id'][:8]} locked_at={r['locked_at']} - {r['description'][:60]}")
    print(f"\nRun: .venv/bin/python scripts/claim_task.py unlock <id> to unblock")


def main():
    parser = argparse.ArgumentParser(description="Task DB CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list")
    p_list.add_argument("--status", help="Filter by status")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show")
    p_show.add_argument("task_id")
    p_show.set_defaults(func=cmd_show)

    p_unlock = sub.add_parser("unlock")
    p_unlock.add_argument("task_id")
    p_unlock.set_defaults(func=cmd_unlock)

    p_add = sub.add_parser("add")
    p_add.add_argument("--desc", required=True)
    p_add.add_argument("--goal", default=None)
    p_add.add_argument("--priority", type=int, default=5)
    p_add.add_argument("--risk", default="low", choices=["low", "medium", "high"])
    p_add.set_defaults(func=cmd_add)

    p_stuck = sub.add_parser("stuck")
    p_stuck.set_defaults(func=cmd_stuck)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
