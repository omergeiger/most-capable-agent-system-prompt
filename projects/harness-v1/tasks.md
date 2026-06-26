# Harness v1 Tasks

**Project:** harness-v1  
**Updated:** 2026-06-26

Tasks are indexed here and also stored in tasks.db once the worker is running. Until then, this file is the authoritative task list for Milestone 1 build work.

---

## Milestone 1 Tasks

### M1-001 - Create directory structure
- **Status:** done
- **Risk:** low
- **Priority:** 10
- **Skill tags:** scaffolding
- **Verification:** `ls -R` shows all dirs: skills/, evals/, logs/, artifacts/, projects/harness-v1/artifacts/, scripts/
- **Evidence:** Directory tree created 2026-06-26

### M1-002 - Create tasks.db with schema
- **Status:** done
- **Risk:** low
- **Priority:** 10
- **Skill tags:** database, scaffolding
- **Verification:** `sqlite3 tasks.db .tables` returns goals, incidents, memory_entries, sessions, tasks
- **Evidence:** tasks.db created 2026-06-26, WAL mode confirmed

### M1-003 - Write implementation-contract.md
- **Status:** done
- **Risk:** low
- **Priority:** 10
- **Skill tags:** planning, documentation
- **Verification:** File exists, contains all 7 required sections
- **Evidence:** implementation-contract.md written 2026-06-26

### M1-004 - Write projects/harness-v1/plan.md
- **Status:** done
- **Risk:** low
- **Priority:** 9
- **Skill tags:** planning
- **Verification:** File exists, 3 milestones defined with DoD
- **Evidence:** plan.md written 2026-06-26

### M1-005 - Write projects/harness-v1/tasks.md
- **Status:** done
- **Risk:** low
- **Priority:** 9
- **Skill tags:** planning
- **Verification:** This file
- **Evidence:** tasks.md written 2026-06-26

### M1-006 - Write projects/harness-v1/knowledge.md
- **Status:** done
- **Risk:** low
- **Priority:** 9
- **Skill tags:** documentation
- **Verification:** File exists with runtime profile, architecture summary
- **Evidence:** knowledge.md written 2026-06-26

### M1-007 - Write projects/harness-v1/decisions.md
- **Status:** done
- **Risk:** low
- **Priority:** 9
- **Skill tags:** documentation
- **Verification:** File exists with at least 5 key decisions
- **Evidence:** decisions.md written 2026-06-26

### M1-008 - Write projects/harness-v1/status.md with momentum queues
- **Status:** done
- **Risk:** low
- **Priority:** 10
- **Skill tags:** operations
- **Verification:** File has all 5 queues: now, next, blocked, improve, recurring
- **Evidence:** status.md written 2026-06-26

### M1-009 - Scaffold scripts/ directory (init_db, worker, create_goal, claim_task)
- **Status:** done
- **Risk:** low
- **Priority:** 8
- **Skill tags:** coding, orchestration
- **Verification:** All 4 scripts exist with complete logic (not yet executed)
- **Evidence:** Scripts written 2026-06-26

### M1-010 - Write skills/ directory (coding_task.md, verification.md)
- **Status:** done
- **Risk:** low
- **Priority:** 7
- **Skill tags:** skills, documentation
- **Verification:** 2 skill files exist with trigger conditions, SOP, schema
- **Evidence:** Skill files written 2026-06-26

### M1-011 - Write evals/ (task_claim_atomicity.py, smoke_test.md)
- **Status:** done
- **Risk:** low
- **Priority:** 7
- **Skill tags:** evals, coding
- **Verification:** Both eval files exist and are syntactically valid
- **Evidence:** Eval files written 2026-06-26

### M1-012 - Write projects/harness-v1/handoff.md
- **Status:** done
- **Risk:** low
- **Priority:** 10
- **Skill tags:** operations
- **Verification:** File exists with what-completed, what-next, what-blocked, open-questions
- **Evidence:** handoff.md written 2026-06-26

### M1-013 - HUMAN GATE: Review all Milestone 1 files
- **Status:** blocked
- **Risk:** low
- **Priority:** 10
- **Skill tags:** review
- **Depends on:** M1-001 through M1-012
- **Verification:** Human confirms files are legible and approves running scripts
- **Notes:** STOP HERE. Show human what was created. Await go-ahead.

### M1-014 - Execute: init_db.py (re-initialize if needed) + create_goal.py + worker.py
- **Status:** blocked
- **Risk:** medium
- **Priority:** 10
- **Skill tags:** execution, orchestration
- **Depends on:** M1-013 (human approval)
- **Verification:** One real task runs to 'done', evidence file exists, episodic log created

### M1-015 - Verify closed loop (atomicity test + all 9 metrics)
- **Status:** blocked
- **Risk:** low
- **Priority:** 10
- **Depends on:** M1-014
- **Verification:** evals/task_claim_atomicity.py passes, all 9 proof-of-progress items checked

---

## Milestone 2 Tasks

_(Not yet defined in detail - will be populated after Milestone 1 is complete and verified)_

- M2-001: Build skill profile loader
- M2-002: Add 5 domain skills
- M2-003: Build eval harness runner
- M2-004: Add budget tracking
- M2-005: Second domain task type end-to-end

---

## Milestone 3 Tasks

_(Not yet defined in detail - will be populated after Milestone 2 is complete)_

- M3-001: Self-improvement loop
- M3-002: Proactive monitoring scan
- M3-003: External intelligence feed stub
- M3-004: Trust level definitions
