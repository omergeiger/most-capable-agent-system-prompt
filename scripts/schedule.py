"""
schedule.py - Generate and manage launchd plists for recurring harness jobs (macOS).

Jobs managed:
  harness-watchdog     - watchdog.py every 30 minutes
  harness-scan         - run_scan.sh daily at 08:00
  harness-escalate     - escalate_incidents.py hourly

Commands:
  generate   Write plist files to artifacts/launchd/ for review
  install    Copy plists to ~/Library/LaunchAgents and load via launchctl
  uninstall  Unload and remove plists from ~/Library/LaunchAgents
  status     Show load status of each job via launchctl list

Usage:
  .venv/bin/python scripts/schedule.py generate
  .venv/bin/python scripts/schedule.py install
  .venv/bin/python scripts/schedule.py uninstall
  .venv/bin/python scripts/schedule.py status
"""
import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
LAUNCHD_DIR = REPO_ROOT / "artifacts" / "launchd"
USER_LAUNCHD = Path.home() / "Library" / "LaunchAgents"

JOBS = {
    "harness-watchdog": {
        "label": "com.harness.watchdog",
        "description": "Harness stuck-task watchdog (every 30 min)",
        "program": [str(VENV_PYTHON), str(REPO_ROOT / "scripts" / "watchdog.py")],
        "interval_seconds": 1800,
        "log_prefix": "watchdog",
    },
    "harness-scan": {
        "label": "com.harness.scan",
        "description": "Harness proactive scan (daily 08:00)",
        "program": ["/bin/bash", str(REPO_ROOT / "scripts" / "run_scan.sh")],
        "calendar": {"Hour": 8, "Minute": 0},
        "log_prefix": "scan",
    },
    "harness-escalate": {
        "label": "com.harness.escalate",
        "description": "Harness incident escalation (hourly)",
        "program": [str(VENV_PYTHON), str(REPO_ROOT / "scripts" / "escalate_incidents.py")],
        "interval_seconds": 3600,
        "log_prefix": "escalate",
    },
}


def render_plist(job_name: str, job: dict) -> str:
    logs_dir = REPO_ROOT / "logs"
    out_log = logs_dir / f"{job['log_prefix']}.stdout.log"
    err_log = logs_dir / f"{job['log_prefix']}.stderr.log"

    program_args = "\n".join(
        f"        <string>{arg}</string>" for arg in job["program"]
    )

    if "interval_seconds" in job:
        schedule_xml = f"""
    <key>StartInterval</key>
    <integer>{job['interval_seconds']}</integer>"""
    else:
        cal = job["calendar"]
        cal_items = "\n".join(
            f"        <key>{k}</key>\n        <integer>{v}</integer>"
            for k, v in cal.items()
        )
        schedule_xml = f"""
    <key>StartCalendarInterval</key>
    <dict>
{cal_items}
    </dict>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{job['label']}</string>

    <key>ProgramArguments</key>
    <array>
{program_args}
    </array>

    <key>WorkingDirectory</key>
    <string>{REPO_ROOT}</string>
{schedule_xml}

    <key>StandardOutPath</key>
    <string>{out_log}</string>

    <key>StandardErrorPath</key>
    <string>{err_log}</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""


def cmd_generate(args) -> None:
    LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[schedule] Writing plists to {LAUNCHD_DIR}/")
    for name, job in JOBS.items():
        plist_path = LAUNCHD_DIR / f"{job['label']}.plist"
        plist_path.write_text(render_plist(name, job))
        print(f"  wrote {plist_path.name}  ({job['description']})")
    print("\nTo install: .venv/bin/python scripts/schedule.py install")


def cmd_install(args) -> None:
    if sys.platform != "darwin":
        print("[schedule] install only supported on macOS (launchd)")
        sys.exit(1)

    USER_LAUNCHD.mkdir(parents=True, exist_ok=True)
    LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)

    for name, job in JOBS.items():
        plist_path = LAUNCHD_DIR / f"{job['label']}.plist"
        if not plist_path.exists():
            plist_path.write_text(render_plist(name, job))

        dest = USER_LAUNCHD / plist_path.name
        import shutil
        shutil.copy2(plist_path, dest)

        result = subprocess.run(
            ["launchctl", "load", str(dest)],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"  [loaded]  {job['label']}  ({job['description']})")
        else:
            print(f"  [error]   {job['label']}: {result.stderr.strip()}")

    print("\n[schedule] Done. Use 'status' to confirm.")


def cmd_uninstall(args) -> None:
    if sys.platform != "darwin":
        print("[schedule] uninstall only supported on macOS (launchd)")
        sys.exit(1)

    for name, job in JOBS.items():
        dest = USER_LAUNCHD / f"{job['label']}.plist"
        if not dest.exists():
            print(f"  [skip]    {job['label']} (not installed)")
            continue

        subprocess.run(["launchctl", "unload", str(dest)],
                       capture_output=True, text=True)
        dest.unlink()
        print(f"  [removed] {job['label']}")

    print("[schedule] All harness jobs uninstalled.")


def cmd_status(args) -> None:
    if sys.platform != "darwin":
        print("[schedule] status only supported on macOS (launchd)")
        sys.exit(1)

    result = subprocess.run(
        ["launchctl", "list"], capture_output=True, text=True
    )
    lines = result.stdout.splitlines()
    labels = {job["label"] for job in JOBS.values()}

    print(f"{'LABEL':<35} {'STATUS'}")
    print("-" * 55)
    found = set()
    for line in lines:
        for label in labels:
            if label in line:
                parts = line.split()
                pid = parts[0] if parts else "-"
                last_exit = parts[1] if len(parts) > 1 else "-"
                status = "running" if pid != "-" else f"loaded (last exit: {last_exit})"
                print(f"  {label:<33} {status}")
                found.add(label)

    for label in labels - found:
        print(f"  {label:<33} not loaded")


def main():
    parser = argparse.ArgumentParser(description="Manage harness launchd schedules")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("generate", help="Write plist files to artifacts/launchd/")
    sub.add_parser("install", help="Install and load launchd agents (macOS)")
    sub.add_parser("uninstall", help="Unload and remove launchd agents (macOS)")
    sub.add_parser("status", help="Show load status via launchctl list")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "generate": cmd_generate,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "status": cmd_status,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
