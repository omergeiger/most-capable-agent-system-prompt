"""
m4_features.py - Validates Milestone 4 additions.

Checks:
  1. goals.budget_limit column exists
  2. worker.py has --goal-id and --no-hitl flags
  3. scan.py generates dashboard section in scan reports
  4. Trust gating logic: guided + low risk -> proceed; supervised + any -> block without --no-hitl
  5. Budget gate: blocks task when goal cost_usd >= budget_limit

Usage: .venv/bin/python evals/m4_features.py
"""
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "tasks.db"
PYTHON = REPO_ROOT / ".venv" / "bin" / "python"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_budget_limit_column() -> bool:
    print("Column check: goals.budget_limit exists")
    if not DB_PATH.exists():
        print("  SKIP: tasks.db not found")
        return False
    conn = sqlite3.connect(str(DB_PATH))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(goals)")}
    conn.close()
    if "budget_limit" not in cols:
        print("  FAIL: goals.budget_limit not found")
        return False
    print("  PASS")
    return True


def check_worker_flags() -> bool:
    print("Worker flags: --goal-id and --no-hitl exist in worker.py help")
    result = subprocess.run(
        [str(PYTHON), str(REPO_ROOT / "scripts" / "worker.py"), "--help"],
        capture_output=True, text=True
    )
    if "--goal-id" not in result.stdout:
        print("  FAIL: --goal-id not in worker --help")
        return False
    if "--no-hitl" not in result.stdout:
        print("  FAIL: --no-hitl not in worker --help")
        return False
    print("  PASS")
    return True


def check_scan_dashboard() -> bool:
    print("Scan dashboard: build_dashboard() function exists in scan.py")
    scan_src = (REPO_ROOT / "scripts" / "scan.py").read_text()
    if "def build_dashboard" not in scan_src:
        print("  FAIL: build_dashboard function not found in scan.py")
        return False
    print("  PASS")
    return True


def check_trust_gating() -> bool:
    print("Trust gating: importing and testing check_hitl_gate logic")
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        import importlib
        worker = importlib.import_module("worker")

        # guided + low risk -> proceed
        task_low = {"risk_level": "low"}
        goal_guided = {"trust_level": "guided"}
        ok, reason = worker.check_hitl_gate(task_low, goal_guided, no_hitl=False)
        if not ok:
            print(f"  FAIL: guided+low should proceed, got blocked: {reason}")
            return False

        # supervised + any -> block without --no-hitl
        task_any = {"risk_level": "medium"}
        goal_supervised = {"trust_level": "supervised"}
        ok, reason = worker.check_hitl_gate(task_any, goal_supervised, no_hitl=False)
        if ok:
            print(f"  FAIL: supervised+medium without --no-hitl should block, got proceed")
            return False

        # supervised + --no-hitl -> proceed
        ok, reason = worker.check_hitl_gate(task_any, goal_supervised, no_hitl=True)
        if not ok:
            print(f"  FAIL: supervised+medium with --no-hitl should proceed: {reason}")
            return False

        # autonomous -> always proceed
        goal_auto = {"trust_level": "autonomous"}
        ok, reason = worker.check_hitl_gate({"risk_level": "high"}, goal_auto, no_hitl=False)
        if not ok:
            print(f"  FAIL: autonomous+high should proceed: {reason}")
            return False

        print("  PASS: all 4 gating scenarios correct")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False
    finally:
        sys.path.pop(0)


def check_budget_gate() -> bool:
    print("Budget gate: check_budget blocks when spent >= limit")
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        import importlib
        worker = importlib.import_module("worker")

        # No budget -> always pass
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        ok, reason = worker.check_budget(conn, {}, {"id": "fake", "budget_limit": None})
        if not ok:
            print(f"  FAIL: no budget limit should pass: {reason}")
            conn.close()
            return False

        # Over budget -> block
        # Temporarily insert a test goal with spent tasks
        gid = str(uuid.uuid4())
        tid = str(uuid.uuid4())
        now = utcnow()
        conn.execute(
            "INSERT INTO goals (id, description, status, budget_limit, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (gid, "[eval] budget gate test", "active", 0.01, now, now)
        )
        conn.execute(
            "INSERT INTO tasks (id, goal_id, description, status, cost_usd, priority, risk_level, attempts, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (tid, gid, "[eval] spent task", "done", 0.05, 5, "low", 1, now, now)
        )
        conn.commit()

        goal_row = dict(conn.execute("SELECT * FROM goals WHERE id=?", (gid,)).fetchone())
        task_row = {"goal_id": gid}
        ok, reason = worker.check_budget(conn, task_row, goal_row)

        # Cleanup
        conn.execute("DELETE FROM tasks WHERE id=?", (tid,))
        conn.execute("DELETE FROM goals WHERE id=?", (gid,))
        conn.commit()
        conn.close()

        if ok:
            print(f"  FAIL: over-budget goal should block, got proceed: {reason}")
            return False

        print(f"  PASS: over-budget correctly blocked: {reason}")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False
    finally:
        sys.path.pop(0)


def main() -> bool:
    print("=== M4 Features Eval ===\n")
    results = [
        check_budget_limit_column(),
        check_worker_flags(),
        check_scan_dashboard(),
        check_trust_gating(),
        check_budget_gate(),
    ]
    passed = sum(results)
    total = len(results)
    print(f"\n--- Results: {passed}/{total} passed ---")
    return passed == total


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
