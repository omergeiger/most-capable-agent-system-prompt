"""
run_evals.py - Discover and run all evals/*.py files, store results, print summary.

Usage: .venv/bin/python scripts/run_evals.py [--eval <name>] [--output-dir <dir>]
  --eval        Run only this eval (filename without .py, e.g. task_claim_atomicity)
  --output-dir  Where to write result JSON files (default: evals/results/)
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
EVALS_DIR = REPO_ROOT / "evals"
RESULTS_DIR = EVALS_DIR / "results"
PYTHON = REPO_ROOT / ".venv" / "bin" / "python"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_eval(eval_path: Path) -> dict:
    """Run one eval script and return a result dict."""
    start = time.monotonic()
    try:
        result = subprocess.run(
            [str(PYTHON), str(eval_path)],
            capture_output=True, text=True,
            timeout=120, cwd=REPO_ROOT,
        )
        passed = result.returncode == 0
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
    except subprocess.TimeoutExpired:
        passed = False
        stdout = ""
        stderr = "TIMEOUT: eval exceeded 120 seconds"
    except Exception as e:
        passed = False
        stdout = ""
        stderr = str(e)

    duration_s = round(time.monotonic() - start, 2)
    return {
        "eval": eval_path.stem,
        "passed": passed,
        "duration_s": duration_s,
        "stdout": stdout,
        "stderr": stderr,
        "ran_at": utcnow(),
    }


def write_result(result: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = output_dir / f"{ts}_{result['eval']}.json"
    out_path.write_text(json.dumps(result, indent=2))
    return out_path


def print_summary(results: list[dict]) -> None:
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    print(f"\n{'='*60}")
    print(f"Eval Results: {passed}/{total} passed")
    print(f"{'='*60}")
    print(f"{'Eval':<35} {'Result':<8} {'Duration':>10}")
    print(f"{'-'*35} {'-'*8} {'-'*10}")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"{r['eval']:<35} {status:<8} {r['duration_s']:>9.1f}s")
    print(f"{'='*60}")
    if passed < total:
        print("\nFailed eval output:")
        for r in results:
            if not r["passed"]:
                print(f"\n-- {r['eval']} --")
                if r["stdout"]:
                    print(r["stdout"])
                if r["stderr"]:
                    print(f"STDERR: {r['stderr']}")


def main():
    parser = argparse.ArgumentParser(description="Run all evals and record results")
    parser.add_argument("--eval", help="Run only this eval (stem name, no .py)")
    parser.add_argument("--output-dir", default=str(RESULTS_DIR),
                        help="Directory for result JSON files")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    if args.eval:
        eval_files = [EVALS_DIR / f"{args.eval}.py"]
        missing = [f for f in eval_files if not f.exists()]
        if missing:
            print(f"Eval not found: {missing[0]}")
            sys.exit(1)
    else:
        eval_files = sorted(EVALS_DIR.glob("*.py"))

    if not eval_files:
        print("No eval files found in evals/")
        sys.exit(0)

    print(f"Running {len(eval_files)} eval(s)...")
    results = []
    for eval_path in eval_files:
        print(f"  {eval_path.stem}... ", end="", flush=True)
        result = run_eval(eval_path)
        out_path = write_result(result, output_dir)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"{status} ({result['duration_s']}s) -> {out_path.name}")
        results.append(result)

    print_summary(results)

    all_passed = all(r["passed"] for r in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
