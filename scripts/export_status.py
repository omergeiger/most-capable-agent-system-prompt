"""
export_status.py - Export harness status as an HTML dashboard.

Writes artifacts/dashboard.html with task board, goal breakdown, and recent incidents.

Usage: .venv/bin/python scripts/export_status.py [--out PATH]
"""
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "tasks.db"
DEFAULT_OUT = REPO_ROOT / "artifacts" / "dashboard.html"

STATUS_COLOR = {
    "done": "#22c55e",
    "pending": "#f59e0b",
    "running": "#3b82f6",
    "locked": "#8b5cf6",
    "failed": "#ef4444",
    "blocked": "#f97316",
    "cancelled": "#94a3b8",
}

SEVERITY_COLOR = {
    "low": "#22c55e",
    "medium": "#f59e0b",
    "high": "#ef4444",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def get_data() -> dict:
    if not DB_PATH.exists():
        return {}
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    counts = dict(conn.execute("""
        SELECT
            COUNT(*) FILTER (WHERE status='pending')   AS pending,
            COUNT(*) FILTER (WHERE status='locked')    AS locked,
            COUNT(*) FILTER (WHERE status='running')   AS running,
            COUNT(*) FILTER (WHERE status='done')      AS done,
            COUNT(*) FILTER (WHERE status='failed')    AS failed,
            COUNT(*) FILTER (WHERE status='blocked')   AS blocked,
            COUNT(*) FILTER (WHERE status='cancelled') AS cancelled
        FROM tasks
    """).fetchone())

    goals = [dict(r) for r in conn.execute("""
        SELECT g.id, g.description, g.status AS goal_status, g.trust_level,
               COALESCE(g.budget_limit, 0) AS budget_limit,
               COUNT(t.id) AS task_count,
               COUNT(t.id) FILTER (WHERE t.status='done') AS done_count,
               COUNT(t.id) FILTER (WHERE t.status='failed') AS failed_count,
               ROUND(SUM(COALESCE(t.cost_usd, 0)), 4) AS total_cost
        FROM goals g
        LEFT JOIN tasks t ON t.goal_id = g.id
        GROUP BY g.id
        ORDER BY g.created_at DESC
        LIMIT 20
    """).fetchall()]

    incidents = [dict(r) for r in conn.execute("""
        SELECT id, severity, title, status, created_at, resolved_at
        FROM incidents
        ORDER BY created_at DESC
        LIMIT 20
    """).fetchall()]

    recent_tasks = [dict(r) for r in conn.execute("""
        SELECT id, description, status, risk_level, cost_usd, completed_at, updated_at
        FROM tasks
        WHERE status IN ('done', 'failed')
        ORDER BY updated_at DESC
        LIMIT 15
    """).fetchall()]

    conn.close()
    return {"counts": counts, "goals": goals, "incidents": incidents, "recent_tasks": recent_tasks}


def status_badge(status: str) -> str:
    color = STATUS_COLOR.get(status, "#94a3b8")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:0.8em;font-weight:600">{status}</span>'


def severity_badge(severity: str) -> str:
    color = SEVERITY_COLOR.get(severity, "#94a3b8")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:0.8em;font-weight:600">{severity}</span>'


def render_html(data: dict) -> str:
    counts = data.get("counts", {})
    goals = data.get("goals", [])
    incidents = data.get("incidents", [])
    recent_tasks = data.get("recent_tasks", [])
    now = utcnow()

    total = sum(counts.values())
    done_pct = round(counts.get("done", 0) / total * 100) if total else 0

    count_cells = "".join(
        f'<div style="background:#1e293b;border-radius:8px;padding:16px;text-align:center">'
        f'<div style="font-size:2em;font-weight:700;color:{STATUS_COLOR.get(k,"#fff")}">{v}</div>'
        f'<div style="color:#94a3b8;font-size:0.85em;text-transform:uppercase">{k}</div>'
        f'</div>'
        for k, v in counts.items()
    )

    goal_rows = ""
    for g in goals:
        prog = f"{g['done_count']}/{g['task_count']}"
        budget = f"${g['budget_limit']:.2f}" if g["budget_limit"] else "none"
        cost = f"${g['total_cost'] or 0:.4f}"
        pct = round(g["done_count"] / g["task_count"] * 100) if g["task_count"] else 0
        bar = f'<div style="background:#0f172a;border-radius:4px;height:8px;overflow:hidden"><div style="background:#22c55e;width:{pct}%;height:100%"></div></div>'
        goal_rows += (
            f"<tr>"
            f"<td style='font-family:monospace;color:#94a3b8'>{g['id'][:8]}</td>"
            f"<td>{g['description'][:60]}</td>"
            f"<td>{status_badge(g['trust_level'])}</td>"
            f"<td>{budget}</td>"
            f"<td>{prog} {bar}</td>"
            f"<td>{cost}</td>"
            f"</tr>"
        )

    incident_rows = ""
    for inc in incidents:
        incident_rows += (
            f"<tr>"
            f"<td style='font-family:monospace;color:#94a3b8'>{inc['id'][:8]}</td>"
            f"<td>{severity_badge(inc['severity'])}</td>"
            f"<td>{inc['title'][:70]}</td>"
            f"<td>{status_badge(inc['status'])}</td>"
            f"<td style='color:#94a3b8;font-size:0.85em'>{(inc['created_at'] or '')[:19]}</td>"
            f"</tr>"
        )
    if not incident_rows:
        incident_rows = "<tr><td colspan='5' style='color:#94a3b8;text-align:center'>No incidents</td></tr>"

    task_rows = ""
    for t in recent_tasks:
        cost = f"${t['cost_usd']:.4f}" if t.get("cost_usd") else "-"
        task_rows += (
            f"<tr>"
            f"<td style='font-family:monospace;color:#94a3b8'>{t['id'][:8]}</td>"
            f"<td>{t['description'][:65]}</td>"
            f"<td>{status_badge(t['status'])}</td>"
            f"<td>{cost}</td>"
            f"<td style='color:#94a3b8;font-size:0.85em'>{(t['updated_at'] or '')[:19]}</td>"
            f"</tr>"
        )

    table_style = "width:100%;border-collapse:collapse;font-size:0.9em"
    th_style = "text-align:left;padding:8px 12px;color:#94a3b8;border-bottom:1px solid #1e293b;text-transform:uppercase;font-size:0.75em"
    td_style = "padding:8px 12px;border-bottom:1px solid #1e293b"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Harness Dashboard</title>
<style>
  body {{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:24px}}
  h1 {{margin:0 0 4px;font-size:1.5em;color:#f8fafc}}
  .subtitle {{color:#64748b;margin:0 0 24px;font-size:0.85em}}
  h2 {{color:#f8fafc;font-size:1.1em;margin:32px 0 12px}}
  .grid {{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:12px;margin-bottom:24px}}
  .card {{background:#1e293b;border-radius:8px;padding:20px}}
  table {{background:#1e293b;border-radius:8px;overflow:hidden;{table_style}}}
  th {{{th_style}}}
  td {{{td_style}}}
  tr:hover td {{background:#263148}}
</style>
</head>
<body>
<h1>Harness v1 Dashboard</h1>
<p class="subtitle">Generated {now} - {total} total tasks - {done_pct}% complete</p>

<h2>Task Board</h2>
<div class="grid">{count_cells}</div>

<h2>Goals (recent 20)</h2>
<table>
<thead><tr>
  <th>ID</th><th>Description</th><th>Trust</th><th>Budget</th><th>Progress</th><th>Cost</th>
</tr></thead>
<tbody>{goal_rows}</tbody>
</table>

<h2>Incidents (recent 20)</h2>
<table>
<thead><tr>
  <th>ID</th><th>Severity</th><th>Title</th><th>Status</th><th>Created</th>
</tr></thead>
<tbody>{incident_rows}</tbody>
</table>

<h2>Recent Tasks</h2>
<table>
<thead><tr>
  <th>ID</th><th>Description</th><th>Status</th><th>Cost</th><th>Updated</th>
</tr></thead>
<tbody>{task_rows}</tbody>
</table>

</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Export harness status as HTML dashboard")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output path")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = get_data()
    html = render_html(data)
    out_path.write_text(html)
    print(f"Dashboard exported to: {out_path}")
    counts = data.get("counts", {})
    print(f"  Tasks: {sum(counts.values())} total, {counts.get('done', 0)} done, {counts.get('failed', 0)} failed")
    print(f"  Incidents: {len(data.get('incidents', []))}")


if __name__ == "__main__":
    main()
