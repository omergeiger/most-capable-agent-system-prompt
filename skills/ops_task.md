# Skill: ops_task

## Domain

Operations tasks: filesystem audits, process health checks, log analysis, script execution,
environment validation, and recurring maintenance procedures.

## When to Load

Load this skill when a task's `skill_tags` includes `ops`, `maintenance`, `audit`,
`health-check`, or `environment`.

## Mindset

- Observe before acting. Read current state before making any change.
- Prefer read-only verification first; confirm the problem exists before fixing it.
- Every ops action must be reversible or have a documented rollback.
- Write findings to artifacts/ as you go, not only at the end.
- If a check reveals unexpected state, pause and document it before proceeding.

## Scope Boundaries

ops_task must NOT:

- Run schema migrations or modify database structure
- Install packages or modify dependencies (no `pip install`, `npm install`, etc.)
- Perform git operations (no commits, pushes, branch changes, or merges)

## Standard Procedure

1. **Scope check** - restate in one sentence what system component this task touches.
2. **Read current state** - list files, read configs, check process status, tail logs.
3. **Identify the condition** - what does "healthy" look like? What does "broken" look like?
4. **Take action (if needed)** - smallest change that moves toward healthy state.
5. **Verify the fix** - re-check the same indicators you checked in step 2.
6. **Write artifact** - `artifacts/<task_id>/ops_report.md` with: what was found, what was done, final state.

## Verification Checklist

Before marking an ops task done, confirm:

- [ ] The target system/file/process is in the expected healthy state
- [ ] No unintended side-effects on neighboring systems
- [ ] ops_report.md written to artifacts/
- [ ] Any changed files are noted in evidence

## Common Patterns

### Filesystem audit

```
find <dir> -name "*.log" -mtime +7 | head -20  # find stale logs
du -sh <dir>/*                                  # check disk usage
ls -la <dir>                                    # check permissions
```

### Process health

```
pgrep -fl <process_name>         # check if running
ps aux | grep <name>             # detailed view
```

### Environment validation

```
which python3 && python3 --version
cat .venv/pyvenv.cfg             # confirm venv Python version
pip list --format=freeze         # installed packages
```

### Log analysis

Look for: ERROR, CRITICAL, FATAL, Traceback, killed, OOM, timeout.
Capture the 5 lines before and after each match for context.

## Output Format

Always produce `artifacts/<task_id>/ops_report.md` with:

```markdown
# Ops Report - <task description>
**Date:** <ISO timestamp>
**System:** <what was checked>

## Initial State
<what was found>

## Actions Taken
<numbered list, or "none required">

## Final State
<confirmed healthy / issue persists / escalated>

## Evidence
<key file paths, commands run, outputs>
```
