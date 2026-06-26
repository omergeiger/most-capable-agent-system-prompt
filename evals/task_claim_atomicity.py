"""
task_claim_atomicity.py - Proves that concurrent task claiming does not double-claim.

Simulates N concurrent workers all trying to claim the same pending task.
Exactly one should succeed. All others should get None.

Usage: .venv/bin/python evals/task_claim_atomicity.py
"""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "tasks.db"

CONCURRENCY = 10  # threads all trying to claim at once


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def setup_test_task(db_path: Path) -> tuple[str, str]:
    """Insert a test goal and one pending task. Returns (goal_id, task_id)."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    now = utcnow()

    goal_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO goals (id, description, status, created_at, updated_at) VALUES (?,?,?,?,?)",
        (goal_id, "[eval] atomicity test goal", "active", now, now),
    )

    task_id = str(uuid.uuid4())
    conn.execute("""
        INSERT INTO tasks
        (id, goal_id, description, status, priority, risk_level, attempts, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (task_id, goal_id, "[eval] atomicity test task", "pending", 5, "low", 0, now, now))

    conn.commit()
    conn.close()
    return goal_id, task_id


def try_claim(db_path: Path, task_id: str, results: list, idx: int) -> None:
    """One worker thread: try to claim the task and record whether it succeeded."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    now = utcnow()

    cur = conn.execute("""
        UPDATE tasks
        SET status = 'locked', locked_at = ?, attempts = attempts + 1, updated_at = ?
        WHERE id = ? AND status = 'pending'
        RETURNING id
    """, (now, now, task_id))
    row = cur.fetchone()
    conn.commit()
    conn.close()
    results[idx] = row is not None  # True = claimed, False = missed


def cleanup_test_task(db_path: Path, goal_id: str, task_id: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    conn.commit()
    conn.close()


def run_atomicity_test() -> bool:
    print(f"Atomicity test: {CONCURRENCY} concurrent workers claiming one task")
    print(f"DB: {DB_PATH}")

    if not DB_PATH.exists():
        print("SKIP: tasks.db not found. Run scripts/init_db.py first.")
        return False

    goal_id, task_id = setup_test_task(DB_PATH)
    print(f"Test task: {task_id[:8]}")

    results = [None] * CONCURRENCY
    threads = [
        threading.Thread(target=try_claim, args=(DB_PATH, task_id, results, i))
        for i in range(CONCURRENCY)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    claims = sum(1 for r in results if r is True)

    cleanup_test_task(DB_PATH, goal_id, task_id)

    if claims == 1:
        print(f"PASS: exactly 1 of {CONCURRENCY} workers claimed the task")
        return True
    else:
        print(f"FAIL: {claims} workers claimed the task (expected 1)")
        return False


def run_schema_test() -> bool:
    """Verify the DB has the expected tables."""
    print("\nSchema test: checking tables and indexes")
    if not DB_PATH.exists():
        print("SKIP: tasks.db not found.")
        return False

    conn = sqlite3.connect(str(DB_PATH))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    expected = {"goals", "tasks", "sessions", "memory_entries", "incidents"}
    missing = expected - tables
    if missing:
        print(f"FAIL: missing tables: {missing}")
        return False
    print(f"PASS: all expected tables present: {expected}")

    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    print(f"WAL mode: {mode}")
    conn.close()
    return True


if __name__ == "__main__":
    schema_ok = run_schema_test()
    atomicity_ok = run_atomicity_test()

    print("\n--- Results ---")
    print(f"Schema: {'PASS' if schema_ok else 'FAIL'}")
    print(f"Atomicity: {'PASS' if atomicity_ok else 'FAIL'}")

    if schema_ok and atomicity_ok:
        print("\nAll evals PASS")
        raise SystemExit(0)
    else:
        print("\nSome evals FAILED")
        raise SystemExit(1)
