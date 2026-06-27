"""
set_trust.py - Promote or demote a goal's trust level.

Trust levels control how much autonomy the worker runs with:

  supervised  - Default. Worker pauses for HITL approval before every
                medium/high-risk action. No autonomous goal creation.

  guided      - Worker auto-proceeds on low/medium risk. Pauses only for
                high-risk actions and goal completion gates.

  autonomous  - Worker runs without HITL gates. Reserved for well-tested
                recurring goals with a proven track record.

Promotion is always manual. Demotion can be triggered by a failed verifier.

Usage:
  .venv/bin/python scripts/set_trust.py <goal_id_prefix> <level>
  .venv/bin/python scripts/set_trust.py list
"""
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "tasks.db"

LEVELS = ("supervised", "guided", "autonomous")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def list_goals(conn: sqlite3.Connection) -> None:
    rows = conn.execute("""
        SELECT id, trust_level, status, description
        FROM goals
        ORDER BY created_at DESC
        LIMIT 20
    """).fetchall()
    if not rows:
        print("No goals found.")
        return
    print(f"{'ID':8}  {'Trust':12}  {'Status':10}  Description")
    print("-" * 80)
    for r in rows:
        print(f"{r['id'][:8]}  {r['trust_level']:12}  {r['status']:10}  {r['description'][:50]}")


def set_trust(conn: sqlite3.Connection, goal_prefix: str, level: str) -> None:
    if level not in LEVELS:
        print(f"Invalid level '{level}'. Must be one of: {', '.join(LEVELS)}")
        sys.exit(1)

    rows = conn.execute(
        "SELECT id, description, trust_level FROM goals WHERE id LIKE ?",
        (goal_prefix + "%",)
    ).fetchall()

    if not rows:
        print(f"No goal found matching prefix '{goal_prefix}'")
        sys.exit(1)
    if len(rows) > 1:
        print(f"Prefix '{goal_prefix}' is ambiguous ({len(rows)} matches). Use more characters.")
        for r in rows:
            print(f"  {r['id'][:8]}  {r['description'][:60]}")
        sys.exit(1)

    goal = rows[0]
    old_level = goal["trust_level"]
    if old_level == level:
        print(f"Goal {goal['id'][:8]} is already at trust level '{level}'.")
        return

    conn.execute(
        "UPDATE goals SET trust_level = ?, updated_at = ? WHERE id = ?",
        (level, utcnow(), goal["id"])
    )
    conn.commit()
    print(f"Goal {goal['id'][:8]}: {old_level} -> {level}")
    print(f"  {goal['description'][:70]}")

    if level == "autonomous":
        print("\nWarning: autonomous goals run without HITL gates. Confirm this goal has")
        print("a verified track record before running the worker against it.")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    conn = get_conn()

    if sys.argv[1] == "list":
        list_goals(conn)
        return

    if len(sys.argv) < 3:
        print("Usage: set_trust.py <goal_id_prefix> <level>   OR   set_trust.py list")
        sys.exit(1)

    goal_prefix = sys.argv[1]
    level = sys.argv[2]
    set_trust(conn, goal_prefix, level)


if __name__ == "__main__":
    main()
