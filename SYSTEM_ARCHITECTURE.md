# Harness v1 - System Architecture

**Audience:** AI engineers who want to understand how the harness is built, what tradeoffs were made, what levers exist to tune behavior, and where the system is headed.
**Version:** 1.0 (Milestones 1-7 complete)

---

## 1. Architecture Overview

The harness is a thin, durable orchestration layer around Claude Code. It does not implement its own LLM calls - it delegates all inference to the `claude` CLI subprocess. Its job is to manage state, enforce workflow invariants, and close the verification loop that Claude Code alone leaves open.

### Layered View

```
+===========================================================+
|  HUMAN OPERATOR                                           |
|  - Defines goals in natural language                      |
|  - Sets trust levels (supervised / guided / autonomous)   |
|  - Reviews incidents, handoffs, dashboard                 |
+===========================================================+
                          |
+===========================================================+
|  HARNESS CONTROL PLANE                                    |
|                                                           |
|  tasks.db (SQLite WAL)                                    |
|  +---------+  +---------+  +-----------+  +-----------+  |
|  | goals   |  | tasks   |  | incidents |  | memory    |  |
|  +---------+  +---------+  +-----------+  +-----------+  |
|                                                           |
|  Canonical docs: status.md / handoff.md / episodic.md    |
+===========================================================+
                          |
+===========================================================+
|  WORKER (scripts/worker.py)                               |
|                                                           |
|  1. claim_task (atomic SQLite UPDATE...RETURNING)         |
|  2. check_hitl_gate (trust level x risk level)            |
|  3. check_budget (goal spend vs budget_limit)             |
|  4. load_skill_profiles (tag-based selection)             |
|  5. execute_task (Claude Code subprocess)                 |
|  6. verify_task (separate Claude Code subprocess)         |
|  7. update_task / create_incident                         |
|  8. append_episodic_memory                               |
+===========================================================+
          |                            |
+-----------------+          +-----------------+
| EXECUTOR        |          | VERIFIER        |
| Claude Code CLI |          | Claude Code CLI |
| (separate proc) |          | (separate proc) |
| full tools      |          | clean context   |
+-----------------+          +-----------------+
```

### Key Design Decisions

**SQLite as the state store.** All harness state lives in a single file. No network dependency, no external service, trivially portable, and WAL mode provides concurrent-reader safety. The tradeoff is that multi-machine distribution is not possible without replacing the store.

**Claude Code as the execution engine, not the harness itself.** The harness knows nothing about how to write code, read files, or make tool calls - it delegates all of that to `claude`. This means the harness stays stable as Claude improves. The harness is a wrapper, not an agent.

**Verifier isolation enforced by process boundary.** The executor and verifier are separate subprocess invocations with no shared in-process state. This is enforced structurally, not by prompt instruction. A single process with two contexts can self-certify; two processes cannot.

**Trust is per-goal, not global.** Elevating one goal to autonomous does not affect how any other goal runs. This contains the blast radius of trust decisions.

---

## 2. Database Schema

### goals

```sql
CREATE TABLE goals (
    id           TEXT PRIMARY KEY,  -- UUID
    description  TEXT NOT NULL,
    project_id   TEXT,
    status       TEXT NOT NULL DEFAULT 'active',  -- active | complete
    trust_level  TEXT NOT NULL DEFAULT 'supervised',
    budget_limit REAL,              -- NULL = unlimited
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
)
```

`budget_limit` is checked before each task execution. Enforcement is pre-task, not post-task - no task starts if the goal has already hit its limit.

### tasks

```sql
CREATE TABLE tasks (
    id                TEXT PRIMARY KEY,
    goal_id           TEXT REFERENCES goals(id),
    project_id        TEXT,
    description       TEXT NOT NULL,
    scope             TEXT,
    mindset           TEXT,
    context           TEXT,
    skill_tags        TEXT,          -- JSON array: ["coding", "review"]
    status            TEXT NOT NULL DEFAULT 'pending',
    depends_on        TEXT,          -- JSON array of task UUIDs
    owner             TEXT,
    reviewer          TEXT,
    priority          INTEGER NOT NULL DEFAULT 5,
    risk_level        TEXT NOT NULL DEFAULT 'low',
    budget_limit      REAL,          -- task-level override (rarely used)
    tokens_used       INTEGER DEFAULT 0,
    cost_usd          REAL DEFAULT 0.0,
    attempts          INTEGER NOT NULL DEFAULT 0,
    verification_plan TEXT,
    evidence          TEXT,          -- JSON: execution result + verifier verdict
    artifacts         TEXT,          -- JSON: list of artifact dir paths
    escalation_reason TEXT,          -- set when HITL or budget gate fires
    locked_at         TEXT,
    completed_at      TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
)
```

The `evidence` JSON field is the task's memory: it stores the execution result, verification verdict, and cost for every attempt. The `depends_on` JSON array is resolved at claim time - a task with unresolved dependencies cannot be claimed.

### incidents

```sql
CREATE TABLE incidents (
    id                TEXT PRIMARY KEY,
    severity          TEXT NOT NULL DEFAULT 'low',   -- low | medium | high
    title             TEXT NOT NULL,
    description       TEXT,
    task_id           TEXT,
    goal_id           TEXT,
    status            TEXT NOT NULL DEFAULT 'open',  -- open | resolved
    root_cause        TEXT,
    remediation       TEXT,
    escalated_at      TEXT,          -- added by escalate_incidents.py
    escalation_count  INTEGER DEFAULT 0,
    created_at        TEXT NOT NULL,
    resolved_at       TEXT
)
```

Incidents are append-only in practice. Resolution adds `root_cause`, `remediation`, and `resolved_at` but does not delete the record. This preserves the audit trail.

### State Machine

```
                  +--------+
     (depends     |        |  (worker polls)
      resolved)   |PENDING |<-------------------+
                  |        |                    |
                  +---+----+                    |
                      |                         |
           (atomic    |                         |
            claim)    v                         |
                  +--------+                    |
                  |        |  (HITL gate blocks)|
                  |LOCKED  +--------------------+
                  |        |  (budget exceeded) -> BLOCKED
                  +---+----+
                      |
           (worker    |
            starts)   v
                  +--------+
                  |        |  (max attempts)
                  |RUNNING +-----> FAILED -> [INCIDENT]
                  |        |
                  +---+----+
                      |
           (PASS)     |  (FAIL, attempts < 3)
                      +----> PENDING (retry)
                      |
                      v
                  +--------+
                  |  DONE  |
                  +--------+
```

---

## 3. Execution Pipeline - Deep Dive

### Step 1: Claim (Atomic Lock)

```python
cur = conn.execute("""
    UPDATE tasks
    SET status = 'locked',
        locked_at = ?,
        attempts = attempts + 1,
        updated_at = ?
    WHERE id = (
        SELECT id FROM tasks
        WHERE status = 'pending'
          AND (depends_on IS NULL OR depends_on = '[]'
               OR NOT EXISTS (
                   SELECT 1 FROM json_each(tasks.depends_on) dep
                   INNER JOIN tasks t2 ON t2.id = dep.value
                   WHERE t2.status NOT IN ('done')
               ))
        ORDER BY priority DESC, created_at ASC
        LIMIT 1
    )
    AND status = 'pending'
    RETURNING *
""", (now, now))
```

The atomicity guarantee comes from SQLite's `UPDATE ... RETURNING` pattern. The `WHERE status = 'pending'` in the outer UPDATE is the critical lock - even if two workers read the same subquery result simultaneously, only one UPDATE will find `status = 'pending'` and succeed. The other gets zero rows returned. This was verified by an 8-thread race test in M6: 8 threads simultaneously claiming one task, exactly 1 succeeds.

Dependency resolution happens inside the subquery using `json_each()` - tasks with unsatisfied `depends_on` arrays are excluded from selection entirely.

### Step 2: Trust Gate

```
trust_level x risk_level -> gate decision

supervised  x any       -> BLOCK (unless --no-hitl)
guided      x low       -> PROCEED
guided      x medium    -> PROCEED
guided      x high      -> BLOCK (unless --no-hitl)
autonomous  x any       -> PROCEED
```

A blocked task is returned to `pending` with `escalation_reason` set to the gate message. The worker does not crash - it simply does not execute the task and moves on.

### Step 3: Budget Gate

```python
spent = SUM(cost_usd WHERE goal_id = X AND status IN ('done', 'failed'))
if spent >= goal.budget_limit:
    task.status = 'blocked'
    task.escalation_reason = f"BUDGET EXCEEDED: ${spent:.4f} >= ${budget:.4f}"
```

Enforcement is against **already-spent** cost, not projected cost. This means a goal could technically overspend slightly if multiple tasks complete simultaneously (in a multi-worker scenario). In single-worker mode, which is the current design, the enforcement is exact.

### Step 4: Skill Profile Loading

Skills are not injected globally - they are loaded per-task based on `skill_tags`. Each skill file contains a `**Trigger conditions:**` line that lists which tags activate it:

```
**Trigger conditions:** "coding", "testing", "debugging"
```

The loader iterates all skill files, parses the trigger line, and computes the intersection with the task's `skill_tags`. Only matching skill files are concatenated into the executor prompt. This keeps the context window lean for simple tasks.

The current tag-to-skill mapping:

| Tags | Skill Loaded |
|---|---|
| `coding`, `testing`, `debugging` | `coding_task.md` |
| `ops`, `infrastructure`, `maintenance` | `ops_task.md` |
| `planning`, `decomposition`, `architecture` | `planning_task.md` |
| `research`, `analysis`, `investigation` | `research_task.md` |
| `review`, `audit`, `quality` | `review_task.md` |
| `verification`, `testing` | `verification.md` |

### Step 5: Executor

```python
result = subprocess.run(
    ["claude", "--print", "--output-format", "json", prompt],
    capture_output=True, text=True,
    timeout=TASK_TIMEOUT, cwd=REPO_ROOT,
)
```

The executor prompt contains: task description, scope, context, verification plan, skill profiles, and artifact directory instructions. The `--output-format json` flag returns structured output including `usage`, `total_cost_usd`, and `duration_ms` alongside the result text.

`TASK_TIMEOUT = 1800` (30 minutes). Tasks that exceed this are killed and return `TIMEOUT: task exceeded 30 minutes`.

The working directory is `REPO_ROOT` so Claude Code has access to the full repository for any file operations the task requires.

### Step 6: Verifier

```python
result = subprocess.run(
    ["claude", "--print", "--output-format", "json", verifier_prompt],
    capture_output=True, text=True,
    timeout=300, cwd=REPO_ROOT,
)
```

The verifier receives: the task description, the verification plan, and the artifacts directory path. It does **not** receive the executor's output. It reads the artifacts directory itself and writes `verification.md` with a `Status: PASS` or `Status: FAIL` verdict.

This is the critical isolation: the verifier reads evidence from disk, not from a shared variable or context. A future redesign could make this even stronger by running the verifier in a separate working directory with read-only access.

Verifier timeout is 300 seconds (5 minutes) - shorter than executor because verification is a read-only reasoning task.

### Step 7: Outcome Logic

```
success AND verified  -> done
success AND !verified -> pending (retry)
!success AND !verified -> pending (retry)
attempts >= MAX_ATTEMPTS -> failed + incident
```

`MAX_ATTEMPTS = 3`. The attempt counter is incremented at claim time, before execution. This means a task that is claimed but the worker crashes before executing still counts as an attempt - this is intentional, as it prevents infinite retry on tasks that consistently cause worker crashes.

---

## 4. Goal Decomposition

Goal decomposition is the only place in the pipeline where Claude Code is invoked without a human reviewing the output before it runs. The decomposition prompt instructs Claude to produce 3-7 task JSON objects, each with: `description`, `scope`, `skill_tags`, `priority`, `risk_level`, `depends_on`, `verification_plan`.

Dependencies in the decomposition response use description strings (not IDs, which don't exist yet). The `insert_goal_and_tasks` function resolves these by substring matching descriptions to task UUIDs before inserting.

**Known weakness:** The substring match for dependency resolution can fail if the decomposition uses paraphrased descriptions. This is acceptable at current scale but would need improvement for complex multi-step goals with tight ordering requirements.

**Decomposition dry-run:**
```bash
.venv/bin/python scripts/create_goal.py "my goal" --dry-run
```
This invokes Claude Code but does not insert into the database. Use it to review the task graph before committing.

---

## 5. Skill Routing

Skill routing is currently **tag-based exact match**. The advantages are speed (no embedding call needed), determinism, and zero external dependencies. The disadvantages are that skill tags must be set correctly at task creation, and the decomposition model must use the correct tag vocabulary.

### Current Skill Files

Each skill file has this structure:
```markdown
# [Domain] Task Skill

**Trigger conditions:** "tag1", "tag2", "tag3"

## Approach
...

## Quality Standards
...

## Common Patterns
...

## Anti-Patterns
...
```

The `**Trigger conditions:**` line is parsed by a regex in `load_skill_profiles()`. If no quoted tokens are found, it falls back to comma-splitting after the colon.

### Tuning Skill Routing

To add a new skill:
1. Create `skills/new_domain.md` with a `**Trigger conditions:**` line
2. Include the matching tags in task `skill_tags` when creating goals
3. No other changes needed - the loader auto-discovers all `*.md` files in `skills/`

To make skill selection stricter:
- Require exact match (current behavior)

To make it fuzzier (future):
- Replace tag intersection with embedding cosine similarity between task description and skill file headers
- Cost: one embedding call per task claim (negligible)
- Benefit: works even if decomposition uses non-standard tags

---

## 6. Trust and Budget System

### Trust Level Enforcement

Trust is enforced in `check_hitl_gate()`, which is called **after** the task is claimed and **before** it is executed. A blocked task is returned to `pending` (not abandoned) so that when a human approves the gate (either by promoting trust or using `--no-hitl`), the task can be re-claimed and run.

The `--no-hitl` flag bypasses the HITL gate for the current worker invocation only. It does not persist to the goal record. This is intentional - `--no-hitl` is a one-time override, not a permanent trust promotion.

### Budget Enforcement

Budget is checked against the **completed** spend, not the estimated spend. This means:
- A goal with `budget_limit = $1.00` and `$0.95` spent will attempt the next task
- If that task costs `$0.10`, total becomes `$1.05`, and subsequent tasks are blocked
- The goal slightly overshoots the budget on the final task

This design avoids the problem of cost estimation errors blocking tasks before they run. Actual cost is always accurate; estimated cost is not.

**Tuning budget behavior:**

| Want | Change |
|---|---|
| Stricter enforcement | Deduct estimated cost at claim time (requires cost prediction model) |
| Per-task limits | Set `budget_limit` on the task row directly |
| No budget | Leave `goal.budget_limit` NULL |
| Retroactive block | Write a scan check that blocks goals over budget after the fact |

---

## 7. Verification System

### Why a Separate Process?

Verification isolation is the most important architectural invariant in the harness. The failure mode it prevents: an executor that writes a plausible-looking artifact and then certifies its own work as PASS. This is the agentic equivalent of the fox guarding the henhouse.

By running the verifier as a separate subprocess with no shared state, the structural guarantee is:
- The verifier cannot read the executor's in-memory reasoning
- The verifier cannot be biased by the executor's prompt history
- The verifier must form its own independent judgment from physical evidence on disk

### Verification Evidence Chain

```
executor writes:
  artifacts/<task-id>/
    completion_note.md        (what was done)
    <any other output files>

verifier reads:
  artifacts/<task-id>/        (the above)
  task.description            (from the original task)
  task.verification_plan      (from the original task)

verifier writes:
  artifacts/<task-id>/
    verification.md           (PASS or FAIL with reason)
```

### Tuning Verification

| Want | Change |
|---|---|
| Stricter verification | Tighten the `verification_plan` in the task |
| Faster verification | Reduce verifier timeout (currently 300s) |
| Verifier cannot access executor logs | Pass only the artifacts dir, not log paths |
| Human-in-loop verification | Add a `review_required` flag, pause before verifier |
| Multi-verifier consensus | Run N verifier processes, require majority PASS |

The verifier prompt template is in `worker.py:build_verifier_prompt()`. This is the most impactful single string to tune. The current template asks the verifier to check the artifacts directory, read `completion_note.md`, apply the verification plan, and write `verification.md`. A stricter template might require the verifier to list every specific assertion it checked.

---

## 8. Incident Management

### Auto-Creation Triggers

| Trigger | Severity | Where |
|---|---|---|
| Task reaches `failed` status | medium | `worker.py:run_once()` |
| Worker throws uncaught exception | high | `worker.py:run_once()` except block |
| Watchdog resets a stuck task | medium | `watchdog.py:create_incident()` |
| Manual CLI log | user-set | `create_incident.py log` |

### Escalation Ladder

```
open + age > 1hr  -> low becomes medium
open + age > 2hr  -> medium becomes high
high stays high   -> human must resolve
```

Escalation is idempotent: running `escalate_incidents.py` twice in a row produces the same result. The `escalation_count` column tracks how many times an incident has been promoted - useful for detecting incidents that are being repeatedly ignored.

### Schema Additions (M6)

`escalated_at` and `escalation_count` were added to the incidents table via `ALTER TABLE`. The `ensure_escalation_columns()` function in `escalate_incidents.py` runs this migration idempotently on every invocation, so the script is safe to run on a database that predates these columns.

---

## 9. Eval Harness

### Design Philosophy

Evals test the **harness infrastructure**, not the quality of Claude Code's outputs. They verify:
- Do the right scripts exist?
- Does the logic produce the right outcome on a controlled synthetic input?
- Does the atomicity guarantee hold under concurrency?

They do not run Claude Code or make network calls (except M5's `export_status.py` check which runs a subprocess). This makes them fast (< 1 second total) and reliable.

### Eval Structure

```python
def check_something() -> bool:
    print("check_something: description of what is being tested")
    # ... setup, run, assert ...
    if failure:
        print(f"  FAIL: reason")
        return False
    print(f"  PASS: what was confirmed")
    return True

def main() -> bool:
    results = [check_a(), check_b(), check_c(), ...]
    passed = sum(results)
    print(f"\n--- Results: {passed}/{len(results)} passed ---")
    return passed == len(results)
```

Each eval is a standalone runnable script that exits 0 on full pass, 1 on any failure. `run_evals.py` discovers all `evals/m*.py` + `evals/task_claim_atomicity.py` files and runs them in alphabetical order.

### Adding an Eval

1. Create `evals/m8_features.py` following the pattern above
2. It will be auto-discovered by `run_evals.py` on next run
3. Results are automatically saved to `evals/results/<timestamp>_<name>.json`

### Eval Results Storage

```json
{
    "eval": "m6_features",
    "passed": 5,
    "total": 5,
    "duration_s": 0.04,
    "timestamp": "2026-06-27T15:05:40",
    "pass_rate": 1.0
}
```

These JSON files are the ground truth for the self-improvement loop's before/after comparison.

---

## 10. Self-Improvement Loop

### Loop Mechanics

```
run_evals() -> baseline (X/N)
apply_improvement(target, change_description)  [Claude Code edits the file]
run_evals() -> post-change (Y/N)
if Y/N >= X/N: KEEP
else: git checkout HEAD -- <target>; REVERT
append_to improvement_log.md
```

The improvement loop is conservative by design: it only keeps changes that hold the score, never changes that regress it. "Same score" counts as success because adding content to a skill file should not break existing evals.

### What Can Be Improved

The loop is designed to modify **skill files** only. Skill files are the only component that:
- Directly affects execution quality (they are injected into the executor prompt)
- Can change without breaking harness invariants
- Are safe to revert via git

The loop should **not** be pointed at:
- `worker.py` (breaks execution pipeline)
- `scripts/init_db.py` (breaks schema)
- `evals/*.py` (would allow evals to certify their own changes)

### Limitations

The current loop measures improvement only by **eval pass rate**. This is a weak signal when all evals are passing (6/6) - there is no room for improvement by score alone. A stronger signal would be task completion rate, verifier pass rate, cost-per-task, or time-to-complete across a held-out eval set of real tasks.

This is the primary architectural gap in the self-improvement system: the evals test harness integrity, not task execution quality. A separate "task quality eval" set is needed to make self-improvement meaningful.

---

## 11. Observability

### Layers

| Layer | File/Table | Purpose | Updated By |
|---|---|---|---|
| Live state | `tasks.db` | Ground truth for all task/goal/incident state | worker.py, scripts |
| Human summary | `status.md` | Markdown board for quick human review | `update_status.py` |
| HTML dashboard | `dashboard.html` | Rich single-page view with all sections | `export_status.py` |
| Episodic log | `logs/episodic.md` | Append-only record of task outcomes | `worker.py` |
| Exec logs | `logs/exec_<id>.md` | Full executor output per task | `worker.py` |
| Scan reports | `logs/scan_<ts>.md` | Proactive scan findings | `scan.py` |
| Improvement log | `evals/improvement_log.md` | Self-improvement history | `improve.py` |
| Eval results | `evals/results/*.json` | Timestamped pass/fail per eval | `run_evals.py` |
| Artifacts | `artifacts/<task-id>/` | Task outputs, completion notes, verification | executor + verifier |

### What Is Missing

- **Metrics time series:** No time-series store for cost-per-day, tasks-per-hour, or verifier pass rate over time. The JSON result files in `evals/results/` are the closest thing.
- **Alerting:** Incidents exist but there is no push notification when a high-severity incident is created. Adding a webhook call in `create_incident()` would address this.
- **Distributed tracing:** Task execution spans are not correlated across the executor and verifier subprocesses. The shared task ID in the artifact directory is the only linking mechanism.

---

## 12. Performance Knobs

These are the configuration points most likely to affect system behavior at scale.

### Worker Timing

| Constant | Location | Default | Effect of Increasing |
|---|---|---|---|
| `POLL_INTERVAL` | `worker.py` | 30s | Fewer DB reads when idle; slower response to new tasks |
| `TASK_TIMEOUT` | `worker.py` | 1800s | More time for complex tasks; longer stuck-task detection window |
| `MAX_ATTEMPTS` | `worker.py` | 3 | More retries before failure; higher cost on flaky tasks |

### Watchdog and Escalation Timing

| Parameter | Default | Tuning |
|---|---|---|
| Stuck-task threshold | 30 min | Lower to catch faster; raise for long-running tasks |
| Low-severity escalation | 1 hour | Raise if you get too many low incidents |
| Medium-severity escalation | 2 hours | Raise if incidents need longer resolution time |
| Launchd watchdog interval | 30 min | Match to TASK_TIMEOUT for best coverage |

### Budget

| Pattern | Recommendation |
|---|---|
| Simple ops goal (3-5 tasks) | $0.50-$1.00 |
| Research/synthesis (4-6 tasks) | $1.00-$2.00 |
| Code change with review (4-7 tasks) | $1.50-$3.00 |
| Unlimited (trusted goal) | Leave NULL |

The biggest driver of cost is verifier calls - each task runs two Claude Code invocations. A task that takes 30 min to execute and 5 min to verify spends ~85% of its token budget on execution.

### Skill File Size

Each loaded skill file is injected verbatim into the executor prompt. Skill files should be:
- Under 500 lines (to avoid consuming too much of the context window)
- Specific enough to change behavior, but not so long they bury the task description

The current skill files are 50-150 lines each. If skill context is becoming a budget concern, consider splitting large skill files or shortening them.

### Goal Decomposition Quality

The most impactful tuning lever is the decomposition prompt in `create_goal.py`. Better decomposition produces smaller, clearer, less risky tasks that pass verification on the first attempt. Specifically:

- Tasks with vague descriptions fail verification more often (verifier cannot confirm what "done" looks like)
- Tasks with specific, testable verification plans pass more reliably
- Tasks that are too large (>30 min scope) time out

The decomposition prompt is `DECOMPOSITION_PROMPT_TEMPLATE` in `create_goal.py`. It is the single string most worth iterating on as the harness is applied to new domains.

---

## 13. Future Improvement Options

These are listed roughly in order of impact, given the current state of the system.

### High Impact

**Task quality eval set.** The current 6 evals test harness integrity, not Claude Code output quality. A held-out set of 10-20 representative tasks with known correct outputs would allow the self-improvement loop to actually improve execution quality - not just maintain infrastructure integrity. This is the most important gap.

**Parallel task execution.** The worker currently processes one task at a time. Independent tasks (those with no shared `depends_on` edges) could be run concurrently. The claim atomicity guarantee already holds under concurrency (proven by the 8-thread eval). The worker would need a thread pool and a mechanism to track which artifact dirs are in-flight.

**Real workload domains.** Every autonomous goal to date has been about the harness itself. Pointing the harness at a real external problem (code review, research digest, PR triage) is the next capability milestone. Gaps will surface that cannot be anticipated in advance.

### Medium Impact

**Smarter skill routing.** Replace tag-based matching with embedding cosine similarity. This allows skills to be matched to task descriptions that don't use the exact tag vocabulary. Cost: one small embedding call per task claim. Benefit: skills are loaded correctly even when the decomposition uses synonyms or paraphrases.

**Cost prediction at claim time.** Estimate task cost from description length, skill count, and task type before executing. Use this to enforce a stricter budget gate: block tasks where `spent + estimated > budget` rather than waiting for actual overspend. Requires a simple calibration dataset of past tasks with their actual costs.

**Improved dependency resolution.** The current substring match in `insert_goal_and_tasks()` can fail when decomposition uses paraphrased descriptions. Replace with embedding similarity matching or require the decomposition model to output explicit dependency indices rather than description strings.

**Verifier consensus.** For high-risk tasks, run N=3 verifier processes and require majority PASS. This reduces false positives (incorrect PASS verdicts from a single verifier with a bad context) at the cost of 3x verifier token spend.

### Lower Impact (But Good Ops Hygiene)

**WAL checkpoint script.** The WAL files (`tasks.db-shm`, `tasks.db-wal`) are managed automatically by SQLite but can grow if no checkpoint runs. A daily `PRAGMA wal_checkpoint(FULL)` via launchd would keep the WAL trimmed.

**Incident webhook.** When `create_incident()` is called with `severity='high'`, fire a POST to a configurable webhook URL (Slack, PagerDuty, etc.). One function addition to `worker.py`; no schema changes.

**Task graph visualization.** Given a goal ID, render the `depends_on` graph as ASCII or a simple DOT file. Useful for reviewing complex decompositions before running them.

**Archival of completed goals.** Goals and their tasks accumulate indefinitely. A `scripts/archive_goal.py` that moves completed goals to a separate `archive` table (or a separate SQLite file) would keep the active DB lean.

**Multi-project support.** The `project_id` columns in `goals` and `tasks` are wired into the schema but unused. Activating project isolation (filtered queries, per-project scan, per-project budget) would allow multiple parallel projects to share one harness without cross-contamination.

---

## 14. Security Considerations

**Claude Code runs with full tool access.** The executor subprocess can read and write any file the OS user has access to. The harness does not sandbox it. High-risk tasks should be reviewed before running, and the `risk_level` field should be set accurately at decomposition time.

**`--dangerously-skip-permissions` in improve.py.** The self-improvement loop uses this flag to allow Claude Code to edit files without per-operation prompts. This is acceptable because `improve.py` is only invoked with a specific known target file, and the loop reverts on score regression. It should not be used in any other context.

**tasks.db is not encrypted.** All goal descriptions, task contents, and evidence are stored in plaintext. Do not store secrets in goal descriptions. If the harness is used on sensitive codebases, ensure the repository root has appropriate filesystem permissions.

**No authentication on the harness itself.** Any process that can write to `tasks.db` can insert goals and tasks. In a multi-user environment, access controls should be applied at the filesystem level.

---

## 15. Component Summary

```
scripts/
  init_db.py              Database schema creation + migrations
  create_goal.py          Goal decomposition via Claude Code
  claim_task.py           Manual atomic task claim
  worker.py               Main execution loop (claim->gate->exec->verify->record)
  set_trust.py            Goal trust level management
  create_incident.py      Incident CLI (list / log / resolve)
  escalate_incidents.py   Age-based incident severity promotion
  watchdog.py             Stuck-task detection and reset
  sweep_artifacts.py      Old artifact directory cleanup
  scan.py                 Proactive handoff monitoring + goal creation
  run_scan.sh             Shell wrapper: scan + status update
  run_goal.sh             Shell wrapper: create goal + set trust + run worker
  update_status.py        Regenerate status.md from DB
  export_status.py        Generate artifacts/dashboard.html
  improve.py              Self-improvement loop (eval-before/apply/eval-after/keep-or-revert)
  run_evals.py            Eval suite runner
  schedule.py             launchd plist generator + install/uninstall/status

evals/
  m3_features.py          Trust, cost tracking, ops skill, scan
  m4_features.py          Budget enforcement, guided trust, scan dashboard
  m5_features.py          Incidents, run_goal.sh, HTML export, autonomous goal
  m6_features.py          Watchdog, escalation, concurrent claim atomicity
  m7_features.py          Artifact sweep, schedule generate
  task_claim_atomicity.py Standalone N-thread race test

skills/
  coding_task.md          Tags: coding, testing, debugging
  ops_task.md             Tags: ops, infrastructure, maintenance
  planning_task.md        Tags: planning, decomposition, architecture
  research_task.md        Tags: research, analysis, investigation
  review_task.md          Tags: review, audit, quality
  verification.md         Tags: verification, testing
```
