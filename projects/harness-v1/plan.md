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
**Status:** not started

### Scope

- [ ] Self-improvement loop: one-change / eval-before-after / keep or revert
- [ ] Improvement log in evals/improvement_log.md
- [ ] Proactive monitoring: scan projects for stale handoffs, blocked tasks, unanswered open questions
- [ ] Proactive goal generation from scan results
- [ ] Recurring ops: scheduled scans (cron or manual trigger until cron is ready)
- [ ] External intelligence feed stub: weekly digest of relevant repos/papers (manual until network allowed)
- [ ] Third domain: browser or ops task type scaffolded
- [ ] Trust level concept: defined levels (supervised/guided/autonomous), manual promotion for now
- [ ] Cost tracking: per-task and per-goal cost view in status.md

### Definition of Done

The system catches a stale project without being asked, generates a proactive goal, and starts working on it. One skill or eval was improved by the self-improvement loop with evidence.

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
