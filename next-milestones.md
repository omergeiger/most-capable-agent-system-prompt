# Next Milestones - Implementation Order

**Status:** Milestone 1 complete (2026-06-26). Proceed in the order below.

---

## M2-1: Skill Profile Loader

**Goal:** Worker dynamically injects relevant skill files into executor prompt based on task `skill_tags`.

**Why first:** Every subsequent task run benefits immediately. Quality multiplier before adding more complexity.

**Scope:**
- Read `skill_tags` JSON from the claimed task
- Scan `skills/` for files whose trigger conditions match any tag
- Inject matched skill file content into the executor system prompt
- Log which skills were loaded in the execution log

**Verification:** Run a task with `skill_tags: ["coding"]` and confirm `skills/coding_task.md` content appears in the executor prompt sent to Claude.

---

## M2-2: Budget Tracking

**Goal:** Record token usage per task in `tasks.db` after each run.

**Why second:** Low effort, but required as the measurement foundation for the self-improvement loop. No signal = no optimization.

**Scope:**
- Parse token count from Claude subprocess output (usage footer)
- Add `tokens_used` and `duration_seconds` columns to `tasks` table (migration script)
- Write values after each executor and verifier run
- Show per-task cost in `scripts/claim_task.py show TASK_ID`

**Verification:** Run one task, then `claim_task.py show TASK_ID` shows non-zero `tokens_used`.

---

## M2-3: Eval Harness Runner

**Goal:** `scripts/run_evals.py` discovers and runs all `evals/*.py` files, stores results, prints a summary.

**Why third:** Makes the self-improvement loop mechanically possible. Needs budget tracking to record cost-to-pass.

**Scope:**
- Discover all `evals/*.py` via glob
- Run each as a subprocess, capture exit code + stdout
- Write result to `evals/results/<timestamp>_<eval_name>.json` (pass/fail, duration, stdout)
- Print summary table: eval name | result | duration
- Exit 0 if all pass, 1 if any fail

**Verification:** `scripts/run_evals.py` runs `task_claim_atomicity.py`, writes a result file, prints a summary table with PASS.

---

## M2-4: Domain Skills Expansion

**Goal:** Add 3 new skill files and prove a second task domain (research/analysis) works end-to-end.

**Why fourth:** Skill loader is ready; now give it more skills to load. Broadens the types of goals the harness can handle.

**Scope:**
- Write `skills/research_task.md` (web research, source citation, output format)
- Write `skills/review_task.md` (code review, checklist, output format)
- Write `skills/planning_task.md` (decomposition, dependency mapping, risk tagging)
- Run one research-type goal through worker end-to-end with skill loader active

**Verification:** A research task completes with `Status: PASS` in verification.md and the execution log shows `skills/research_task.md` was loaded.

---

## M2-5: Proactive Monitoring Scan

**Goal:** `scripts/scan.py` reads all project handoff files, flags stale items, and auto-creates goals for them.

**Why fifth:** First step toward the system working without being asked. Feeds the self-improvement loop with real signals.

**Scope:**
- Read all `projects/*/handoff.md` files
- Flag: open questions unanswered for >2 days, blocked tasks with no activity, stale `now` queues
- For each flag: call `create_goal.py` to generate a resolution goal
- Write scan report to `logs/scan_<timestamp>.md`
- Print summary of flags found and goals created

**Verification:** Manually introduce a stale open question into a handoff.md, run `scan.py`, confirm a new goal appears in `tasks.db`.

---

## M2-6: Self-Improvement Loop

**Goal:** One-change / eval-before-after / keep-or-revert cycle, logged to `evals/improvement_log.md`.

**Why last:** Capstone. Requires all prior milestones: skill loader, budget tracking, eval runner, and real eval signal.

**Scope:**
- Pick one measurable eval metric (e.g., atomicity test pass rate, or task verification pass rate)
- Make one targeted change to a skill file or executor prompt
- Run eval harness before and after the change
- If score improves or holds: keep, log as WIN
- If score regresses: revert via git, log as REVERT
- Append entry to `evals/improvement_log.md`: change description, before score, after score, outcome

**Verification:** `evals/improvement_log.md` has at least one entry with before/after scores and a keep or revert decision. The loop ran without human intervention after the initial trigger.

---

## Implementation Notes

- Each milestone is a separate goal in `tasks.db` - use `create_goal.py` to decompose and track
- Do not start M2-3 (eval runner) before M2-2 (budget tracking) - the runner records cost-to-pass
- Do not start M2-6 (self-improvement) before M2-3 (eval runner) and M2-4 (domain skills) are verified
- M2-1 and M2-2 can be done in a single session - they are both small
- Update `projects/harness-v1/status.md` after each milestone completes
