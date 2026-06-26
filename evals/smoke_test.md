# Smoke Test - Milestone 1 Closed-Loop Checklist

**Purpose:** Verify that the 9 closed-loop steps all work end to end on a real task.  
**Run after:** Human approves scripts (M1-013)  
**Run via:** Human or verifier subagent walks through each step

---

## Pre-conditions

- [ ] tasks.db exists with 5 tables (WAL mode)
- [ ] `claude` CLI is on PATH (`which claude` returns a path)
- [ ] .venv exists and Python 3.13 is available (`.venv/bin/python --version`)
- [ ] All 4 scripts exist in scripts/
- [ ] skills/ has at least 2 skill files

---

## Step 1: Goal Intake

**Command:**
```bash
.venv/bin/python scripts/create_goal.py "Write a Python function that reverses a string and add a test for it"
```

**Expected result:**
- Claude Code returns 3-5 tasks as JSON lines
- Tasks inserted into tasks.db
- Output shows goal ID and task count

**Check:**
```bash
.venv/bin/python scripts/claim_task.py list
```
- [ ] Shows pending tasks with descriptions matching the goal

---

## Step 2: Task Graph Visible

**Check:**
```bash
.venv/bin/python scripts/claim_task.py list --status pending
```
- [ ] Tasks show correct priority order
- [ ] depends_on relationships are set correctly (if any)

---

## Step 3: Worker Claims Task

**Command:**
```bash
.venv/bin/python scripts/worker.py --once
```

**Check:**
```bash
.venv/bin/python scripts/claim_task.py list --status locked
```
- [ ] Exactly one task is now 'locked' (not two - atomicity check)
- [ ] `locked_at` is set

---

## Step 4: Claude Code Executes

After worker.py runs:

**Check:**
```bash
ls logs/exec_*.md
```
- [ ] Execution log exists for the task

**Check:**
```bash
ls artifacts/
```
- [ ] Artifact directory exists for the task ID

---

## Step 5: Verifier Runs (Separate Subagent)

After worker.py completes:

**Check:**
```bash
cat artifacts/TASK_ID/verification.md
```
- [ ] verification.md exists
- [ ] Contains either `Status: PASS` or `Status: FAIL`
- [ ] Contains a `Reason:` line

**Confirm isolation:**
- [ ] Verifier output is in a separate file from executor output
- [ ] Verifier does not repeat executor reasoning verbatim (clean context)

---

## Step 6: Evidence Recorded

**Check:**
```bash
.venv/bin/python scripts/claim_task.py show TASK_ID
```
- [ ] `evidence` field contains JSON with `verified`, `verification_reason`, `log_path`
- [ ] `artifacts` field contains path to artifact directory
- [ ] `status` is 'done' (or 'pending' if verifier failed with reason)

---

## Step 7: Memory Updated

**Check:**
```bash
cat logs/episodic.md
```
- [ ] Entry exists for the completed task
- [ ] Contains task description and verification outcome

---

## Step 8: Status Visible to Human

**Command:**
```bash
.venv/bin/python scripts/update_status.py
```

**Check:**
```bash
cat projects/harness-v1/status.md
```
- [ ] Task board shows correct counts (at least 1 done)
- [ ] Recently completed section shows the task
- [ ] File was auto-updated (not hand-edited)

---

## Step 9: One Learning Artifact

After the run, the human or worker should produce one of:
- [ ] An update to knowledge.md capturing a new fact from the run
- [ ] An improvement to a skill file based on what the executor did or failed to do
- [ ] A new eval case based on the task that was run

At minimum: add an entry to knowledge.md noting what was learned.

---

## Pass Criteria

All 9 steps checked. The human can:
1. See what the system ran (status.md)
2. Find the evidence (artifacts/ + logs/)
3. Confirm verification was separate (verification.md + log structure)
4. Read memory (logs/episodic.md)
5. Identify the next task to run (status.md NOW/NEXT queues)

---

## Common Failure Modes

| Symptom | Likely cause | Fix |
|---|---|---|
| create_goal.py returns no tasks | Claude prompt format issue | Check DECOMPOSITION_PROMPT_TEMPLATE output |
| Worker claims task but task stays 'locked' | Exception in execute_task before status update | Check logs/exec_*.md for error |
| verification.md missing | Verifier subprocess failed silently | Check worker output for stderr |
| Episodic log not created | LOGS_DIR missing or permission issue | Run `mkdir -p logs` |
| status.md not updated | update_status.py not called after worker | Call manually or wire to post-task hook |
