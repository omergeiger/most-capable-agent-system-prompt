# Skill: planning_task

**Trigger conditions:** Tasks with skill_tags containing "planning", "decompose", "design", "architecture", "roadmap"

**Mindset:** Think in dependencies, risks, and reversibility. Prefer small verifiable steps over big uncertain ones.

---

## Pre-Execution SOP

1. State the goal clearly: what does done look like?
2. Identify constraints: time, people, tools, unknowns.
3. Ask: what is the riskiest assumption here?

## Execution SOP

1. Decompose the goal into the smallest independently verifiable steps.
2. For each step: write a description, risk_level (low/medium/high), and verification_plan.
3. Identify dependencies between steps - draw the dependency graph (text is fine).
4. Flag any steps that require human approval before proceeding.
5. Estimate relative effort (small/medium/large) for each step.

## Output Requirements

- Write a `plan.md` in the artifacts directory.
- Structure: Goal, Steps (with risk and verification), Dependency Graph, Human Gates, Open Questions.
- Write a `completion_note.md` summarizing the plan and the riskiest assumption.

## Risk Guidance

- low: planning a self-contained technical task with clear reversibility
- medium: planning work that touches production systems or multiple people
- high: planning work with irreversible steps or significant unknowns
