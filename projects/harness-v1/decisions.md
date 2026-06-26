# Decision Log - Harness v1

**Project:** harness-v1  
**Updated:** 2026-06-26

Each entry records a decision with the alternatives considered and the reasoning. Decisions here are treated as stable until explicitly revised.

---

## D-001 - Harness-wrapper mode over native SDK

**Date:** 2026-06-26  
**Decision:** Build a harness wrapper around Claude Code rather than implementing a native agent SDK.

**Alternatives:**
- Native SDK (implement agent loop from scratch using Anthropic API)
- Hybrid (build SDK harness + Claude Code for UI/execution)

**Reasoning:** Claude Code is already a strong execution engine with tools, file editing, subagents, and MCP. Building from scratch would duplicate that work without benefit. The harness adds exactly what Claude Code lacks: durable task state, verifier isolation, compounding memory, and momentum queues. The wrapped runtime is a replaceable execution engine - if Claude Code changes, the harness contracts survive.

---

## D-002 - SQLite in WAL mode over PostgreSQL

**Date:** 2026-06-26  
**Decision:** Use SQLite with WAL mode for the task database.

**Alternatives:**
- PostgreSQL (more concurrent, remote-capable)
- Plain JSON/markdown files (no database)

**Reasoning:** SQLite in WAL mode is operationally simpler, requires no external process, supports concurrent reads with one writer, and is surprisingly strong for single-machine agent systems. No current need for remote access or high write concurrency. PostgreSQL is the clear upgrade path if scale demands it - the schema is portable.

---

## D-003 - File-first project state over database-only

**Date:** 2026-06-26  
**Decision:** Canonical per-project state (plan, tasks, knowledge, decisions, status, handoff) lives in markdown files. The database mirrors and accelerates operational coordination.

**Alternatives:**
- Database-only (all state in tasks.db)
- Files only (no database, everything in markdown)

**Reasoning:** Projects should survive runtime changes and be continuable from the folder alone by any compatible agent. A database that is the sole source of truth becomes a hidden dependency. Files are inspectable, diffable, searchable, and portable. The DB handles things files can't: atomic locking, fast indexed queries, session tracking, cost aggregation.

---

## D-004 - Pull-based task claiming over push dispatch

**Date:** 2026-06-26  
**Decision:** Workers poll tasks.db every 30 seconds and atomically claim pending tasks.

**Alternatives:**
- Push dispatch (orchestrator assigns tasks to specific workers)
- Event-driven (webhook/queue triggers worker)

**Reasoning:** Pull-based workers are simpler, more robust to disconnects, and naturally load-balance when multiple workers run. Push dispatch requires knowing which workers are alive and what they can handle, adding coordination complexity. The atomic UPDATE...RETURNING pattern prevents double-claims without external locking.

---

## D-005 - Separate verifier subagent for medium/high risk tasks

**Date:** 2026-06-26  
**Decision:** Verification of medium and high risk tasks must be done by a separate Claude Code invocation with a clean context - never by the executing agent self-reporting.

**Alternatives:**
- Self-certification (executor says task is done)
- Human-only verification

**Reasoning:** Executor agents systematically overestimate completeness. The executor's context contains all its own reasoning and is biased toward "done". A fresh verifier subagent looks only at artifacts and the verification plan - it has no attachment to the work. For low-risk tasks, self-report with evidence is acceptable as a lightweight option.

---

## D-006 - Dead-letter after 3 attempts

**Date:** 2026-06-26  
**Decision:** Tasks that fail 3 times move to `failed` status and require human review before re-queuing.

**Alternatives:**
- Unlimited retries
- Immediate escalation after 1 failure
- 5-attempt threshold

**Reasoning:** Blind retries are a common failure mode. 3 attempts is enough to distinguish transient errors from structural blockers. After 3 failures the human should see the evidence, classify the failure, and decide whether to modify the task, add missing context, or close it. Silent retry storms are worse than escalation.

---

## D-007 - No network calls in Phase 0

**Date:** 2026-06-26  
**Decision:** All scaffolding and Milestone 1 work is local-only. No HTTP requests, no cloud CLIs, no external API calls.

**Reasoning:** CLAUDE.md constraint. The harness must be safe to bootstrap on a fresh machine without external dependencies. This also forces the architecture to be genuinely local-first. Network access can be selectively unlocked by the human for specific tasks once the loop is proven.

---

## D-008 - 30-minute task timeout

**Date:** 2026-06-26  
**Decision:** Task execution has a hard timeout of 30 minutes. Expired tasks are unlocked and re-queued.

**Alternatives:**
- No timeout (hang forever)
- 10-minute timeout (too short for complex tasks)
- 60-minute timeout (too long to detect hangs)

**Reasoning:** Hanging agents waste budget and block the queue. 30 minutes covers most coding and analysis tasks while detecting pathological hangs quickly. Long-running tasks should be decomposed into smaller tasks that each fit the window.
