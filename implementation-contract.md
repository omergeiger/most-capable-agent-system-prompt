# Implementation Contract

**Date:** 2026-06-26  
**Runtime:** Claude Code CLI (harness-wrapper mode)  
**Model:** claude-sonnet-4-6  
**Operator:** Omer Geiger

---

## Mission

Build a durable, self-improving agentic operating system that wraps Claude Code as its execution engine. The harness provides what Claude Code lacks natively:

- Persistent task state across sessions (SQLite + markdown files)
- Genuine verifier isolation (separate subagent, clean context)
- Deterministic workflow rails (enforced by harness code, not by prompt)
- Compounding self-improvement loops (evals, skills, recurring ops)
- Human-inspectable control plane (files, status.md, handoff.md)

Claude Code handles: tool execution, file edits, subagents, MCP.  
The harness handles: task queue, memory, verification, HITL gates, evals, self-improvement.

---

## Runtime Profile

| Capability | Status | Notes |
|---|---|---|
| Repo read/write | Yes | Full access |
| Shell access | Yes | zsh on macOS 25.5.0 |
| Filesystem search | Yes | find, grep, ripgrep |
| File editing | Yes | Claude Code native |
| Git access | Yes | git CLI |
| Network access | Blocked | Phase 0 constraint |
| Package installs | Venv only | .venv/ at repo root |
| Local database | Yes | SQLite WAL (tasks.db) |
| Browser control | Deferred | Milestone 3+ |
| Screenshot/vision | Deferred | Milestone 3+ |
| Desktop automation | Deferred | Milestone 4+ |
| Sub-agent support | Yes | Claude Code subagents |
| Long-running background | Partial | Shell scripts, no daemon yet |
| Cron/scheduled | Deferred | Milestone 3 |
| Persistent storage | Yes | SQLite + markdown |
| UI/dashboard | File-based only | status.md in Milestone 1 |
| Secret management | Deferred | Milestone 2+ |
| Multi-machine | Deferred | Milestone 4+ |

**Implementation mode:** Harness-wrapper. Claude Code is the execution engine; this repo is the orchestration layer.

---

## First Milestone Definition

Prove the closed loop end to end on one real task:

1. Accept a goal via `scripts/create_goal.py` or markdown file
2. Decompose into tasks (stored in tasks.db)
3. Worker (`scripts/worker.py`) claims one task atomically
4. Claude Code executes the task in isolated context
5. Separate verifier subagent checks the result
6. Evidence recorded to `artifacts/<task_id>/`
7. Memory updated (knowledge.md + episodic log in logs/)
8. Human-visible status in `projects/harness-v1/status.md`
9. One learning artifact or skill update produced

**Milestone 1 is NOT complete until all 9 steps run on a real task.**

---

## Non-Goals for v1

- Web UI or dashboard (markdown only)
- Multi-machine coordination
- Browser or desktop automation
- Cloud deployments
- External API integrations
- Science or finance domain harnesses
- Trust score automatic promotion (manual only)
- Multi-tenant or multi-user scenarios
- Model routing layer (one model for now)

---

## Constraints

- No network calls during scaffolding phase
- No pip installs outside .venv/
- No cloud CLI commands (aws, gcloud, az, etc.)
- No writes outside this repository root
- No execution of scaffolded code until milestone 1 files reviewed by human
- tasks.db in WAL mode only, no remote DB
- No secrets stored in repo files

---

## Safety Posture

- HITL gate before any task with `risk_level = high`
- Verifier must be a separate subagent with clean context
- All destructive actions require explicit approval before execution
- Locked tasks timeout after 30 minutes (unlock + re-queue)
- Dead-letter after 3 failed attempts (status = failed, human review required)
- No self-modification of approval policy, security rules, or trust thresholds without human approval

---

## Proof-of-Progress Metrics

- [ ] tasks.db created with correct schema (5 tables, WAL mode)
- [ ] Directory structure scaffolded (`skills/`, `evals/`, `logs/`, `artifacts/`, `projects/`)
- [ ] implementation-contract.md written and legible
- [ ] Milestone 1-3 plan defined in projects/harness-v1/plan.md
- [ ] status.md populated with all 5 momentum queues
- [ ] One real goal decomposed into 3+ tasks
- [ ] Worker claims tasks atomically (verified by atomicity test)
- [ ] Verifier runs as separate subagent with clean context
- [ ] Evidence file written for completed task
- [ ] knowledge.md updated after task completion
- [ ] Episodic log created in logs/
- [ ] handoff.md up to date at session end

---

## Verification Strategy

| Level | Method |
|---|---|
| Unit | `evals/task_claim_atomicity.py` - proves no double-claim |
| Schema | `evals/smoke_test.md` - walks all 9 Milestone 1 steps |
| Integration | One real coding task run end-to-end |
| Human review | Human reads handoff.md and confirms state is legible |
| Regression | Re-run atomicity test after any harness change |
