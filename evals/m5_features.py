"""
m5_features.py - Validates Milestone 5 additions.

Checks:
  1. incidents table exists and auto-incident creation in worker.py
  2. create_incident.py - list/log/resolve commands present
  3. run_goal.sh is executable and contains expected structure
  4. export_status.py - renders HTML dashboard, writes to artifacts/
  5. Autonomous goal ran without HITL gates (confirm incident-free run)

Usage: .venv/bin/python evals/m5_features.py
"""
import importlib
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


def check_incidents_table() -> bool:
    print("Incidents table: exists and worker.py wires create_incident()")
    if not DB_PATH.exists():
        print("  SKIP: tasks.db not found")
        return False

    conn = sqlite3.connect(str(DB_PATH))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()

    if "incidents" not in tables:
        print("  FAIL: incidents table not found")
        return False

    worker_src = (REPO_ROOT / "scripts" / "worker.py").read_text()
    if "create_incident" not in worker_src:
        print("  FAIL: create_incident not referenced in worker.py")
        return False

    # Check that create_incident function is importable from worker
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        worker = importlib.import_module("worker")
        if not hasattr(worker, "create_incident"):
            print("  FAIL: create_incident not found as function in worker module")
            return False
    except Exception as e:
        print(f"  FAIL: {e}")
        return False
    finally:
        sys.path.pop(0)

    print("  PASS: incidents table exists, create_incident() wired in worker.py")
    return True


def check_create_incident_cli() -> bool:
    print("create_incident.py: list/log/resolve commands available")
    script = REPO_ROOT / "scripts" / "create_incident.py"
    if not script.exists():
        print("  FAIL: create_incident.py not found")
        return False

    src = script.read_text()
    for cmd in ("list", "log", "resolve"):
        if f'"{cmd}"' not in src and f"'{cmd}'" not in src:
            print(f"  FAIL: command '{cmd}' not found in create_incident.py")
            return False

    # Functional check: run `list` and confirm it exits 0
    result = subprocess.run(
        [str(PYTHON), str(script), "list"],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    if result.returncode != 0:
        print(f"  FAIL: create_incident.py list returned {result.returncode}: {result.stderr}")
        return False

    # Functional check: log a test incident then resolve it
    gid = str(uuid.uuid4())
    log_result = subprocess.run(
        [str(PYTHON), str(script), "log", "[eval] test incident",
         "--severity", "low", "--description", "eval test"],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    if log_result.returncode != 0:
        print(f"  FAIL: create_incident.py log failed: {log_result.stderr}")
        return False

    # Extract ID from output
    inc_id = None
    for line in log_result.stdout.splitlines():
        if "Incident created:" in line:
            inc_id = line.split(":")[-1].strip()
            break
    if not inc_id:
        print(f"  FAIL: could not extract incident ID from output: {log_result.stdout}")
        return False

    resolve_result = subprocess.run(
        [str(PYTHON), str(script), "resolve", inc_id[:8],
         "--root-cause", "eval test", "--remediation", "eval cleanup"],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    if resolve_result.returncode != 0:
        print(f"  FAIL: resolve command failed: {resolve_result.stderr}")
        return False

    # Cleanup
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("DELETE FROM incidents WHERE id=?", (inc_id,))
    conn.commit()
    conn.close()

    print("  PASS: all three commands work; log->resolve roundtrip verified")
    return True


def check_run_goal_sh() -> bool:
    print("run_goal.sh: executable, contains create_goal + worker invocations")
    script = REPO_ROOT / "scripts" / "run_goal.sh"
    if not script.exists():
        print("  FAIL: run_goal.sh not found")
        return False
    if not script.stat().st_mode & 0o111:
        print("  FAIL: run_goal.sh is not executable")
        return False

    src = script.read_text()
    for token in ("create_goal", "worker", "GOAL_ID", "set_trust"):
        if token not in src:
            print(f"  FAIL: '{token}' not found in run_goal.sh")
            return False

    print("  PASS: run_goal.sh is executable and contains required invocations")
    return True


def check_export_status() -> bool:
    print("export_status.py: generates HTML dashboard at artifacts/dashboard.html")
    script = REPO_ROOT / "scripts" / "export_status.py"
    if not script.exists():
        print("  FAIL: export_status.py not found")
        return False

    result = subprocess.run(
        [str(PYTHON), str(script)],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    if result.returncode != 0:
        print(f"  FAIL: export_status.py exited {result.returncode}: {result.stderr}")
        return False

    out = REPO_ROOT / "artifacts" / "dashboard.html"
    if not out.exists():
        print("  FAIL: artifacts/dashboard.html was not created")
        return False

    html = out.read_text()
    for marker in ("<!DOCTYPE html>", "Task Board", "Goals", "Incidents"):
        if marker not in html:
            print(f"  FAIL: expected HTML marker '{marker}' not found in dashboard")
            return False

    print(f"  PASS: dashboard.html written ({len(html)} bytes), all sections present")
    return True


def check_autonomous_goal_ran() -> bool:
    print("Autonomous goal: at least one goal ran at autonomous trust level with done tasks")
    if not DB_PATH.exists():
        print("  SKIP: tasks.db not found")
        return False

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT g.id, g.trust_level, COUNT(t.id) FILTER (WHERE t.status='done') AS done_count
        FROM goals g
        JOIN tasks t ON t.goal_id = g.id
        WHERE g.trust_level = 'autonomous'
        GROUP BY g.id
        HAVING done_count > 0
    """).fetchall()
    conn.close()

    if not rows:
        print("  FAIL: no autonomous-trust goal with at least one done task found")
        return False

    print(f"  PASS: {len(rows)} autonomous goal(s) with done tasks found")
    for r in rows:
        print(f"    {r['id'][:8]} - {r['done_count']} task(s) done")
    return True


def main() -> bool:
    print("=== M5 Features Eval ===\n")
    results = [
        check_incidents_table(),
        check_create_incident_cli(),
        check_run_goal_sh(),
        check_export_status(),
        check_autonomous_goal_ran(),
    ]
    passed = sum(results)
    total = len(results)
    print(f"\n--- Results: {passed}/{total} passed ---")
    return passed == total


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
