# Harness v1 - User Manual

**Version:** 1.0 (Milestones 1-7 complete)
**Audience:** Engineers and operators who want to use the harness to run autonomous or semi-autonomous agent workloads.

---

## Part I - High-Level Overview

### What Is This?

The Harness is a durable, verifiable, self-monitoring orchestration layer that wraps Claude Code as its execution engine. It provides what Claude Code alone does not: persistent task state across sessions, isolated verifier agents, enforced workflow rails, budget controls, and a compounding self-improvement loop.

Put simply: you describe work as a **goal**. The harness decomposes it into **tasks**, executes them one at a time via Claude Code, verifies each result with a separate agent that did not do the work, stores evidence, and tells you exactly what happened.

You remain in control via **trust levels** - you decide how much the system can do without asking you first.

### The Four-Layer Stack

```
+-------------------------------------------------+
|  You                                            |
|  (goals, trust decisions, incident review)      |
+-------------------------------------------------+
          |
+-------------------------------------------------+
|  Harness Control Plane                          |
|  tasks.db  |  status.md  |  handoff.md          |
|  incidents |  goals      |  eval suite          |
+-------------------------------------------------+
          |
+-------------------------------------------------+
|  scripts/worker.py                              |
|  claim -> gate -> execute -> verify -> record   |
+-------------------------------------------------+
          |
+-------------------------------------------------+
|  Claude Code (Execution Engine)                 |
|  file edits, tool use, subagents, MCP           |
+-------------------------------------------------+
```

Each layer has a distinct job. You interact with the top layer. The harness handles everything in the middle. Claude Code handles raw tool execution at the bottom. This separation means the harness can swap execution engines in the future without changing how you interact with it.

### What a Goal Run Looks Like

1. You provide a goal in plain English: *"Audit the Python dependencies for security issues and write a report."*
2. `create_goal.py` sends that description to Claude Code, which produces a JSON task graph (3-7 tasks, each with a description, scope, skill tags, priority, risk level, dependency list, and verification plan).
3. Tasks are inserted into `tasks.db` as `pending`.
4. `worker.py` polls the queue, claims one task atomically (using SQLite's `RETURNING` clause to guarantee no two workers claim the same task), checks trust/budget gates, and sends the task to Claude Code for execution.
5. After execution, a **separate** Claude Code invocation (the verifier) reads the artifacts directory and writes `verification.md` with a PASS or FAIL verdict. The executor and verifier never share context.
6. On PASS the task becomes `done`. On FAIL it returns to `pending` for retry (up to 3 attempts), then `failed`. On `failed`, an incident is auto-created.
7. When all tasks are done, the goal is complete. You read the output in `artifacts/<task_id>/` and the summary in `logs/episodic.md`.

### Trust Levels at a Glance

| Level | What Happens | When to Use |
|---|---|---|
| `supervised` | Worker pauses before every task, asks for approval | Unfamiliar goals, high-stakes changes |
| `guided` | Worker proceeds automatically on low/medium risk tasks, pauses on high | Routine ops, known domains |
| `autonomous` | Worker runs the full goal without interruption | Proven recurring goals with verified track record |

You set trust per goal - not globally. A goal starts at `supervised` and you promote it when you are confident. Autonomous trust is a deliberate human decision, never a default.

### Self-Monitoring

The harness watches itself. Three recurring jobs (ready to activate via launchd) handle:

- **Watchdog** (every 30 min): finds tasks stuck in `locked` or `running` longer than 30 minutes, resets them to `pending`, and creates an incident.
- **Escalation** (hourly): promotes open incident severity by age - low incidents become medium after 1 hour, medium become high after 2 hours.
- **Proactive Scan** (daily): reads all `handoff.md` files, flags stale open questions and blocked items, and auto-creates goals to address them.

The HTML dashboard (`artifacts/dashboard.html`) gives you a single-page view of task board, goals, incidents, and recent activity.

### The Eval Harness

Six automated evals run in under one second and verify the system's own integrity:

| Eval | What It Checks |
|---|---|
| `m3_features` | Trust levels, cost tracking, ops skill, scan functionality |
| `m4_features` | Budget cap enforcement, guided trust gate, scan dashboard |
| `m5_features` | Incident table, CLI, run_goal.sh, HTML export, autonomous goal |
| `m6_features` | Watchdog reset, incident escalation, 8-thread claim atomicity |
| `m7_features` | Artifact sweep, launchd schedule generation |
| `task_claim_atomicity` | N threads racing one task, exactly one wins |

Run them anytime: `.venv/bin/python scripts/run_evals.py`

If a score drops after a change, the self-improvement loop reverts automatically.

---

## Part II - Getting Started

### Prerequisites

- macOS (launchd scheduling) or Linux (cron scheduling)
- Python 3.11+
- Claude Code CLI (`claude` on PATH) - install via `npm install -g @anthropic-ai/claude-code`
- Git

### First-Time Setup

```bash
# Clone and enter the repository
git clone <repo-url>
cd most-capable-agent-system-prompt

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (stdlib only - no third-party packages required)
# Nothing to install - all scripts use Python stdlib

# Initialize the database
.venv/bin/python scripts/init_db.py

# Verify everything is working
.venv/bin/python scripts/run_evals.py
```

All 6 evals should pass. If any fail, check that:
- `claude` is on your PATH (`which claude`)
- `tasks.db` exists in the repo root
- `.venv/bin/python` is a Python 3.11+ interpreter

### Directory Layout

```
/
  tasks.db                    - SQLite database (all state lives here)
  scripts/                    - All executable scripts
  evals/                      - Eval suite + results + improvement log
  skills/                     - Domain skill profiles loaded per task
  projects/harness-v1/        - Planning docs, handoff, status
  artifacts/                  - Task output evidence (one dir per task UUID)
  logs/                       - Episodic memory, scan reports, exec logs
  artifacts/launchd/          - Generated launchd plists (ready to install)
  artifacts/dashboard.html    - HTML status dashboard (regenerate anytime)
```

---

## Part III - Core Concepts

### Goals

A goal is the top-level unit of work. It has:
- A description in plain English
- A trust level (`supervised` / `guided` / `autonomous`)
- An optional budget limit in USD
- A status (`active` / `complete`)

Goals are never directly executed - they are decomposed into tasks.

### Tasks

A task is an atomic unit of work completable in under 30 minutes. Each task has:
- A description (one clear sentence)
- Scope (what is in/out)
- Skill tags (e.g. `["coding", "review"]`)
- Priority (1-10)
- Risk level (`low` / `medium` / `high`)
- Dependencies (other task IDs that must be done first)
- A verification plan (how to confirm it was done correctly)

Task status transitions:

```
pending -> locked -> running -> done
                 \-> pending (retry, up to 3x)
                 \-> failed (after 3 attempts)
                 \-> blocked (budget exceeded)
                 \-> cancelled (manually or by scan cleanup)
```

When all tasks for a goal reach a terminal state (`done`, `failed`, `blocked`, or `cancelled`), the worker automatically marks the goal `complete`.

### Skills

Skills are markdown files in `skills/` that provide domain-specific context to the executor. The worker matches skill tags on each task to load only relevant skill files - it does not dump all skills into every task context.

Current skills: `coding_task`, `ops_task`, `planning_task`, `research_task`, `review_task`, `verification`.

### Incidents

An incident is created automatically when:
- A task reaches `failed` status (severity: medium)
- The worker itself throws an unexpected exception (severity: high)
- The watchdog resets a stuck task (severity: medium)

Incidents have a severity ladder (low / medium / high) and are escalated by age if left open.

---

## Part IV - Running Goals

### The Fastest Path: run_goal.sh

For a single command that creates a goal, sets trust, and runs the worker:

```bash
./scripts/run_goal.sh "Summarize the open incidents and propose remediations" guided 2.00
# Arguments: <description> <trust_level> [<budget_usd>]
```

This runs the full pipeline unattended. Check results in `artifacts/` and `logs/episodic.md`.

### Step by Step

**Step 1 - Create a goal:**
```bash
.venv/bin/python scripts/create_goal.py "Add input validation to the user signup form"
```
Claude Code decomposes this into 3-7 tasks and inserts them as `pending`. The goal starts at `supervised` trust.

**Step 2 - Review the task graph (optional):**
```bash
.venv/bin/python scripts/update_status.py
cat projects/harness-v1/status.md
```

**Step 3 - Set trust level:**
```bash
# List goals to find the ID
.venv/bin/python scripts/set_trust.py list

# Promote to guided (allows low/medium risk tasks to run without approval)
.venv/bin/python scripts/set_trust.py <goal-id-prefix> guided
```

**Step 4 - Set a budget (optional):**
```bash
# Limit the goal to $1.00 of Claude API spend
python3 -c "
import sqlite3
conn = sqlite3.connect('tasks.db')
conn.execute(\"UPDATE goals SET budget_limit=1.00 WHERE id LIKE '<prefix>%'\")
conn.commit()
"
```

**Step 5 - Run the worker:**
```bash
# Run all tasks for this goal
.venv/bin/python scripts/worker.py --goal-id <prefix>

# Or run one task at a time (supervised testing)
.venv/bin/python scripts/worker.py --once

# Or bypass HITL gates in guided mode (allows all tasks to run without prompts)
.venv/bin/python scripts/worker.py --goal-id <prefix> --no-hitl
```

**Step 6 - Check results:**
```bash
# Regenerate status
.venv/bin/python scripts/update_status.py

# View the HTML dashboard
.venv/bin/python scripts/export_status.py
open artifacts/dashboard.html

# View episodic memory (what ran, what was verified)
cat logs/episodic.md
```

### Running a Specific Task

If you know exactly which task to run:
```bash
.venv/bin/python scripts/worker.py --task-id <full-task-uuid>
```

---

## Part V - Trust and Budget Management

### Choosing a Trust Level

**Supervised** is the right default for:
- Any goal where you are not sure what the tasks will do
- Goals touching production systems or shared infrastructure
- First run of a new goal type

**Guided** is appropriate when:
- You have reviewed the task graph and the tasks look reasonable
- All tasks are low or medium risk
- You want the worker to run without constant interruption but still pause for high-risk steps

**Autonomous** is appropriate only when:
- The goal has run successfully at least once under guided trust
- All tasks have verified outputs on record
- You are comfortable with the worker taking any action the goal requires without asking

Promote trust deliberately:
```bash
.venv/bin/python scripts/set_trust.py <goal-prefix> autonomous
# Warning is printed - this is intentional
```

### Budget Limits

Budget limits are enforced **before** each task run, not after. When the goal's total spend reaches the limit, the remaining tasks are set to `blocked` with reason `BUDGET EXCEEDED`.

Good starting budgets:
- Ops audit (5 tasks): $1.50-$2.00
- Research synthesis (4 tasks): $1.00-$1.50
- Code review (3 tasks): $0.50-$1.00

Costs are tracked in `tasks.cost_usd` and rolled up to the goal level in `status.md`.

---

## Part VI - Monitoring and Incidents

### Status Dashboard

The markdown status board is always current after running `update_status.py`. For a richer view, export the HTML dashboard:

```bash
.venv/bin/python scripts/export_status.py
open artifacts/dashboard.html
```

The dashboard shows: task board counts, goal list with progress and cost, open incidents, and the 10 most recently completed tasks.

### Viewing Incidents

```bash
# All incidents
.venv/bin/python scripts/create_incident.py list

# Open incidents only
.venv/bin/python scripts/create_incident.py list --open
```

### Logging a Manual Incident

```bash
.venv/bin/python scripts/create_incident.py log "Unexpected output in artifact dir" \
  --severity medium \
  --task-id <task-id> \
  --description "artifact contained a binary file that was not expected"
```

### Resolving an Incident

`<incident-prefix>` is the first 8 or more characters of the incident UUID printed when it was created. Any unique prefix works.

```bash
.venv/bin/python scripts/create_incident.py resolve 4a8c2374 \
  --root-cause "worker timeout caused partial write" \
  --remediation "re-ran task, verified output, watchdog reset confirmed"
```

### Proactive Scan

The scan reads all `projects/*/handoff.md` files, flags stale open questions and blocked tasks (older than 2 days by default), and creates goals to address them:

```bash
# Dry-run: see what would be flagged
.venv/bin/python scripts/scan.py --dry-run

# Live: create goals for each flag
.venv/bin/python scripts/scan.py

# Adjust the age threshold
.venv/bin/python scripts/scan.py --age-days 3
```

---

## Part VII - Maintenance

### Watchdog

Run the watchdog manually anytime to check for stuck tasks:

```bash
# Dry-run first to see what would be reset
.venv/bin/python scripts/watchdog.py --dry-run

# Live reset (resets stuck tasks to pending, creates incidents)
.venv/bin/python scripts/watchdog.py

# Adjust the threshold (default: 30 minutes)
.venv/bin/python scripts/watchdog.py --threshold 60
```

### Incident Escalation

Manually trigger escalation to catch aged incidents:

```bash
.venv/bin/python scripts/escalate_incidents.py

# Dry-run to preview
.venv/bin/python scripts/escalate_incidents.py --dry-run

# Custom thresholds
.venv/bin/python scripts/escalate_incidents.py --low-hours 2 --medium-hours 4
```

### Artifact Sweep

Task artifact directories accumulate. Sweep old ones periodically:

```bash
# Preview what would be deleted (safe to run anytime)
.venv/bin/python scripts/sweep_artifacts.py --dry-run

# Delete artifact dirs older than 7 days (default)
.venv/bin/python scripts/sweep_artifacts.py

# Keep more history
.venv/bin/python scripts/sweep_artifacts.py --days 14
```

The sweep skips:
- Non-UUID directories (dashboard.html, launchd/, etc.)
- Artifact dirs belonging to tasks that are still active (pending / locked / running)

---

## Part VIII - Scheduling (macOS launchd)

Three recurring jobs are ready to activate. First generate the plists (already done as of M7):

```bash
.venv/bin/python scripts/schedule.py generate
# Writes to artifacts/launchd/
```

Review them:
```bash
cat artifacts/launchd/com.harness.watchdog.plist
```

Install (loads into launchd - runs automatically from now on):
```bash
.venv/bin/python scripts/schedule.py install
```

Check status:
```bash
.venv/bin/python scripts/schedule.py status
```

Uninstall:
```bash
.venv/bin/python scripts/schedule.py uninstall
```

Job schedule summary:
| Job | Schedule | What It Does |
|---|---|---|
| `com.harness.watchdog` | Every 30 min | Resets stuck tasks, creates incidents |
| `com.harness.scan` | Daily at 08:00 | Scans handoffs, creates goals for flags |
| `com.harness.escalate` | Every hour | Promotes aged open incidents |

---

## Part IX - Evals and Self-Improvement

### Running Evals

```bash
# Run the full suite (takes < 1 second)
.venv/bin/python scripts/run_evals.py

# Run one eval directly
.venv/bin/python evals/m6_features.py
```

Results are saved to `evals/results/` as JSON files with timestamps.

### Self-Improvement Loop

The improvement loop applies a targeted change to a skill file and checks whether the eval score holds:

```bash
.venv/bin/python scripts/improve.py \
  --target skills/coding_task.md \
  --change "Add a section on error handling patterns for Python async functions"
```

What happens:
1. Runs the full eval suite (baseline score)
2. Asks Claude Code to apply the change to the target file
3. Runs the eval suite again
4. If score held or improved: keeps the change
5. If score regressed: reverts via `git checkout HEAD -- <file>`
6. Logs the result to `evals/improvement_log.md`

The loop only touches the file you specify. It never self-modifies worker.py, the database schema, or eval files.

**Important limitation:** The evals test harness infrastructure - script existence, schema columns, logic gates. They do not measure Claude Code output quality. A skill file change that makes task execution worse will still show the same eval score and be kept. The loop is a "do no harm" guard, not a genuine quality signal. To make self-improvement meaningful, a held-out set of real tasks with known correct outputs is needed as a quality eval layer.

### Improvement Log

```bash
cat evals/improvement_log.md
```

Shows every improvement attempt: timestamp, target, change description, before/after score, and decision.

---

## Part X - Script Reference

### Goal and Task Management

| Script | Usage | Notes |
|---|---|---|
| `create_goal.py` | `create_goal.py "description"` | Decomposes via Claude Code, inserts tasks |
| `create_goal.py` | `--file goals/foo.md` | Read goal from file |
| `create_goal.py` | `--dry-run` | Show tasks without inserting |
| `set_trust.py` | `set_trust.py <prefix> guided` | Promote goal trust level |
| `set_trust.py` | `set_trust.py list` | List all goals and trust levels |
| `claim_task.py` | `claim_task.py` | Manually claim one pending task |

### Worker

| Flag | Effect |
|---|---|
| `--once` | Run one iteration and exit |
| `--task-id <id>` | Claim a specific task by ID |
| `--goal-id <prefix>` | Run all tasks for one goal |
| `--no-hitl` | Bypass HITL gates (guided: all risks; supervised: all tasks) |

### Monitoring and Ops

| Script | Usage |
|---|---|
| `update_status.py` | Regenerate `projects/harness-v1/status.md` |
| `export_status.py` | Write `artifacts/dashboard.html` |
| `scan.py --dry-run` | Preview scan flags |
| `scan.py` | Create goals for scan flags |
| `run_scan.sh` | Shell wrapper: scan + export status |
| `run_goal.sh <desc> <trust> [budget]` | One-command goal runner |

### Resilience

| Script | Usage |
|---|---|
| `watchdog.py` | Reset stuck tasks, create incidents |
| `watchdog.py --dry-run` | Preview only |
| `watchdog.py --threshold 60` | Custom threshold (minutes) |
| `escalate_incidents.py` | Escalate aged open incidents |
| `escalate_incidents.py --dry-run` | Preview only |
| `sweep_artifacts.py` | Delete old artifact dirs |
| `sweep_artifacts.py --dry-run` | Preview only |
| `sweep_artifacts.py --days 14` | Custom age threshold |
| `create_incident.py list` | List all incidents |
| `create_incident.py list --open` | Open incidents only |
| `create_incident.py log <title>` | Log a manual incident |
| `create_incident.py resolve <prefix>` | Mark incident resolved |

### Evals and Improvement

| Script | Usage |
|---|---|
| `run_evals.py` | Run full eval suite |
| `improve.py --target <file> --change <desc>` | Run self-improvement loop |
| `schedule.py generate` | Write launchd plists |
| `schedule.py install` | Load into launchd (macOS) |
| `schedule.py uninstall` | Unload from launchd |
| `schedule.py status` | Show launchd job status |

---

## Part XI - Troubleshooting

### Worker Claims a Task but Nothing Happens

- Check `logs/exec_<task-id>.md` for the executor output
- Check `artifacts/<task-id>/completion_note.md` for what Claude Code did
- If the task is stuck in `running`, the worker likely crashed - run the watchdog

### Budget Exceeded

Tasks are set to `blocked` with reason `BUDGET EXCEEDED: goal budget $X.XX already spent ($Y.YY used)`. To continue:
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('tasks.db')
conn.execute(\"UPDATE goals SET budget_limit=<new_limit> WHERE id='<goal_id>'\")
conn.execute(\"UPDATE tasks SET status='pending', escalation_reason=NULL WHERE goal_id='<goal_id>' AND status='blocked'\")
conn.commit()
"
```

### Task Keeps Failing

Check `artifacts/<task-id>/verification.md` for the verifier's FAIL reason. Common causes:
- Task description is ambiguous - the task graph needs to be more specific
- Skill tags don't match available skills - check `skills/` directory
- Verification plan is too strict for what Claude Code can produce

### Eval Suite Regression

If `run_evals.py` shows fewer passing evals after a change:
```bash
# Run the specific failing eval for details
.venv/bin/python evals/<failing_eval>.py

# Revert the last file change if it was a skill improvement
git diff --stat HEAD
git checkout HEAD -- skills/<file>
```

### tasks.db WAL Files

If you see `tasks.db-shm` and `tasks.db-wal` accumulating:
```bash
# Force WAL checkpoint (SQLite will do this automatically, but you can trigger it)
python3 -c "import sqlite3; conn = sqlite3.connect('tasks.db'); conn.execute('PRAGMA wal_checkpoint(FULL)'); conn.close()"
```

---

## Part XII - Quick Reference

```
# Start a goal (full pipeline)
./scripts/run_goal.sh "my goal description" guided 1.50

# Check what's running
.venv/bin/python scripts/update_status.py && cat projects/harness-v1/status.md

# View dashboard
.venv/bin/python scripts/export_status.py && open artifacts/dashboard.html

# Check for stuck tasks
.venv/bin/python scripts/watchdog.py --dry-run

# Check open incidents
.venv/bin/python scripts/create_incident.py list --open

# Run evals
.venv/bin/python scripts/run_evals.py

# Sweep old artifacts (preview first)
.venv/bin/python scripts/sweep_artifacts.py --dry-run

# Activate launchd scheduling
.venv/bin/python scripts/schedule.py install
```
