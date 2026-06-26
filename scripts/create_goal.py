"""
create_goal.py - Accept a goal, decompose into tasks, insert into tasks.db.

Usage:
  .venv/bin/python scripts/create_goal.py "Fix the failing auth unit test"
  .venv/bin/python scripts/create_goal.py --file goals/my_goal.md
  .venv/bin/python scripts/create_goal.py --interactive

The decomposition step invokes Claude Code to plan the task graph.
Each task is inserted into tasks.db as 'pending'.
"""
import argparse
import json
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "tasks.db"
SKILLS_DIR = REPO_ROOT / "skills"
LOGS_DIR = REPO_ROOT / "logs"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


DECOMPOSITION_PROMPT_TEMPLATE = """
You are a task planner for an agentic harness wrapping Claude Code.

GOAL: {goal_description}

Your job: decompose this goal into a minimal set of concrete tasks (3-7 tasks).

For each task output a JSON object on its own line with these fields:
- description: str (one clear sentence)
- scope: str (what is in scope, what is not)
- skill_tags: list[str] (e.g. ["coding", "testing", "review"])
- priority: int (1-10, higher = more urgent)
- risk_level: str ("low", "medium", or "high")
- depends_on: list[str] (descriptions of tasks this depends on - use empty list if none)
- verification_plan: str (how to verify this task is done correctly)

Rules:
- Each task must be completable in under 30 minutes
- High risk_level tasks need explicit justification in scope
- depends_on should reference task descriptions (not IDs yet)
- Do not include tasks that are already done

Output ONLY valid JSON objects, one per line. No markdown, no explanation.
"""


def get_goal_description(args: argparse.Namespace) -> str:
    if args.file:
        return Path(args.file).read_text().strip()
    if args.goal:
        return " ".join(args.goal)
    if args.interactive:
        print("Enter goal description (end with Ctrl+D):")
        return sys.stdin.read().strip()
    print("Error: provide a goal via positional args, --file, or --interactive")
    sys.exit(1)


def decompose_goal(goal_description: str) -> list[dict]:
    """Invoke Claude Code to decompose a goal into tasks."""
    prompt = DECOMPOSITION_PROMPT_TEMPLATE.format(goal_description=goal_description)
    result = subprocess.run(
        ["claude", "--print", prompt],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        print(f"Claude error: {result.stderr}")
        sys.exit(1)

    tasks = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                tasks.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return tasks


def insert_goal_and_tasks(goal_description: str, raw_tasks: list[dict],
                           project_id: str | None = None) -> str:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys=ON")
    now = utcnow()

    goal_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO goals (id, description, project_id, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (goal_id, goal_description, project_id, "active", now, now),
    )

    # First pass: assign IDs and build description->ID map
    task_records = []
    desc_to_id = {}
    for t in raw_tasks:
        tid = str(uuid.uuid4())
        desc_to_id[t["description"]] = tid
        task_records.append((tid, t))

    # Second pass: resolve depends_on from descriptions to IDs
    for tid, t in task_records:
        dep_ids = []
        for dep_desc in t.get("depends_on", []):
            for desc, dep_id in desc_to_id.items():
                if dep_desc.lower() in desc.lower() or desc.lower() in dep_desc.lower():
                    dep_ids.append(dep_id)
                    break

        conn.execute("""
            INSERT INTO tasks
            (id, goal_id, project_id, description, scope, skill_tags, status,
             depends_on, priority, risk_level, verification_plan,
             attempts, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            tid, goal_id, project_id,
            t["description"],
            t.get("scope"),
            json.dumps(t.get("skill_tags", [])),
            "pending",
            json.dumps(dep_ids),
            t.get("priority", 5),
            t.get("risk_level", "low"),
            t.get("verification_plan"),
            0, now, now,
        ))

    conn.commit()
    conn.close()
    return goal_id


def main():
    parser = argparse.ArgumentParser(description="Create a goal and decompose into tasks")
    parser.add_argument("goal", nargs="*", help="Goal description")
    parser.add_argument("--file", help="Path to markdown file with goal description")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--project", help="Project ID to associate with this goal")
    parser.add_argument("--dry-run", action="store_true", help="Print tasks without inserting")
    args = parser.parse_args()

    goal_description = get_goal_description(args)
    print(f"Goal: {goal_description}\n")
    print("Decomposing into tasks via Claude Code...")

    raw_tasks = decompose_goal(goal_description)
    if not raw_tasks:
        print("Error: no tasks returned from decomposition")
        sys.exit(1)

    print(f"Got {len(raw_tasks)} tasks:")
    for i, t in enumerate(raw_tasks, 1):
        risk = t.get("risk_level", "low")
        print(f"  {i}. [{risk}] {t['description']}")

    if args.dry_run:
        print("\n(dry-run: not inserting into DB)")
        return

    goal_id = insert_goal_and_tasks(goal_description, raw_tasks, args.project)
    print(f"\nInserted goal {goal_id} with {len(raw_tasks)} tasks into tasks.db")
    print("Run scripts/worker.py to start execution.")


if __name__ == "__main__":
    main()
