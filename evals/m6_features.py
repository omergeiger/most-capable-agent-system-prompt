"""
m6_features.py - Validates Milestone 6 additions.

Checks:
  1. watchdog.py exists and contains stuck-task detection + reset + incident creation
  2. watchdog functional: insert a stuck task, run watchdog, confirm reset + incident
  3. escalate_incidents.py exists with low->medium->high logic
  4. escalation functional: create old incident, escalate, confirm severity change
  5. Concurrent claim atomicity: two threads race to claim same task, only one wins

Usage: .venv/bin/python evals/m6_features.py
"""
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "tasks.db"
PYTHON = REPO_ROOT / ".venv" / "bin" / "python"

sys.path.insert(0, str(REPO_ROOT / "scripts"))


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def check_watchdog_script() -> bool:
    print("watchdog.py: exists and contains required logic")
    script = REPO_ROOT / "scripts" / "watchdog.py"
    if not script.exists():
        print("  FAIL: watchdog.py not found")
        return False

    src = script.read_text()
    required = ["locked", "running", "reset", "create_incident", "STUCK_THRESHOLD"]
    for token in required:
        if token not in src:
            print(f"  FAIL: '{token}' not found in watchdog.py")
            return False

    print("  PASS: watchdog.py present with all required logic tokens")
    return True


def check_watchdog_functional() -> bool:
    print("watchdog functional: stuck task gets reset to pending + incident created")
    if not DB_PATH.exists():
        print("  SKIP: tasks.db not found")
        return False

    conn = get_connection()

    # Insert a dummy goal so the task foreign key is satisfiable (goal is nullable)
    test_task_id = str(uuid.uuid4())
    old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    conn.execute(
        """INSERT INTO tasks (id, description, status, attempts, priority, risk_level,
                             created_at, updated_at, locked_at)
           VALUES (?, '[eval-m6] watchdog test stuck task', 'locked', 1, 5, 'low', ?, ?, ?)""",
        (test_task_id, old_time, old_time, old_time)
    )
    conn.commit()

    # Count incidents before
    inc_before = conn.execute("SELECT COUNT(*) FROM incidents WHERE task_id = ?",
                              (test_task_id,)).fetchone()[0]

    # Run watchdog with 30-min threshold (our task is 2h old, so it should be caught)
    try:
        import importlib
        watchdog = importlib.import_module("watchdog")
        importlib.reload(watchdog)
        affected = watchdog.run_watchdog(threshold_minutes=30, dry_run=False)
    except Exception as e:
        conn.execute("DELETE FROM tasks WHERE id=?", (test_task_id,))
        conn.commit()
        conn.close()
        print(f"  FAIL: watchdog import/run error: {e}")
        return False

    # Verify task was reset
    row = conn.execute("SELECT status FROM tasks WHERE id=?", (test_task_id,)).fetchone()
    if not row:
        print("  FAIL: test task not found after watchdog run")
        conn.close()
        return False

    if row["status"] != "pending":
        print(f"  FAIL: task status is '{row['status']}', expected 'pending'")
        conn.execute("DELETE FROM tasks WHERE id=?", (test_task_id,))
        conn.commit()
        conn.close()
        return False

    # Verify incident was created
    inc_after = conn.execute("SELECT COUNT(*) FROM incidents WHERE task_id = ?",
                             (test_task_id,)).fetchone()[0]
    if inc_after <= inc_before:
        print(f"  FAIL: no new incident created (before={inc_before}, after={inc_after})")
        conn.execute("DELETE FROM tasks WHERE id=?", (test_task_id,))
        conn.commit()
        conn.close()
        return False

    # Cleanup
    conn.execute("DELETE FROM incidents WHERE task_id=?", (test_task_id,))
    conn.execute("DELETE FROM tasks WHERE id=?", (test_task_id,))
    conn.commit()
    conn.close()

    print(f"  PASS: task reset to pending, incident created (caught in affected list: "
          f"{any(t['id'] == test_task_id for t in affected)})")
    return True


def check_escalation_script() -> bool:
    print("escalate_incidents.py: exists with severity escalation logic")
    script = REPO_ROOT / "scripts" / "escalate_incidents.py"
    if not script.exists():
        print("  FAIL: escalate_incidents.py not found")
        return False

    src = script.read_text()
    required = ["low", "medium", "high", "escalate", "NEXT_SEVERITY"]
    for token in required:
        if token not in src:
            print(f"  FAIL: '{token}' not found in escalate_incidents.py")
            return False

    print("  PASS: escalate_incidents.py present with all required logic tokens")
    return True


def check_escalation_functional() -> bool:
    print("escalation functional: old low-severity incident escalates to medium")
    if not DB_PATH.exists():
        print("  SKIP: tasks.db not found")
        return False

    conn = get_connection()

    # Ensure escalation columns exist
    try:
        import importlib
        escalate = importlib.import_module("escalate_incidents")
        importlib.reload(escalate)
        escalate.ensure_escalation_columns(conn)
    except Exception as e:
        conn.close()
        print(f"  FAIL: escalate_incidents import error: {e}")
        return False

    # Create an old low-severity incident (3 hours old)
    inc_id = str(uuid.uuid4())
    old_time = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    conn.execute(
        """INSERT INTO incidents (id, severity, title, description, status, created_at)
           VALUES (?, 'low', '[eval-m6] escalation test incident', 'eval test', 'open', ?)""",
        (inc_id, old_time)
    )
    conn.commit()

    # Run escalation with 1h threshold for low
    try:
        escalated = escalate.run_escalation(low_hours=1, medium_hours=2, dry_run=False)
    except Exception as e:
        conn.execute("DELETE FROM incidents WHERE id=?", (inc_id,))
        conn.commit()
        conn.close()
        print(f"  FAIL: run_escalation error: {e}")
        return False

    # Check severity was updated
    row = conn.execute("SELECT severity, escalation_count FROM incidents WHERE id=?",
                       (inc_id,)).fetchone()
    if not row:
        print("  FAIL: test incident not found after escalation")
        conn.close()
        return False

    if row["severity"] != "medium":
        print(f"  FAIL: severity is '{row['severity']}', expected 'medium'")
        conn.execute("DELETE FROM incidents WHERE id=?", (inc_id,))
        conn.commit()
        conn.close()
        return False

    if (row["escalation_count"] or 0) < 1:
        print(f"  FAIL: escalation_count is {row['escalation_count']}, expected >= 1")
        conn.execute("DELETE FROM incidents WHERE id=?", (inc_id,))
        conn.commit()
        conn.close()
        return False

    # Cleanup
    conn.execute("DELETE FROM incidents WHERE id=?", (inc_id,))
    conn.commit()
    conn.close()

    print(f"  PASS: incident escalated low -> medium, escalation_count incremented")
    return True


def check_concurrent_claim_atomicity() -> bool:
    """Spawn N threads all racing to claim the same task. Confirm exactly one wins."""
    print("Concurrent claim atomicity: N threads race to claim same task, exactly one wins")
    if not DB_PATH.exists():
        print("  SKIP: tasks.db not found")
        return False

    # Insert a dummy goal and task
    conn0 = get_connection()
    test_goal_id = str(uuid.uuid4())
    test_task_id = str(uuid.uuid4())
    now = utcnow()
    conn0.execute(
        """INSERT INTO goals (id, description, status, created_at, updated_at)
           VALUES (?, '[eval-m6] concurrency test goal', 'active', ?, ?)""",
        (test_goal_id, now, now)
    )
    conn0.execute(
        """INSERT INTO tasks (id, goal_id, description, status, attempts, priority,
                             risk_level, created_at, updated_at)
           VALUES (?, ?, '[eval-m6] concurrency test task', 'pending', 0, 5, 'low', ?, ?)""",
        (test_task_id, test_goal_id, now, now)
    )
    conn0.commit()
    conn0.close()

    # Import claim_task from worker
    try:
        import importlib
        worker = importlib.import_module("worker")
        importlib.reload(worker)
    except Exception as e:
        print(f"  FAIL: worker import error: {e}")
        return False

    NUM_THREADS = 8
    results = []
    errors = []

    def try_claim():
        try:
            c = worker.get_connection()
            task = worker.claim_task(c, task_id=test_task_id)
            results.append(task is not None)
            c.close()
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=try_claim) for _ in range(NUM_THREADS)]
    # Start all at once
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    if errors:
        print(f"  FAIL: {len(errors)} thread error(s): {errors[0]}")
        return False

    wins = sum(1 for r in results if r)
    losses = sum(1 for r in results if not r)

    # Cleanup
    conn1 = get_connection()
    conn1.execute("DELETE FROM tasks WHERE id=?", (test_task_id,))
    conn1.execute("DELETE FROM goals WHERE id=?", (test_goal_id,))
    conn1.commit()
    conn1.close()

    if wins != 1:
        print(f"  FAIL: {wins} threads claimed the task (expected exactly 1). "
              f"{losses} got None.")
        return False

    print(f"  PASS: {wins} thread claimed, {losses} got None "
          f"({NUM_THREADS} threads raced)")
    return True


def main() -> bool:
    print("=== M6 Features Eval ===\n")
    results = [
        check_watchdog_script(),
        check_watchdog_functional(),
        check_escalation_script(),
        check_escalation_functional(),
        check_concurrent_claim_atomicity(),
    ]
    passed = sum(results)
    total = len(results)
    print(f"\n--- Results: {passed}/{total} passed ---")
    return passed == total


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
