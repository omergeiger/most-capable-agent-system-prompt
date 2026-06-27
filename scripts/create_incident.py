"""
create_incident.py - CLI for viewing and logging incidents.

Usage:
  .venv/bin/python scripts/create_incident.py list [--open]
  .venv/bin/python scripts/create_incident.py log <title> [--severity low|medium|high]
                                                          [--task-id TASK_ID]
                                                          [--goal-id GOAL_ID]
                                                          [--description TEXT]
  .venv/bin/python scripts/create_incident.py resolve <incident-id-prefix> [--root-cause TEXT] [--remediation TEXT]
"""
import argparse
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "tasks.db"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def cmd_list(args) -> None:
    conn = get_connection()
    where = "WHERE status = 'open'" if args.open else ""
    rows = conn.execute(f"""
        SELECT id, severity, title, status, task_id, goal_id, created_at, resolved_at
        FROM incidents
        {where}
        ORDER BY created_at DESC
        LIMIT 50
    """).fetchall()
    conn.close()

    if not rows:
        print("No incidents found.")
        return

    print(f"{'ID':<10} {'SEV':<8} {'STATUS':<10} {'CREATED':<22} TITLE")
    print("-" * 90)
    for r in rows:
        print(f"{r['id'][:8]:<10} {r['severity']:<8} {r['status']:<10} {r['created_at'][:19]:<22} {r['title'][:60]}")


def cmd_log(args) -> None:
    conn = get_connection()
    incident_id = str(uuid.uuid4())
    now = utcnow()
    conn.execute(
        """INSERT INTO incidents (id, severity, title, description, task_id, goal_id, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'open', ?)""",
        (incident_id, args.severity, args.title,
         args.description or "", args.task_id or None, args.goal_id or None, now)
    )
    conn.commit()
    conn.close()
    print(f"Incident created: {incident_id}")
    print(f"  Severity: {args.severity}")
    print(f"  Title: {args.title}")


def cmd_resolve(args) -> None:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id FROM incidents WHERE id LIKE ?", (args.prefix + "%",)
    ).fetchall()
    if not rows:
        print(f"No incident found matching prefix '{args.prefix}'")
        sys.exit(1)
    if len(rows) > 1:
        print(f"Prefix '{args.prefix}' is ambiguous. Use more characters.")
        sys.exit(1)

    incident_id = rows[0][0]
    now = utcnow()
    conn.execute(
        """UPDATE incidents
           SET status='resolved', resolved_at=?, root_cause=?, remediation=?
           WHERE id=?""",
        (now, args.root_cause or None, args.remediation or None, incident_id)
    )
    conn.commit()
    conn.close()
    print(f"Incident {incident_id[:8]} resolved.")


def main():
    parser = argparse.ArgumentParser(description="Incident management CLI")
    sub = parser.add_subparsers(dest="command")

    list_p = sub.add_parser("list", help="List incidents")
    list_p.add_argument("--open", action="store_true", help="Show only open incidents")

    log_p = sub.add_parser("log", help="Log a new incident manually")
    log_p.add_argument("title", help="Short title for the incident")
    log_p.add_argument("--severity", choices=["low", "medium", "high"], default="low")
    log_p.add_argument("--task-id", help="Task ID this incident is linked to")
    log_p.add_argument("--goal-id", help="Goal ID this incident is linked to")
    log_p.add_argument("--description", help="Detailed description")

    resolve_p = sub.add_parser("resolve", help="Mark an incident resolved")
    resolve_p.add_argument("prefix", help="Incident ID prefix")
    resolve_p.add_argument("--root-cause", help="Root cause summary")
    resolve_p.add_argument("--remediation", help="Remediation taken")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "list":
        cmd_list(args)
    elif args.command == "log":
        cmd_log(args)
    elif args.command == "resolve":
        cmd_resolve(args)


if __name__ == "__main__":
    main()
