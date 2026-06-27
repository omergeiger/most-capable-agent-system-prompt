"""
worker.py - Main harness worker loop.

Polls tasks.db for pending tasks, executes via Claude Code CLI,
runs a separate verifier subagent, records evidence, updates memory.

Usage: .venv/bin/python scripts/worker.py [--once] [--task-id TASK_ID]
  --once      Run one iteration and exit (useful for testing)
  --task-id   Claim a specific task by ID instead of polling
"""
import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "tasks.db"
LOGS_DIR = REPO_ROOT / "logs"
ARTIFACTS_DIR = REPO_ROOT / "artifacts"
SKILLS_DIR = REPO_ROOT / "skills"
PROJECTS_DIR = REPO_ROOT / "projects"
HARNESS_PROJECT_DIR = PROJECTS_DIR / "harness-v1"

POLL_INTERVAL = 30
TASK_TIMEOUT = 1800  # 30 minutes
MAX_ATTEMPTS = 3


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_prerequisites() -> None:
    if not shutil.which("claude"):
        print("ERROR: 'claude' not found on PATH. Install Claude Code CLI first.")
        sys.exit(1)
    if not DB_PATH.exists():
        print(f"ERROR: tasks.db not found at {DB_PATH}. Run scripts/init_db.py first.")
        sys.exit(1)
    LOGS_DIR.mkdir(exist_ok=True)
    ARTIFACTS_DIR.mkdir(exist_ok=True)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def claim_task(conn: sqlite3.Connection, task_id: str | None = None,
               goal_id: str | None = None) -> dict | None:
    """Atomically claim one pending task. Returns task dict or None."""
    if task_id:
        filter_clause = f"id = '{task_id}'"
    else:
        goal_filter = f"AND goal_id = '{goal_id}'" if goal_id else ""
        filter_clause = f"""id = (SELECT id FROM tasks WHERE
            status = 'pending'
            {goal_filter}
            AND (depends_on IS NULL OR depends_on = '[]'
                 OR NOT EXISTS (
                     SELECT 1 FROM json_each(tasks.depends_on) dep
                     INNER JOIN tasks t2 ON t2.id = dep.value
                     WHERE t2.status NOT IN ('done')
                 ))
            ORDER BY priority DESC, created_at ASC
            LIMIT 1)"""

    cur = conn.execute(f"""
        UPDATE tasks
        SET status = 'locked',
            locked_at = ?,
            attempts = attempts + 1,
            updated_at = ?
        WHERE {filter_clause}
          AND status = 'pending'
        RETURNING *
    """, (utcnow(), utcnow()))

    row = cur.fetchone()
    conn.commit()
    return dict(row) if row else None


def load_skill_profiles(skill_tags: list[str]) -> tuple[str, list[str]]:
    """Load relevant skill files based on task skill_tags.

    Parses the '**Trigger conditions:**' line from each skill file and matches
    against the task's skill_tags. Returns (combined_content, loaded_file_names).
    """
    tag_set = {t.lower() for t in skill_tags}
    loaded = []
    profiles = []

    for skill_file in sorted(SKILLS_DIR.glob("*.md")):
        content = skill_file.read_text()
        triggers: set[str] = set()
        for line in content.splitlines():
            if "Trigger conditions:" in line:
                # Extract all quoted tokens: **Trigger conditions:** ... "coding", "review" ...
                for match in re.findall(r'"([^"]+)"', line):
                    triggers.add(match.strip().lower())
                # Fallback: if no quoted tokens, split after last colon on commas
                if not triggers:
                    after_colon = line.split(":", 1)[-1]
                    for token in after_colon.split(","):
                        t = re.sub(r"[^a-z0-9_]", "", token.strip().lower())
                        if t:
                            triggers.add(t)
                break
        if triggers & tag_set:
            loaded.append(skill_file.name)
            profiles.append(content)

    combined = "\n\n---\n\n".join(profiles) if profiles else ""
    return combined, loaded


def build_executor_prompt(task: dict, skill_context: str) -> str:
    task_artifacts_dir = ARTIFACTS_DIR / task["id"]
    parts = [
        f"# Task Execution\n\n**Task ID:** {task['id']}",
        f"**Goal:** {task.get('goal_id', 'standalone')}",
        f"**Description:** {task['description']}",
    ]
    if task.get("scope"):
        parts.append(f"**Scope:** {task['scope']}")
    if task.get("context"):
        parts.append(f"**Context:** {task['context']}")
    if task.get("verification_plan"):
        parts.append(f"**Verification plan:** {task['verification_plan']}")
    if skill_context:
        parts.append(f"\n## Skill Profile\n\n{skill_context}")
    parts.append(f"\n## Artifact Instructions\n\nWrite any outputs or evidence to: {task_artifacts_dir}/\nCreate that directory if it does not exist.\nWrite a brief `completion_note.md` there summarizing what you did.")
    return "\n\n".join(parts)


def build_verifier_prompt(task: dict, task_artifacts_dir: Path) -> str:
    return f"""# Verification Task

You are a skeptical verifier with a clean context. You did NOT execute this task.
Your job is to independently check whether it was done correctly.

**Task:** {task['description']}
**Verification plan:** {task.get('verification_plan', 'Check that the task description was fulfilled and there is evidence.')}
**Artifacts directory:** {task_artifacts_dir}

## Instructions

1. Check the artifacts directory for evidence of completion
2. Read completion_note.md if it exists
3. Apply the verification plan
4. Write your result to: {task_artifacts_dir}/verification.md

Use this exact format in verification.md:
```
# Verification Result
Status: PASS
Reason: <one clear paragraph>
Evidence checked:
- <item 1>
- <item 2>
```

or:
```
# Verification Result
Status: FAIL
Reason: <one clear paragraph explaining what is missing or wrong>
Evidence checked:
- <item 1>
```

Only output to that file. Do not self-certify.
"""


def execute_task(task: dict) -> tuple[bool, str]:
    """Run the task executor. Returns (success, log_path)."""
    task_artifacts_dir = ARTIFACTS_DIR / task["id"]
    task_artifacts_dir.mkdir(parents=True, exist_ok=True)

    skill_tags = json.loads(task.get("skill_tags") or "[]")
    skill_context, loaded_skills = load_skill_profiles(skill_tags)
    prompt = build_executor_prompt(task, skill_context)

    log_path = LOGS_DIR / f"exec_{task['id']}.md"
    skills_note = f"Skills loaded: {', '.join(loaded_skills)}" if loaded_skills else "Skills loaded: none"

    tokens_used = 0
    cost_usd = 0.0
    duration_ms = 0

    try:
        result = subprocess.run(
            ["claude", "--print", "--output-format", "json", prompt],
            capture_output=True, text=True,
            timeout=TASK_TIMEOUT, cwd=REPO_ROOT,
        )
        success = result.returncode == 0
        try:
            parsed = json.loads(result.stdout)
            output = parsed.get("result", result.stdout)
            usage = parsed.get("usage", {})
            tokens_used = (
                usage.get("input_tokens", 0)
                + usage.get("output_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
            )
            cost_usd = parsed.get("total_cost_usd", 0.0) or 0.0
            duration_ms = parsed.get("duration_ms", 0) or 0
        except (json.JSONDecodeError, AttributeError):
            output = result.stdout
        if result.stderr:
            output += f"\n\nSTDERR:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        success = False
        output = "TIMEOUT: task exceeded 30 minutes"

    log_path.write_text(
        f"# Execution Log: {task['id']}\n\n"
        f"**Task:** {task['description']}\n"
        f"**Time:** {utcnow()}\n"
        f"**Success:** {success}\n"
        f"**{skills_note}**\n"
        f"**Tokens used:** {tokens_used} | **Cost:** ${cost_usd:.4f} | **Duration:** {duration_ms}ms\n\n"
        f"## Output\n\n{output}\n"
    )
    return success, str(log_path), tokens_used, cost_usd


def verify_task(task: dict) -> tuple[bool, str, int, float]:
    """Run verifier subagent. Returns (verified, reason, tokens_used, cost_usd)."""
    task_artifacts_dir = ARTIFACTS_DIR / task["id"]
    verification_file = task_artifacts_dir / "verification.md"
    prompt = build_verifier_prompt(task, task_artifacts_dir)

    tokens_used = 0
    cost_usd = 0.0

    try:
        result = subprocess.run(
            ["claude", "--print", "--output-format", "json", prompt],
            capture_output=True, text=True,
            timeout=300, cwd=REPO_ROOT,
        )
        try:
            parsed = json.loads(result.stdout)
            usage = parsed.get("usage", {})
            tokens_used = (
                usage.get("input_tokens", 0)
                + usage.get("output_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
            )
            cost_usd = parsed.get("total_cost_usd", 0.0) or 0.0
        except (json.JSONDecodeError, AttributeError):
            pass
    except subprocess.TimeoutExpired:
        return False, "Verifier timed out", 0, 0.0

    if not verification_file.exists():
        return False, "Verifier did not write verification.md", tokens_used, cost_usd

    content = verification_file.read_text()
    passed = "Status: PASS" in content
    reason = "No reason extracted"
    for line in content.splitlines():
        if line.startswith("Reason:"):
            reason = line[7:].strip()
            break
    return passed, reason, tokens_used, cost_usd


def update_task(conn: sqlite3.Connection, task_id: str, status: str,
                evidence: dict | None = None, artifacts: list | None = None,
                tokens_used: int = 0, cost_usd: float = 0.0) -> None:
    conn.execute("""
        UPDATE tasks
        SET status = ?, evidence = ?, artifacts = ?, updated_at = ?,
            tokens_used = tokens_used + ?,
            cost_usd = cost_usd + ?,
            completed_at = CASE WHEN ? IN ('done', 'failed') THEN ? ELSE completed_at END
        WHERE id = ?
    """, (
        status,
        json.dumps(evidence) if evidence else None,
        json.dumps(artifacts) if artifacts else None,
        utcnow(), tokens_used, cost_usd, status, utcnow(), task_id,
    ))
    conn.commit()


def append_episodic_memory(task: dict, verified: bool, reason: str) -> None:
    """Append a brief episodic log entry to logs/episodic.md."""
    episodic_path = LOGS_DIR / "episodic.md"
    entry = (
        f"\n## {utcnow()} - Task {task['id'][:8]}\n\n"
        f"**Goal:** {task.get('goal_id', 'standalone')[:8] if task.get('goal_id') else 'none'}\n"
        f"**Task:** {task['description']}\n"
        f"**Verified:** {'PASS' if verified else 'FAIL'}\n"
        f"**Reason:** {reason}\n"
    )
    with episodic_path.open("a") as f:
        f.write(entry)


def get_goal(conn: sqlite3.Connection, goal_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM goals WHERE id = ?", (goal_id,)
    ).fetchone()
    return dict(row) if row else None


def get_goal_spent(conn: sqlite3.Connection, goal_id: str) -> float:
    """Sum cost_usd already spent on done/failed tasks for this goal."""
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM tasks WHERE goal_id = ? AND status IN ('done', 'failed')",
        (goal_id,)
    ).fetchone()
    return float(row[0])


def check_hitl_gate(task: dict, goal: dict | None, no_hitl: bool) -> tuple[bool, str]:
    """Return (can_proceed, reason). Blocks tasks that require human approval."""
    trust_level = (goal or {}).get("trust_level", "supervised")
    risk = task.get("risk_level", "low")

    if trust_level == "autonomous":
        return True, "autonomous trust: no gate"

    if trust_level == "guided":
        if risk in ("low", "medium"):
            return True, f"guided trust: auto-proceed ({risk} risk)"
        if no_hitl:
            return True, f"guided trust: --no-hitl override ({risk} risk)"
        return False, f"guided trust: HITL required for {risk}-risk task (pass --no-hitl to override)"

    # supervised
    if no_hitl:
        return True, "supervised trust: --no-hitl override"
    return False, "supervised trust: HITL required (pass --no-hitl to override)"


def check_budget(conn: sqlite3.Connection, task: dict, goal: dict | None) -> tuple[bool, str]:
    """Return (within_budget, reason). Blocks tasks if goal budget would be exceeded."""
    if goal is None:
        return True, "no goal"
    budget = goal.get("budget_limit")
    if budget is None:
        return True, "no budget limit set"
    spent = get_goal_spent(conn, goal["id"])
    if spent >= budget:
        return False, f"goal budget ${budget:.4f} already spent (${spent:.4f} used)"
    return True, f"within budget (${spent:.4f}/${budget:.4f} used)"


def run_once(conn: sqlite3.Connection, specific_task_id: str | None = None,
             goal_id: str | None = None, no_hitl: bool = False) -> bool:
    """Run one worker iteration. Returns True if a task was processed."""
    task = claim_task(conn, specific_task_id, goal_id)
    if task is None:
        return False

    task_id = task["id"]
    print(f"[worker] Claimed task {task_id[:8]}: {task['description'][:70]}")

    goal = get_goal(conn, task["goal_id"]) if task.get("goal_id") else None

    # Trust-level gate
    can_run, gate_reason = check_hitl_gate(task, goal, no_hitl)
    if not can_run:
        print(f"[worker] HITL gate: {gate_reason}")
        conn.execute(
            "UPDATE tasks SET status='pending', escalation_reason=?, updated_at=? WHERE id=?",
            (gate_reason, utcnow(), task_id)
        )
        conn.commit()
        return True  # "processed" - just not executed

    # Budget gate
    within_budget, budget_reason = check_budget(conn, task, goal)
    if not within_budget:
        print(f"[worker] Budget exceeded: {budget_reason}")
        conn.execute(
            "UPDATE tasks SET status='blocked', escalation_reason=?, updated_at=? WHERE id=?",
            (f"BUDGET EXCEEDED: {budget_reason}", utcnow(), task_id)
        )
        conn.commit()
        return True

    print(f"[worker] Gate check: {gate_reason} | {budget_reason}")
    update_task(conn, task_id, "running")

    try:
        success, log_path, exec_tokens, exec_cost = execute_task(task)
        verified, reason, verify_tokens, verify_cost = verify_task(task)

        total_tokens = exec_tokens + verify_tokens
        total_cost = exec_cost + verify_cost

        if success and verified:
            final_status = "done"
        elif task["attempts"] >= MAX_ATTEMPTS:
            final_status = "failed"
            reason = f"Max attempts ({MAX_ATTEMPTS}) reached. Last: {reason}"
        else:
            final_status = "pending"

        evidence = {
            "execution_success": success,
            "verified": verified,
            "verification_reason": reason,
            "log_path": log_path,
            "attempt": task["attempts"],
            "tokens_used": total_tokens,
            "cost_usd": round(total_cost, 6),
        }
        artifacts_list = [str(ARTIFACTS_DIR / task_id)]

        update_task(conn, task_id, final_status, evidence=evidence, artifacts=artifacts_list,
                    tokens_used=total_tokens, cost_usd=total_cost)
        append_episodic_memory(task, verified, reason)
        cost_str = f"${total_cost:.4f}" if total_cost else "n/a"
        print(f"[worker] Task {task_id[:8]} -> {final_status}. Verified: {verified}. Tokens: {total_tokens} ({cost_str})")
        print(f"         {reason}")

    except Exception as e:
        update_task(conn, task_id, "failed", evidence={"error": str(e)})
        print(f"[worker] Task {task_id[:8]} raised: {e}")

    return True


def worker_loop(once: bool = False, specific_task_id: str | None = None,
                goal_id: str | None = None, no_hitl: bool = False) -> None:
    check_prerequisites()
    conn = get_connection()
    trust_note = " no-hitl" if no_hitl else ""
    goal_note = f" goal={goal_id[:8]}" if goal_id else ""
    print(f"[worker] Started. DB: {DB_PATH}. Poll: {POLL_INTERVAL}s.{goal_note}{trust_note}")

    while True:
        processed = run_once(conn, specific_task_id, goal_id=goal_id, no_hitl=no_hitl)

        if once or specific_task_id:
            print("[worker] --once flag or specific task: exiting.")
            break

        if goal_id and not processed:
            print(f"[worker] No more claimable tasks for goal {goal_id[:8]}. Exiting.")
            break

        if not processed:
            print(f"[worker] No claimable tasks. Sleeping {POLL_INTERVAL}s...")
            time.sleep(POLL_INTERVAL)


def main():
    parser = argparse.ArgumentParser(description="Harness worker loop")
    parser.add_argument("--once", action="store_true", help="Run one iteration and exit")
    parser.add_argument("--task-id", help="Claim a specific task by ID")
    parser.add_argument("--goal-id", help="Run all tasks for this goal (prefix OK)")
    parser.add_argument("--no-hitl", action="store_true",
                        help="Bypass HITL gates (guided: allows high-risk; supervised: allows all)")
    args = parser.parse_args()

    # Resolve goal-id prefix to full ID if needed
    goal_id = None
    if args.goal_id:
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(str(DB_PATH))
        rows = conn.execute(
            "SELECT id FROM goals WHERE id LIKE ?", (args.goal_id + "%",)
        ).fetchall()
        conn.close()
        if not rows:
            print(f"No goal found matching prefix '{args.goal_id}'")
            sys.exit(1)
        if len(rows) > 1:
            print(f"Prefix '{args.goal_id}' is ambiguous. Use more characters.")
            sys.exit(1)
        goal_id = rows[0][0]

    worker_loop(once=args.once, specific_task_id=args.task_id,
                goal_id=goal_id, no_hitl=args.no_hitl)


if __name__ == "__main__":
    main()
