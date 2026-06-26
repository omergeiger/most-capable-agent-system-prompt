"""
improve.py - Self-improvement loop.

Runs one improvement cycle:
  1. Run eval harness (baseline score)
  2. Apply one targeted change to a skill file or prompt
  3. Run eval harness again (post-change score)
  4. Keep if score is same or better; revert (git checkout) if worse
  5. Log result to evals/improvement_log.md

Usage: .venv/bin/python scripts/improve.py --target <skill_file> --change "<description>"
  --target    Skill file to improve (e.g. skills/coding_task.md)
  --change    One-line description of the improvement to make via Claude
  --dry-run   Show what would happen without making changes
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
EVALS_DIR = REPO_ROOT / "evals"
IMPROVEMENT_LOG = EVALS_DIR / "improvement_log.md"
PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
RUN_EVALS = REPO_ROOT / "scripts" / "run_evals.py"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_evals() -> tuple[int, int]:
    """Run eval harness and return (passed, total)."""
    result = subprocess.run(
        [str(PYTHON), str(RUN_EVALS)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    passed = 0
    total = 0
    for line in result.stdout.splitlines():
        if "Eval Results:" in line:
            # "Eval Results: 1/1 passed"
            parts = line.split(":")[1].strip().split("/")
            try:
                passed = int(parts[0].strip())
                total = int(parts[1].split()[0].strip())
            except (IndexError, ValueError):
                pass
    return passed, total


def apply_improvement(target: Path, change_description: str) -> bool:
    """Ask Claude to apply the improvement to the target file using its tools."""
    prompt = f"""Improve the skill file at {target} by making this specific change:

{change_description}

Edit the file in place. Make only the requested change - do not restructure or reformat
unrelated sections. When done, output a single line: DONE"""

    before_mtime = target.stat().st_mtime

    result = subprocess.run(
        ["claude", "--print", "--dangerously-skip-permissions", prompt],
        capture_output=True, text=True, timeout=120, cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        print(f"Claude failed: {result.stderr[:200]}")
        return False

    after_mtime = target.stat().st_mtime
    if after_mtime == before_mtime:
        print(f"Warning: file was not modified. Claude output: {result.stdout[:200]}")
        return False

    return True


def git_revert(target: Path) -> None:
    """Revert the target file to HEAD."""
    subprocess.run(
        ["git", "checkout", "HEAD", "--", str(target.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT, check=True,
    )


def append_log(entry: dict) -> None:
    IMPROVEMENT_LOG.parent.mkdir(exist_ok=True)
    if not IMPROVEMENT_LOG.exists():
        IMPROVEMENT_LOG.write_text("# Improvement Log\n\n")
    with IMPROVEMENT_LOG.open("a") as f:
        outcome = "KEEP" if entry["kept"] else "REVERT"
        f.write(
            f"\n## {entry['timestamp']} - {outcome}\n\n"
            f"**Target:** `{entry['target']}`  \n"
            f"**Change:** {entry['change']}  \n"
            f"**Score before:** {entry['before_passed']}/{entry['before_total']}  \n"
            f"**Score after:** {entry['after_passed']}/{entry['after_total']}  \n"
            f"**Decision:** {outcome}  \n"
            f"**Reason:** {entry['reason']}  \n"
        )


def main():
    parser = argparse.ArgumentParser(description="Self-improvement loop")
    parser.add_argument("--target", required=True, help="Skill file to improve (relative path)")
    parser.add_argument("--change", required=True, help="Description of the improvement to make")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without making changes")
    args = parser.parse_args()

    target = REPO_ROOT / args.target
    if not target.exists():
        print(f"Target not found: {target}")
        sys.exit(1)

    print(f"Self-improvement loop")
    print(f"  Target: {args.target}")
    print(f"  Change: {args.change}")

    print("\n[1/4] Baseline eval run...")
    before_passed, before_total = run_evals()
    print(f"  Baseline: {before_passed}/{before_total} passed")

    if args.dry_run:
        print("\n--dry-run: would apply change and re-run evals. Exiting.")
        sys.exit(0)

    print("\n[2/4] Applying improvement...")
    ok = apply_improvement(target, args.change)
    if not ok:
        print("Failed to apply improvement. Aborting.")
        sys.exit(1)
    print("  Applied.")

    print("\n[3/4] Post-change eval run...")
    after_passed, after_total = run_evals()
    print(f"  After: {after_passed}/{after_total} passed")

    improved = (after_total == 0) or (after_passed / after_total >= before_passed / max(before_total, 1))

    if improved:
        decision = "KEEP"
        reason = f"Score held or improved ({before_passed}/{before_total} -> {after_passed}/{after_total})"
        print(f"\n[4/4] Decision: KEEP ({reason})")
    else:
        decision = "REVERT"
        reason = f"Score regressed ({before_passed}/{before_total} -> {after_passed}/{after_total})"
        print(f"\n[4/4] Decision: REVERT ({reason})")
        git_revert(target)
        print(f"  Reverted {args.target} to HEAD.")

    entry = {
        "timestamp": utcnow(),
        "target": args.target,
        "change": args.change,
        "before_passed": before_passed,
        "before_total": before_total,
        "after_passed": after_passed,
        "after_total": after_total,
        "kept": improved,
        "reason": reason,
    }
    append_log(entry)
    print(f"\nLogged to {IMPROVEMENT_LOG}")


if __name__ == "__main__":
    main()
