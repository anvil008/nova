---
name: code-review
description: Run a multi-lens, adversarially verified review of a pull request, diff, or change-set before merge.
---

# Code review

Review one pull request, diff, or integrated change-set before merge. The primary agent running this skill owns the consolidated report and verdict.

## Lens selection and fan-out

Inspect the change, then select lenses from its actual risks:

- correctness and tests are always selected;
- security applies when trust boundaries, authentication or authorization, dependencies, secrets, or input handling change;
- performance applies to hot paths, loops, allocations, concurrency, or materially larger data flow;
- api-contract applies when a public surface, wire format, schema, CLI, or compatibility promise changes.

The fan-out count equals the applicable lenses, never a fixed N. Spawn one read-only `code-reviewer` per selected lens in parallel. Give each reviewer the same change-set and exactly one lens. Reviewers return structured findings and never edit.

## Merge and adversarial verification

1. Collect the per-lens JSON files and deduplicate by `(file, line, claim)`. `skills/code-review/scripts/merge_findings.py --dedupe-only` chooses the representative by highest severity, highest confidence, then lexicographically smallest `(lens, failureScenario)`. This full tie-break is independent of parallel collection order; the helper then ranks candidates deterministically.
2. Run an independent adversarial verification of every surviving candidate. Use a fresh read-only reviewer that did not originate the candidate, assign its lens and exact claim, and require a skeptic pass that tries to refute it against the code and concrete failure scenario.
3. Record one verification per candidate with `substantiated`, `refutationAttempt`, and `evidence`. Run the helper again with `--verification`. DROP every finding that the independent pass cannot substantiate; missing, duplicate, or extra verification records are errors.

Only verified findings reach the report. The helper ranks `critical`, `high`, `medium`, `low`, then `nit`; `critical` or `high` yields `block`, remaining findings yield `approve-with-nits`, and no findings yields `approve`.

## Report

Return the verified findings ranked by severity and the verdict: `block` / `approve-with-nits` / `approve`. Include the selected lenses and verification evidence. The primary agent is the sole synthesis and completion authority; reviewer or verifier output is evidence, not the verdict.

## Offline demonstration

These commands read local fixtures only and have no GitHub or subagent side effects:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B skills/code-review/scripts/merge_findings.py --dedupe-only skills/code-review/examples/correctness.json skills/code-review/examples/tests.json skills/code-review/examples/security.json
PYTHONDONTWRITEBYTECODE=1 python3 -B skills/code-review/scripts/merge_findings.py --verification skills/code-review/examples/verification.json skills/code-review/examples/correctness.json skills/code-review/examples/tests.json skills/code-review/examples/security.json
```
