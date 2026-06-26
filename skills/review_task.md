# Skill: review_task

**Trigger conditions:** Tasks with skill_tags containing "review", "audit", "inspect", "check", "lint"

**Mindset:** Skeptical but fair. Look for real problems, not style preferences. Never rubber-stamp.

---

## Pre-Execution SOP

1. Read the thing being reviewed fully before writing any feedback.
2. Identify the review criteria: correctness, security, performance, style, completeness.
3. Check whether there is an existing standard to measure against (a spec, a prior version, a checklist).

## Execution SOP

1. Go through the subject systematically (file by file, section by section).
2. For each finding: classify as blocking (must fix), advisory (should fix), or nitpick (optional).
3. Be specific: quote the line or section, explain why it is a problem, suggest a fix.
4. Do not flag things that are correct just because they are unfamiliar to you.
5. Do not pass a review just because you cannot find obvious problems - say what you checked.

## Output Requirements

- Write a `review_report.md` in the artifacts directory.
- Structure: Summary verdict (PASS/PASS WITH NOTES/FAIL), Blocking Issues, Advisory Issues, Nitpicks.
- Write a `completion_note.md` with the verdict and top finding.

## Risk Guidance

- low: reviewing documentation, non-production scripts
- medium: reviewing production code changes
- high: reviewing security-sensitive code, auth, billing, or data migrations
