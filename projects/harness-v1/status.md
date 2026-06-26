# Status - Harness v1

**Updated:** 2026-06-26  
**Session:** scaffolding

---

## NOW

**Active milestone:** Milestone 1 - Closed-Loop Baseline

**Current task:** M1-013 - HUMAN GATE: Review all Milestone 1 files

All scaffolding files for Milestone 1 have been created. The system is paused at the human review gate, awaiting approval to run any scripts.

**Completed this session:**
- M1-001: Directory structure
- M1-002: tasks.db with 5-table schema (WAL mode)
- M1-003: implementation-contract.md
- M1-004: plan.md (3 milestones)
- M1-005: tasks.md (Milestone 1 task list)
- M1-006: knowledge.md
- M1-007: decisions.md (8 key decisions)
- M1-008: status.md (this file)
- M1-009: scripts/ directory (4 scripts scaffolded)
- M1-010: skills/ (coding_task.md, verification.md)
- M1-011: evals/ (atomicity test + smoke test)
- M1-012: handoff.md

---

## NEXT

Once the human reviews and approves (M1-013):

1. **M1-014a:** Run `evals/task_claim_atomicity.py` to verify schema and atomic lock logic
2. **M1-014b:** Run `scripts/create_goal.py` to create the first goal and decompose into tasks
3. **M1-014c:** Run `scripts/worker.py` for one iteration (claim one task, execute, verify)
4. **M1-015:** Verify all 9 closed-loop metrics are passing

Then begin Milestone 2:
- Build skill profile loader
- Add 5 domain skills
- Build eval harness runner

---

## BLOCKED

- **M1-013:** Blocked on human review and approval
- **M1-014:** Blocked on M1-013 (cannot execute scripts until human approves)
- **M1-015:** Blocked on M1-014

No structural blockers (no missing tools, no schema errors, no network dependencies).

---

## IMPROVE

Known gaps to address as improvements in Milestone 2+:

- Skill profile loader: tasks declare `skill_tags` but there is no automatic skill-file injection yet
- Eval runner: `evals/task_claim_atomicity.py` exists but has no automated runner or reporting
- Budget tracking: `tokens_used` field exists in schema but is not updated by worker.py yet
- Status auto-update: `update_status.py` is scaffolded but not wired to post-task hook yet
- Timeout unlock: worker has timeout handling but no background "stuck task" sweeper yet
- Dead-letter triage: tasks that hit 3 failures need a triage workflow

---

## RECURRING

(Not yet active - will be defined in Milestone 3)

Planned recurring operations:
- Daily: scan projects/ for stale handoffs (handoff.md older than 48h with no update)
- Daily: check tasks.db for locked tasks older than 30min and unlock them
- Weekly: run full eval suite, record pass rates in evals/results/
- Weekly: run self-improvement loop (one candidate change + eval before/after)
- Weekly: external intelligence sweep (when network is unlocked)
- Session-end: always update handoff.md before stopping
