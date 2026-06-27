"""
m3_features.py - Validates Milestone 3 additions are present and functional.

Checks:
  1. tasks.cost_usd column exists
  2. goals.trust_level column exists with correct default
  3. skills/ops_task.md exists and has required sections
  4. scripts/set_trust.py exists and lists goals without crashing
  5. scripts/run_scan.sh exists and is executable

Usage: .venv/bin/python evals/m3_features.py
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "tasks.db"


def check_db_columns() -> bool:
    print("Column check: cost_usd in tasks, trust_level in goals")
    if not DB_PATH.exists():
        print("  SKIP: tasks.db not found")
        return False
    conn = sqlite3.connect(str(DB_PATH))
    task_cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)")}
    goal_cols = {r[1] for r in conn.execute("PRAGMA table_info(goals)")}
    conn.close()

    missing = []
    if "cost_usd" not in task_cols:
        missing.append("tasks.cost_usd")
    if "trust_level" not in goal_cols:
        missing.append("goals.trust_level")

    if missing:
        print(f"  FAIL: missing columns: {missing}")
        return False
    print("  PASS: both columns present")
    return True


def check_trust_default() -> bool:
    print("Trust level default: goals.trust_level defaults to 'supervised'")
    if not DB_PATH.exists():
        print("  SKIP: tasks.db not found")
        return False
    conn = sqlite3.connect(str(DB_PATH))
    col_info = conn.execute("PRAGMA table_info(goals)").fetchall()
    conn.close()
    for row in col_info:
        if row[1] == "trust_level":
            if row[4] == "'supervised'":
                print("  PASS: default is 'supervised'")
                return True
            else:
                print(f"  FAIL: default is '{row[4]}', expected 'supervised'")
                return False
    print("  FAIL: trust_level column not found")
    return False


def check_ops_skill() -> bool:
    print("Ops skill: skills/ops_task.md exists with required sections")
    skill_path = REPO_ROOT / "skills" / "ops_task.md"
    if not skill_path.exists():
        print("  FAIL: skills/ops_task.md not found")
        return False
    content = skill_path.read_text()
    required = ["## Mindset", "## Standard Procedure", "## Verification Checklist", "## Output Format"]
    missing = [s for s in required if s not in content]
    if missing:
        print(f"  FAIL: missing sections: {missing}")
        return False
    print("  PASS: all required sections present")
    return True


def check_set_trust_script() -> bool:
    print("set_trust.py: script exists and runs without error")
    script = REPO_ROOT / "scripts" / "set_trust.py"
    if not script.exists():
        print("  FAIL: scripts/set_trust.py not found")
        return False
    python = REPO_ROOT / ".venv" / "bin" / "python"
    result = subprocess.run(
        [str(python), str(script), "list"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        print(f"  FAIL: set_trust.py list exited {result.returncode}: {result.stderr[:100]}")
        return False
    print("  PASS: set_trust.py list ran successfully")
    return True


def check_scan_script() -> bool:
    print("run_scan.sh: script exists and is executable")
    script = REPO_ROOT / "scripts" / "run_scan.sh"
    if not script.exists():
        print("  FAIL: scripts/run_scan.sh not found")
        return False
    if not os.access(script, os.X_OK):
        print("  FAIL: run_scan.sh is not executable")
        return False
    print("  PASS: run_scan.sh exists and is executable")
    return True


def main() -> bool:
    print("=== M3 Features Eval ===\n")
    results = [
        check_db_columns(),
        check_trust_default(),
        check_ops_skill(),
        check_set_trust_script(),
        check_scan_script(),
    ]
    passed = sum(results)
    total = len(results)
    print(f"\n--- Results: {passed}/{total} passed ---")
    return passed == total


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
