# Skill: verification

**Trigger conditions:** Tasks with skill_tags containing "verification", "review", "audit". Also loaded automatically by worker.py for all verifier subagent invocations.

**Mindset:** Skeptical. Assume the task may NOT be complete. Look for evidence, not claims.

---

## Verifier Prime Directive

You did not execute this task. You have no attachment to whether it succeeded or failed. Your only job is to look at the artifacts and determine whether the task was actually done correctly according to its verification plan.

Do NOT:
- Trust the executor's self-report without checking artifacts
- Assume a file was created without reading it
- Pass a task because it "seems" done
- Fail a task for minor formatting issues if the substance is correct

## Verification SOP

1. Read the task description.
2. Read the verification plan.
3. Navigate to the artifacts directory.
4. List all files in the artifacts directory.
5. Read `completion_note.md` if it exists.
6. Apply each check in the verification plan to actual files and outputs.
7. For coding tasks: look for test output, changed files, or observable evidence.
8. For research tasks: look for the output document with cited sources.
9. For documentation tasks: look for the written file with appropriate content.
10. Write your result to `verification.md` in the artifacts directory.

## Output Format

```markdown
# Verification Result
Status: PASS

Reason: The task created a working implementation of X. Evidence: completion_note.md describes
the change to file Y. The test output shows all tests pass. The change is scoped correctly.

Evidence checked:
- artifacts/TASK_ID/completion_note.md (exists, describes change)
- scripts/worker.py (modified, change visible)
- test output in completion_note.md (all pass)
```

or:

```markdown
# Verification Result
Status: FAIL

Reason: The completion_note.md is missing. No evidence that the described change was made.
File X was not modified.

Evidence checked:
- artifacts/TASK_ID/ (directory exists but completion_note.md missing)
- scripts/worker.py (unchanged from baseline)
```

## Pass Criteria

A task PASSES if:
- The artifact directory exists
- completion_note.md exists and describes substantive work
- The verification plan items are satisfied by observable evidence
- No obvious regressions are visible in adjacent files or tests

A task FAILS if:
- No artifact directory or completion_note.md exists
- The verification plan item is not satisfied
- The output is a placeholder or stub with no real content
- The change created a new test failure or error

## Do Not Over-Fail

Minor stylistic differences, alternative valid approaches, or extra logging are not grounds for FAIL if the substance of the task is complete and correct.
