# Harness v1 Build Plan

**Project:** harness-v1  
**Mode:** harness-wrapper around Claude Code  
**Started:** 2026-06-26  
**Charter:** Build a self-improving agentic operating system that wraps Claude Code.

---

## Objective

Prove a durable, verifiable, self-improving agent loop on local infrastructure, then expand capability domain by domain. Start narrow, close the loop completely, then grow.

---

## Milestone 1 - Closed-Loop Baseline

**Target:** 2026-06-27  
**Status:** in-progress

Prove the complete pipeline end to end:

```
goal -> task graph -> claim -> execute (Claude Code) -> verify (subagent) -> evidence -> memory -> visible status
```

### Scope

- [ ] Directory structure complete
- [ ] tasks.db created with 5-table schema
- [ ] implementation-contract.md written
- [ ] scripts/init_db.py scaffolded
- [ ] scripts/worker.py scaffolded (full logic, pending human approval to run)
- [ ] scripts/create_goal.py scaffolded
- [ ] scripts/claim_task.py scaffolded
- [ ] skills/coding_task.md written
- [ ] skills/verification.md written
- [ ] evals/task_claim_atomicity.py written
- [ ] evals/smoke_test.md written
- [ ] projects/harness-v1/ canonical file pack complete
- [ ] HUMAN APPROVES -> execute one real goal end to end
- [ ] All 9 milestone proof-of-progress metrics checked

### Definition of Done

The human can open status.md, see what the system ran, find the evidence in artifacts/, read the episodic log in logs/, and confirm the task was verified by a separate subagent - all without asking the agent to explain what it did.

---

## Milestone 2 - Skills, Profiles, and Eval Harness

**Target:** ~2026-06-30  
**Status:** not started

### Scope

- [ ] Skills system: 5+ domain skills (coding, verification, research, review, planning)
- [ ] Profile loader: reads skill tags from task, loads relevant skill files into context
- [ ] Eval harness: offline test runner against a set of tasks and expected outcomes
- [ ] Eval tracking: pass rate, cost-to-pass, time-to-pass stored in evals/results/
- [ ] Model routing stub: per-skill model config (even if only one model now)
- [ ] Budget tracking: tokens_used updated in tasks table after each run
- [ ] Second domain: research/analysis task type working end to end
- [ ] Dashboard artifact: auto-generated markdown report of task board state

### Definition of Done

Run the eval harness, get a pass rate, then make one improvement, re-run, and confirm score stayed the same or improved.

---

## Milestone 3 - Self-Improvement Loop + Proactive Monitoring

**Target:** ~2026-07-07  
**Status:** complete (2026-06-27)

### Scope

- [x] Self-improvement loop: one-change / eval-before-after / keep or revert
- [x] Improvement log in evals/improvement_log.md
- [x] Proactive monitoring: scan projects for stale handoffs, blocked tasks, unanswered open questions
- [x] Proactive goal generation from scan results
- [x] Recurring ops: scheduled scans (cron or manual trigger - scripts/run_scan.sh)
- [ ] External intelligence feed stub: weekly digest (deferred - requires network)
- [x] Third domain: ops task type scaffolded (skills/ops_task.md)
- [x] Trust level concept: supervised/guided/autonomous, scripts/set_trust.py for promotion
- [x] Cost tracking: cost_usd column in tasks, per-goal cost view in status.md

### Definition of Done

- Scan.py detects stale handoffs and auto-queues goals
- Improvement loop ran on ops skill: 2/2 -> 2/2, change kept (evals/improvement_log.md)
- Eval suite expanded to 2 evals (m3_features + task_claim_atomicity)

---

## Milestone 4 - Autonomous Loop + Real Workloads

**Target:** ~2026-07-14  
**Status:** complete (2026-06-27)

### Scope

- [x] Trust-level gating enforced in worker.py (supervised/guided/autonomous behavior)
- [x] Budget cap: goals.budget_limit enforced before each task run
- [x] Scan dashboard: markdown summary artifact written on every scan run
- [x] First guided-trust ops goal run by worker (3/5 tasks done before $0.50 cap)
- [x] Cost alerting: task blocked when goal budget exceeded ($0.5301 > $0.50)
- [x] Eval suite expanded to 3 evals: m3_features + m4_features + task_claim_atomicity (3/3 PASS)
- [x] worker.py --goal-id flag: run all tasks for a specific goal
- [x] worker.py --no-hitl flag: bypass HITL gates per invocation

### Definition of Done

Worker ran real ops goal `2c0f463d` in guided mode. Budget cap triggered at task 3. All 3 evals pass. Scan dashboard generated on every scan run.

---

## Milestone 5 - Incidents, Unattended Execution, and Autonomous Run

**Target:** ~2026-07-21
**Status:** complete (2026-06-27)

### Scope

- [x] Incident tracking: `incidents` table, auto-created on task failure with reason + context
- [x] `scripts/create_incident.py`: CLI to log incidents and link to task/goal
- [x] `scripts/run_goal.sh`: unattended goal runner (create goal + worker in one command)
- [x] `scripts/export_status.py`: HTML dashboard export to `artifacts/dashboard.html`
- [x] Autonomous goal `2010c7e7`: eval-audit, 4/4 tasks done, zero HITL gates triggered
- [x] `evals/m5_features.py`: 5/5 PASS; full suite 4/4 PASS (m3 + m4 + m5 + atomicity)

### Definition of Done

- Incident tracking wired in worker.py for task failure and worker exceptions
- `run_goal.sh` accepts goal description, sets trust, optionally sets budget, runs worker
- `artifacts/dashboard.html` exported (14KB, all sections: task board, goals, incidents, recent tasks)
- Autonomous goal `2010c7e7` ran 4 tasks without any HITL gate
- Eval suite: 4/4 PASS

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────┐
│                   Human / User                      │
│  (status.md, handoff.md, approval requests)         │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│              Harness Control Plane                  │
│  tasks.db  │  status.md  │  projects/  │  logs/     │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│              scripts/worker.py                      │
│  1. claim_task (atomic lock)                        │
│  2. load skill profile                              │
│  3. invoke Claude Code (executor subagent)          │
│  4. invoke Claude Code (verifier subagent)          │
│  5. record evidence to artifacts/                   │
│  6. update tasks.db                                 │
│  7. update memory (knowledge.md + episodic log)     │
│  8. update status.md                               │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│           Claude Code (Execution Engine)            │
│  Tool execution, file edits, sub-agents, MCP        │
└─────────────────────────────────────────────────────┘
```

---

## Risk Register

| Risk | Level | Mitigation |
|---|---|---|
| Worker crashes mid-task, task stuck as 'locked' | Medium | 30-min timeout check + unlock + re-queue |
| Verifier self-certifies (same context as executor) | High | ENFORCE separate subprocess invocation |
| tasks.db WAL corruption | Low | SQLite WAL is robust; daily backup script |
| Claude Code CLI not on PATH | Medium | worker.py checks PATH at startup |
| Scope creep into Milestone 2 during Milestone 1 | Low | Strict milestone gate in tasks.md |
