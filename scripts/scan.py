"""
scan.py - Proactive monitoring scan.

Reads all projects/*/handoff.md files, flags stale open questions and blocked
tasks, then auto-creates goals for each flag via create_goal.py.

Usage: .venv/bin/python scripts/scan.py [--dry-run] [--age-days N]
  --dry-run    Report flags but do not create goals
  --age-days   Flag items older than N days (default: 2)
"""
import argparse
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PROJECTS_DIR = REPO_ROOT / "projects"
LOGS_DIR = REPO_ROOT / "logs"
DB_PATH = REPO_ROOT / "tasks.db"
PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
CREATE_GOAL = REPO_ROOT / "scripts" / "create_goal.py"

DEFAULT_AGE_DAYS = 2


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(s: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


def age_days(ts: datetime) -> float:
    return (utcnow() - ts).total_seconds() / 86400


def scan_handoff(path: Path, max_age_days: float) -> list[dict]:
    """Parse a handoff.md and return a list of flag dicts."""
    flags = []
    content = path.read_text()
    project = path.parent.name

    # Detect session end date
    session_date = None
    for line in content.splitlines():
        m = re.search(r"\*\*Session end:\*\*\s*(.+)", line)
        if m:
            raw = m.group(1).strip()
            # Try ISO parse, then YYYY-MM-DD
            session_date = parse_iso(raw) or parse_iso(raw + "T00:00:00Z")
            break

    # If session date is stale, flag the whole handoff
    if session_date and age_days(session_date) > max_age_days:
        # Flag open questions
        in_open_questions = False
        for line in content.splitlines():
            if "## Open Questions" in line:
                in_open_questions = True
                continue
            if in_open_questions and line.startswith("## "):
                break
            if in_open_questions and re.match(r"\d+\.", line.strip()):
                question = line.strip().lstrip("0123456789. ")
                flags.append({
                    "project": project,
                    "type": "open_question",
                    "description": question,
                    "age_days": round(age_days(session_date), 1),
                    "source": str(path),
                    "goal": f"Resolve open question in {project} handoff: {question[:120]}",
                })

        # Flag blocked tasks in momentum section
        in_blocked = False
        for line in content.splitlines():
            if "blocked:" in line.lower() or "## What Is Blocked" in line:
                in_blocked = True
                continue
            if in_blocked and line.startswith("## "):
                break
            if in_blocked and line.strip() and not line.strip().startswith("#"):
                stripped = line.strip().lstrip("-* ")
                skip_words = ("none", "no structural", "no missing", "no schema")
                if stripped and not any(w in stripped.lower() for w in skip_words) and len(stripped) > 10:
                    flags.append({
                        "project": project,
                        "type": "blocked_task",
                        "description": stripped,
                        "age_days": round(age_days(session_date), 1),
                        "source": str(path),
                        "goal": f"Unblock task in {project}: {stripped[:120]}",
                    })

    return flags


def build_dashboard() -> str:
    """Generate a markdown dashboard from tasks.db."""
    if not DB_PATH.exists():
        return "_tasks.db not found._\n"

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    counts = dict(conn.execute("""
        SELECT
            COUNT(*) FILTER (WHERE status='pending')  AS pending,
            COUNT(*) FILTER (WHERE status='locked')   AS locked,
            COUNT(*) FILTER (WHERE status='running')  AS running,
            COUNT(*) FILTER (WHERE status='done')     AS done,
            COUNT(*) FILTER (WHERE status='failed')   AS failed,
            COUNT(*) FILTER (WHERE status='blocked')  AS blocked,
            COUNT(*) FILTER (WHERE status='cancelled') AS cancelled
        FROM tasks
    """).fetchone())

    goals = conn.execute("""
        SELECT g.id, g.description, g.status, g.trust_level,
               COALESCE(g.budget_limit, 0) AS budget_limit,
               COUNT(t.id) AS task_count,
               COUNT(t.id) FILTER (WHERE t.status='done') AS done_count,
               ROUND(SUM(COALESCE(t.cost_usd, 0)), 4) AS total_cost
        FROM goals g
        LEFT JOIN tasks t ON t.goal_id = g.id
        GROUP BY g.id
        ORDER BY g.created_at DESC
        LIMIT 15
    """).fetchall()

    conn.close()

    lines = [
        f"## Dashboard - {utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n",
        "| Status | Count |",
        "|---|---|",
    ]
    for k, v in counts.items():
        lines.append(f"| {k} | {v} |")

    lines.append("\n### Goals (recent 15)\n")
    lines.append("| Goal | Trust | Budget | Progress | Cost |")
    lines.append("|---|---|---|---|---|")
    for g in goals:
        desc = g["description"][:40] if g["description"] else ""
        budget_str = f"${g['budget_limit']:.2f}" if g["budget_limit"] else "none"
        progress = f"{g['done_count']}/{g['task_count']}"
        cost = f"${g['total_cost'] or 0:.4f}"
        lines.append(f"| {desc} | {g['trust_level']} | {budget_str} | {progress} | {cost} |")

    return "\n".join(lines) + "\n"


def write_scan_report(flags: list[dict], goals_created: list[str]) -> Path:
    LOGS_DIR.mkdir(exist_ok=True)
    ts = utcnow().strftime("%Y%m%dT%H%M%S")
    report_path = LOGS_DIR / f"scan_{ts}.md"

    dashboard = build_dashboard()

    lines = [
        f"# Scan Report - {utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"\n**Flags found:** {len(flags)}  ",
        f"**Goals created:** {len(goals_created)}",
        f"\n{dashboard}",
        "\n## Flags\n",
    ]
    if not flags:
        lines.append("_No flags found._")
    for f in flags:
        lines.append(
            f"- **[{f['type']}]** `{f['project']}` ({f['age_days']}d old): {f['description'][:100]}"
        )

    if goals_created:
        lines.append("\n## Goals Created\n")
        for g in goals_created:
            lines.append(f"- {g}")

    report_path.write_text("\n".join(lines) + "\n")
    return report_path


def create_goal(goal_description: str) -> bool:
    result = subprocess.run(
        [str(PYTHON), str(CREATE_GOAL), goal_description],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Proactive monitoring scan")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report flags but do not create goals")
    parser.add_argument("--age-days", type=float, default=DEFAULT_AGE_DAYS,
                        help=f"Flag items older than N days (default: {DEFAULT_AGE_DAYS})")
    args = parser.parse_args()

    handoff_files = sorted(PROJECTS_DIR.glob("*/handoff.md"))
    if not handoff_files:
        print("No handoff.md files found in projects/")
        sys.exit(0)

    print(f"Scanning {len(handoff_files)} project(s) for items older than {args.age_days} day(s)...")

    all_flags = []
    for hf in handoff_files:
        flags = scan_handoff(hf, args.age_days)
        all_flags.extend(flags)
        if flags:
            print(f"  {hf.parent.name}: {len(flags)} flag(s)")
        else:
            print(f"  {hf.parent.name}: clean")

    if not all_flags:
        print("\nNo flags found. All projects are current.")
        report = write_scan_report([], [])
        print(f"Scan report: {report}")
        sys.exit(0)

    print(f"\nFlags found: {len(all_flags)}")
    for f in all_flags:
        print(f"  [{f['type']}] {f['project']} ({f['age_days']}d): {f['description'][:80]}")

    goals_created = []
    if args.dry_run:
        print("\n--dry-run: skipping goal creation")
    else:
        print("\nCreating goals...")
        for f in all_flags:
            print(f"  Creating: {f['goal'][:80]}...")
            ok = create_goal(f["goal"])
            if ok:
                goals_created.append(f["goal"])
                print(f"    -> created")
            else:
                print(f"    -> FAILED")

    report = write_scan_report(all_flags, goals_created)
    print(f"\nScan report: {report}")
    print(f"Summary: {len(all_flags)} flag(s), {len(goals_created)} goal(s) created")


if __name__ == "__main__":
    main()
