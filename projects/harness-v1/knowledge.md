# Knowledge Base - Harness v1

**Updated:** 2026-06-26

This file captures stable facts, architecture knowledge, and distilled insights about the harness build program. It is read at session start and updated as new facts are learned.

---

## Runtime Profile

- **Runtime:** Claude Code CLI on macOS 25.5.0 (darwin)
- **Model:** claude-sonnet-4-6
- **Python:** 3.13 in .venv/ at repo root
- **Shell:** zsh
- **Git:** initialized, branch main
- **Database:** SQLite 3 in WAL mode (tasks.db at repo root)
- **Network:** blocked in Phase 0

## Architecture Decisions

See `decisions.md` for the full decision log. Key summary:

1. **Harness-wrapper mode** - wrap Claude Code, don't rebuild its core
2. **SQLite-first** - WAL mode, single-machine, upgrade to Postgres only if scale demands
3. **File-first project state** - markdown files are canonical, DB mirrors/accelerates
4. **Pull-based task claiming** - worker polls, atomically locks; never push-only
5. **Separate verifier** - executor and verifier are always different subprocess invocations

## Task Schema Fields

Every task in tasks.db must have (at minimum):
- `id` - unique UUID
- `goal_id` - parent goal
- `description` - what to do
- `skill_tags` - JSON array, used to load the right skill profiles
- `status` - pending / locked / running / done / failed / blocked
- `depends_on` - JSON array of task IDs that must be done first
- `priority` - higher = claimed first (1-10)
- `risk_level` - low / medium / high (high = HITL gate before execution)
- `verification_plan` - explicit description of how to verify completion
- `evidence` - JSON object of verification results
- `attempts` - auto-incremented on each claim; dead-letter at 3

## Task Status Lifecycle

```
pending -> locked (claimed by worker)
locked  -> running (executor subagent started)
running -> done (verified pass)
running -> pending (verifier fail, attempts < 3)
running -> failed (attempts >= 3 or unrecoverable error)
pending -> blocked (depends_on task is blocked or failed)
```

## File Layout

```
/
├── tasks.db                      <- live operational state
├── implementation-contract.md    <- build program contract
├── CLAUDE.md                     <- harness operating instructions
├── projects/
│   └── harness-v1/
│       ├── plan.md              <- 3-milestone build plan
│       ├── tasks.md             <- Milestone 1 task list
│       ├── knowledge.md         <- this file
│       ├── decisions.md         <- decision log
│       ├── status.md            <- live momentum queues
│       ├── handoff.md           <- session handoff
│       └── artifacts/           <- task artifacts for this project
├── skills/
│   ├── coding_task.md           <- SOP for software engineering tasks
│   └── verification.md          <- SOP for verifier subagent
├── evals/
│   ├── task_claim_atomicity.py  <- proves no double-claim
│   └── smoke_test.md            <- 9-step Milestone 1 checklist
├── logs/                        <- episodic session logs
├── artifacts/                   <- task artifacts (by task ID)
└── scripts/
    ├── init_db.py               <- DB schema setup
    ├── create_goal.py           <- goal intake + task decomposition
    ├── worker.py                <- main worker polling loop
    ├── claim_task.py            <- CLI tool to claim/inspect tasks
    └── update_status.py         <- updates status.md from DB
```

## What the Harness Does NOT Do

- Execute any code on its own during scaffolding phase
- Make network calls
- Install packages outside .venv/
- Touch cloud CLIs
- Self-modify approval or security policy

## Milestone 1 Smoke Test - Learnings (2026-06-26)

Closed-loop run completed successfully on 2026-06-26. Key observations:

- `claude --print` (long form) is the correct non-interactive CLI flag. `-p` is the short alias. Both work.
- Artifact directories use full UUID paths (`artifacts/<full-uuid>/`), not the 8-char prefix shown in claim_task list output. Scripts reference full IDs correctly.
- SQLite WAL atomicity holds under 10-thread concurrency: exactly 1 of 10 concurrent UPDATE...RETURNING claims succeeds.
- Verifier subagent independently re-ran assertions (subprocess execution) rather than trusting executor's self-report - the isolation is working as designed.
- `create_goal.py` Claude decomposition: for a simple 2-part goal, Claude returned 3 tasks (implement, test, run) which is the right granularity.
- Episodic log appends correctly; each entry captures goal_id, task description, verification outcome.

## Known Gaps (to close in Milestone 2+)

- No skill profile loader yet (static skill files, manual loading)
- No eval harness runner (eval files exist, no automated runner)
- No budget tracking update after task runs
- No proactive monitoring scan
- No recurring automation cron
- No dashboard beyond status.md markdown
