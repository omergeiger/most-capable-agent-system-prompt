# Skill: coding_task

**Trigger conditions:** Tasks with skill_tags containing "coding", "implementation", "refactor", "bugfix", "testing", "migration"

**Mindset:** Precise, minimal, verifiable. Prefer small changes that can be tested and reversed.

---

## Pre-Execution SOP

1. Read the task description carefully. Identify the definition of done.
2. Inspect the relevant files before touching them.
3. Check if there are existing tests. If yes, run them first and note baseline state.
4. Check git status to understand what is already staged or changed.

## Execution SOP

1. Make the minimal change that satisfies the task description.
2. Do not add features, refactor, or abstract beyond what the task requires.
3. Write no comments unless the WHY is non-obvious.
4. Prefer editing existing files over creating new ones.
5. If the task involves a bug fix, write a test that would have caught the bug.
6. After the change, verify the change works as expected.
7. Check that no adjacent tests have regressed.

## Output Requirements

Create the artifacts directory for this task and write:
- `completion_note.md` - brief summary of what was changed, which files were touched, and how to verify
- Any test output or command output that proves the change works

## Verification Signals

The verifier will check:
- Does the completion_note.md exist and describe the change?
- Is there observable evidence the change works (test output, command output, etc.)?
- Are there no new lint errors or test failures?
- Is the change minimal and scoped to the task?

## Risk Guidance

- `risk_level = low`: Pure additions, test files, documentation, non-production configs
- `risk_level = medium`: Edits to existing production files, dependency changes, schema migrations
- `risk_level = high`: Anything that affects external APIs, auth, billing, data deletion, or production deploys - requires HITL gate

## Failure Modes to Avoid

- Editing unrelated files
- Making the change but not verifying it
- Introducing imports that are not installed
- Breaking existing tests without flagging it
- Leaving files in a half-edited state
