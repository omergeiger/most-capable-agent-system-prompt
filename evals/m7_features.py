"""
m7_features.py - Validates Milestone 7 additions.

Checks:
  1. sweep_artifacts.py: exists, has --dry-run, skips active tasks and non-UUID dirs
  2. sweep functional: create a fake old artifact dir, sweep it, confirm removal
  3. sweep dry-run: confirm --dry-run reports but does NOT delete
  4. schedule.py: exists, defines all three jobs (watchdog, scan, escalate)
  5. schedule generate: writes valid plist files to artifacts/launchd/

Usage: .venv/bin/python evals/m7_features.py
"""
import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "tasks.db"
PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
ARTIFACTS_DIR = REPO_ROOT / "artifacts"

sys.path.insert(0, str(REPO_ROOT / "scripts"))


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_sweep_script() -> bool:
    print("sweep_artifacts.py: exists with dry-run, age filter, active-task guard")
    script = REPO_ROOT / "scripts" / "sweep_artifacts.py"
    if not script.exists():
        print("  FAIL: sweep_artifacts.py not found")
        return False

    src = script.read_text()
    required = ["dry_run", "UUID_RE", "get_active_task_ids", "DEFAULT_DAYS", "shutil.rmtree"]
    for token in required:
        if token not in src:
            print(f"  FAIL: '{token}' not found in sweep_artifacts.py")
            return False

    print("  PASS: sweep_artifacts.py present with all required logic tokens")
    return True


def make_old_dir(name: str, days_old: int = 10) -> Path:
    """Create a fake UUID artifact dir with an old mtime."""
    path = ARTIFACTS_DIR / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "completion_note.md").write_text("# fake artifact for eval sweep test\n")
    old_ts = (datetime.now(timezone.utc) - timedelta(days=days_old)).timestamp()
    os.utime(path, (old_ts, old_ts))
    return path


def check_sweep_functional() -> bool:
    print("sweep functional: old UUID artifact dir gets deleted")
    import importlib
    try:
        sweep = importlib.import_module("sweep_artifacts")
        importlib.reload(sweep)
    except Exception as e:
        print(f"  FAIL: sweep_artifacts import error: {e}")
        return False

    fake_id = str(uuid.uuid4())
    fake_dir = make_old_dir(fake_id, days_old=10)

    removed = sweep.run_sweep(days=7, dry_run=False)
    removed_names = {p.name for p in removed}

    if fake_id in removed_names:
        print(f"  PASS: old artifact dir {fake_id[:8]}... was swept")
        return True

    # If it wasn't removed, clean up manually
    if fake_dir.exists():
        import shutil
        shutil.rmtree(fake_dir)
    print(f"  FAIL: fake artifact dir {fake_id[:8]}... was not removed by sweep")
    return False


def check_sweep_dry_run() -> bool:
    print("sweep dry-run: reports old dir but does NOT delete it")
    import importlib
    try:
        sweep = importlib.import_module("sweep_artifacts")
        importlib.reload(sweep)
    except Exception as e:
        print(f"  FAIL: sweep_artifacts import error: {e}")
        return False

    fake_id = str(uuid.uuid4())
    fake_dir = make_old_dir(fake_id, days_old=10)

    reported = sweep.run_sweep(days=7, dry_run=True)
    reported_names = {p.name for p in reported}

    exists_after = fake_dir.exists()

    # Cleanup
    if fake_dir.exists():
        import shutil
        shutil.rmtree(fake_dir)

    if fake_id not in reported_names:
        print(f"  FAIL: fake dir {fake_id[:8]}... not reported in dry-run")
        return False

    if not exists_after:
        print(f"  FAIL: fake dir {fake_id[:8]}... was deleted despite --dry-run")
        return False

    print(f"  PASS: dir reported ({fake_id[:8]}...), NOT deleted (dry-run respected)")
    return True


def check_schedule_script() -> bool:
    print("schedule.py: exists, defines all three scheduled jobs")
    script = REPO_ROOT / "scripts" / "schedule.py"
    if not script.exists():
        print("  FAIL: schedule.py not found")
        return False

    src = script.read_text()
    required = [
        "harness-watchdog", "harness-scan", "harness-escalate",
        "generate", "install", "uninstall", "StartInterval",
    ]
    for token in required:
        if token not in src:
            print(f"  FAIL: '{token}' not found in schedule.py")
            return False

    print("  PASS: schedule.py present with all three jobs and required commands")
    return True


def check_schedule_generate() -> bool:
    print("schedule generate: writes valid plist files to artifacts/launchd/")
    result = subprocess.run(
        [str(PYTHON), str(REPO_ROOT / "scripts" / "schedule.py"), "generate"],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    if result.returncode != 0:
        print(f"  FAIL: schedule.py generate exited {result.returncode}: {result.stderr}")
        return False

    launchd_dir = REPO_ROOT / "artifacts" / "launchd"
    expected_labels = [
        "com.harness.watchdog",
        "com.harness.scan",
        "com.harness.escalate",
    ]
    for label in expected_labels:
        plist = launchd_dir / f"{label}.plist"
        if not plist.exists():
            print(f"  FAIL: {plist.name} not found after generate")
            return False
        content = plist.read_text()
        if "<?xml" not in content or label not in content:
            print(f"  FAIL: {plist.name} does not look like a valid plist")
            return False

    print(f"  PASS: 3 plist files written to artifacts/launchd/ - valid XML with correct labels")
    return True


def main() -> bool:
    print("=== M7 Features Eval ===\n")
    results = [
        check_sweep_script(),
        check_sweep_functional(),
        check_sweep_dry_run(),
        check_schedule_script(),
        check_schedule_generate(),
    ]
    passed = sum(results)
    total = len(results)
    print(f"\n--- Results: {passed}/{total} passed ---")
    return passed == total


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
