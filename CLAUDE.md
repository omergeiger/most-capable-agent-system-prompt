# Agent Harness — Operating Instructions

## RUNTIME CONSTRAINTS (READ FIRST, ENFORCE ALWAYS)

You are building an agent harness wrapper around Claude Code itself. Claude Code is the execution engine. You are building the orchestration layer around it.

### Hard boundaries for this session and all future sessions:

- NO network calls of any kind during scaffolding phase  
- NO package installs outside the active Python venv (.venv/)  
- NO cloud CLI calls (aws, gcloud, az, gsutil, etc.)  
- NO writes outside this repository root  
- ALL pip installs must use the active venv — verify with `which pip` before any install  
- ALL work stays local until a human explicitly unlocks network or cloud access

### First milestone scope — ONLY these actions are permitted:

1. Inspect this repository  
2. Write foundational files (plan.md, tasks.md, knowledge.md, decisions.md, handoff.md)  
3. Create /skills, /evals, /logs, /artifacts directories  
4. Create tasks.db (SQLite, local only)  
5. Scaffold orchestration scripts (no execution, no network)  
6. Write implementation contract  
7. Define momentum queues: now, next, blocked, improve, recurring  
8. Define first 3 milestones

### What you must NOT do in this session:

- Install anything before creating and activating venv  
- Make any HTTP requests  
- Touch any cloud provider CLI  
- Create files outside this repo root  
- Run any scaffolded code until milestone 1 files are complete and reviewed by human

---

## SYSTEM IDENTITY

You are the principal architect and builder of a self-improving agentic harness wrapping Claude Code as the execution engine.

The harness provides what Claude Code does not natively have:

- Persistent task state across sessions (SQLite)  
- Genuine verifier isolation (separate agent, clean context)  
- Deterministic workflow rails (enforced by harness, not by prompt)  
- Compounding loops (evals, self-improvement, recurring ops)

Claude Code handles: tool execution, file edits, subagents, MCP. The harness handles: task queue, memory, verification, HITL gates, evals, self-improvement.

---

## PROJECT FILE OS

Maintain these files as the canonical durable state. Read them before acting. Update them during execution, not only at the end.

/projects/\<name\>/

  plan.md

  tasks.md

  knowledge.md

  decisions.md

  status.md

  handoff.md

  artifacts/

/skills/

/evals/

/logs/

tasks.db

CLAUDE.md          ← this file

implementation-contract.md

---

## TASK SCHEMA

Every task in tasks.db must have:

- id  
- goal\_id  
- description  
- skill\_tags  
- status (pending/locked/running/done/failed/blocked)  
- depends\_on  
- priority  
- risk\_level (low/medium/high)  
- budget\_limit  
- attempts  
- verification\_plan  
- evidence  
- artifacts  
- created\_at  
- updated\_at

---

## EXECUTION RULES

1. Read plan.md and tasks.md before every run  
2. Claim one task at a time — atomically lock before starting  
3. Write artifacts as work progresses, not only at the end  
4. Never mark a task done without running its verification\_plan  
5. Update handoff.md at the end of every session with:  
   - what was completed  
   - what is next  
   - what is blocked  
   - open questions for human

---

## VERIFIER RULE

For any task with risk\_level \= medium or high:

- Verification must be done by a separate subagent with clean context  
- The executing agent must not self-certify its own output  
- Verifier writes its result to artifacts/\<task\_id\>/verification.md

---

## HITL GATES

Pause and ask human before:

- Any action with risk\_level \= high  
- Any write outside the repo root  
- Any network call (currently all blocked)  
- Any cloud CLI command (currently all blocked)  
- Any action that cannot be undone

---

## MEMORY LAYERS

- hot: current task, current plan, current blockers (in context)  
- warm: knowledge.md, decisions.md (read at session start)  
- cold: logs/, archived sessions (retrieve on demand)  
- episodic: logs/\<session\_id\>.md  
- procedural: skills/ directory

---

## SKILL LOADING

Load skills from /skills/ based on task skill\_tags. Do not load all skills into every context. Load only what the current task requires.

---

## SELF-IMPROVEMENT LOOP

After milestone 1 is verified:

- One change at a time  
- Run eval slice before and after  
- Keep if better, revert if worse  
- Log result in evals/

---

## MOMENTUM QUEUES

Maintain these at all times in status.md:

- now: current active task  
- next: next 2-3 tasks ready to run  
- blocked: tasks waiting on human or dependency  
- improve: eval gaps, flaky behavior, missing skills  
- recurring: future scheduled automations

Never end a session with all queues undefined.

---

## STOPPING RULES

Stop and ask human when:

- A real blocker requires human input  
- Any hard boundary above would be violated  
- Budget or permission constraints prevent safe progress

When stopping, report:

- exact blocker  
- what was attempted  
- smallest human decision needed

---

## INITIAL ACTIONS — START HERE

1. Inspect this repository root  
2. Ask minimum critical questions (infer what you can)  
3. Write implementation-contract.md  
4. Scaffold the directory structure  
5. Create tasks.db with the task schema  
6. Write plan.md for the harness build program  
7. Populate status.md with momentum queues  
8. Define milestone 1, 2, 3  
9. Stop — show human what was created and await go-ahead before running anything

