"""
init_db.py - Initialize or migrate tasks.db schema.

Run this before the first worker run, or when the schema changes.
Usage: .venv/bin/python scripts/init_db.py
"""
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "tasks.db"

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    project_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    trust_level TEXT NOT NULL DEFAULT 'supervised',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    goal_id TEXT REFERENCES goals(id),
    project_id TEXT,
    description TEXT NOT NULL,
    scope TEXT,
    mindset TEXT,
    context TEXT,
    skill_tags TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    depends_on TEXT,
    owner TEXT,
    reviewer TEXT,
    priority INTEGER NOT NULL DEFAULT 5,
    risk_level TEXT NOT NULL DEFAULT 'low',
    budget_limit REAL,
    tokens_used INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    attempts INTEGER NOT NULL DEFAULT 0,
    verification_plan TEXT,
    evidence TEXT,
    artifacts TEXT,
    escalation_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    locked_at TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    task_id TEXT REFERENCES tasks(id),
    goal_id TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    output_path TEXT,
    tokens_used INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS memory_entries (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    source_task_id TEXT,
    source_session_id TEXT,
    tags TEXT,
    created_at TEXT NOT NULL,
    superseded_at TEXT
);

CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    severity TEXT NOT NULL DEFAULT 'low',
    title TEXT NOT NULL,
    description TEXT,
    task_id TEXT,
    goal_id TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    root_cause TEXT,
    remediation TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_goal ON tasks(goal_id);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_sessions_task ON sessions(task_id);
CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_entries(type);
"""


MIGRATIONS = [
    "ALTER TABLE tasks ADD COLUMN cost_usd REAL DEFAULT 0.0",
    "ALTER TABLE goals ADD COLUMN trust_level TEXT NOT NULL DEFAULT 'supervised'",
]


def apply_migrations(conn: sqlite3.Connection) -> None:
    existing_task_cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
    existing_goal_cols = {row[1] for row in conn.execute("PRAGMA table_info(goals)")}
    for stmt in MIGRATIONS:
        col = stmt.split("ADD COLUMN")[1].strip().split()[0]
        table = stmt.split("TABLE")[1].strip().split()[0]
        existing = existing_task_cols if table == "tasks" else existing_goal_cols
        if col not in existing:
            conn.execute(stmt)
            print(f"Migration applied: {stmt}")


def init_db(db_path: Path = DB_PATH) -> None:
    print(f"Initializing database at: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    apply_migrations(conn)
    conn.commit()
    conn.close()
    print("Done. Tables:", ", ".join(get_tables(db_path)))


def get_tables(db_path: Path) -> list[str]:
    conn = sqlite3.connect(str(db_path))
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cur.fetchall()]
    conn.close()
    return tables


if __name__ == "__main__":
    init_db()
