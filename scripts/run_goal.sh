#!/usr/bin/env bash
# run_goal.sh - Unattended goal runner.
#
# Usage:
#   scripts/run_goal.sh "goal description" [BUDGET_USD] [TRUST_LEVEL]
#
# Examples:
#   scripts/run_goal.sh "audit all evals for completeness"
#   scripts/run_goal.sh "run nightly syntax check" 1.50 guided
#   scripts/run_goal.sh "verify docs are up to date" 2.00 autonomous
#
# TRUST_LEVEL defaults to 'guided'. Budget defaults to none (unlimited).
# The script exits non-zero if goal creation or the worker fails.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
CREATE_GOAL="$REPO_ROOT/scripts/create_goal.py"
SET_TRUST="$REPO_ROOT/scripts/set_trust.py"
WORKER="$REPO_ROOT/scripts/worker.py"

GOAL_DESC="${1:-}"
BUDGET="${2:-}"
TRUST="${3:-guided}"

if [[ -z "$GOAL_DESC" ]]; then
    echo "Usage: $0 \"goal description\" [BUDGET_USD] [TRUST_LEVEL]"
    exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
    echo "ERROR: .venv/bin/python not found. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

cd "$REPO_ROOT"

# Create goal
echo "[run_goal] Creating goal: $GOAL_DESC"
GOAL_OUTPUT=$("$PYTHON" "$CREATE_GOAL" "$GOAL_DESC" 2>&1)
echo "$GOAL_OUTPUT"

# Extract goal ID from output (create_goal.py prints "Goal created: <id>")
GOAL_ID=$(echo "$GOAL_OUTPUT" | grep "^Goal created:" | awk '{print $3}')
if [[ -z "$GOAL_ID" ]]; then
    echo "[run_goal] ERROR: could not extract goal ID from create_goal.py output"
    exit 1
fi

echo "[run_goal] Goal ID: $GOAL_ID"

# Set trust level
if [[ "$TRUST" != "supervised" ]]; then
    echo "[run_goal] Setting trust level: $TRUST"
    "$PYTHON" "$SET_TRUST" set "$GOAL_ID" "$TRUST"
fi

# Apply budget if given
if [[ -n "$BUDGET" ]]; then
    echo "[run_goal] Setting budget: \$$BUDGET"
    "$PYTHON" -c "
import sqlite3
conn = sqlite3.connect('tasks.db')
conn.execute(\"UPDATE goals SET budget_limit=? WHERE id=?\", ($BUDGET, '$GOAL_ID'))
conn.commit()
print(f'Budget set to \$$BUDGET for goal $GOAL_ID')
conn.close()
"
fi

# Run worker until goal queue is empty
echo "[run_goal] Starting worker for goal $GOAL_ID (trust=$TRUST)"
"$PYTHON" "$WORKER" --goal-id "$GOAL_ID" --no-hitl

echo "[run_goal] Done. Goal $GOAL_ID complete."
