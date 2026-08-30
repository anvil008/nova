---
name: code-analysis
description: Hunt real defects across a codebase end-to-end — reproduce each as a failing test, fix it, and open one PR to main. Correctness only; never refactors for taste or adds features.
---

# Code analysis

Find what is actually broken, prove it, and fix it. Every defect that ships in the PR arrives with a test that failed before the fix and passes after — no "hardening", no speculative defensiveness, no cleanup that happened to be nearby. One PR to `main` at the end.

You are the orchestrator: you scope the hunt, dispatch the agents, hold the gates, and merge ([ADR 0007](../../docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)). You read the file list and the evidence, never the code.

## What counts as a finding

A defect needs a **concrete failure scenario**: inputs or state that produce a wrong result, a crash, corruption, a leak, or a security hole. "This could be clearer", "this lacks a null check nothing can reach", and "this is not how I would write it" are not defects — the first belongs to [`code-refactor`](../code-refactor/SKILL.md) and the rest belong nowhere.

Rank by what actually goes wrong, not by how alarming it sounds. A `critical` is data loss, corruption, or an exploitable hole; a `high` is a wrong answer users act on; below that, say so honestly rather than inflating to be heard.

## Procedure

1. **Baseline.** Dispatch an `integrator` to run the full verification untouched. A suite that is already red tells you which failures are pre-existing — that is the map, not a blocker.
2. **Hunt.** Dispatch `code-reviewer` agents in parallel, one lens each, over the area under analysis: `correctness` and `tests` always, plus `security`, `performance`, `api-contract`, `backend`, `integrations`, or `frontend` as the code warrants. Each returns structured findings with a failure scenario and never edits.
3. **Verify adversarially before believing anything.** Dispatch a fresh reviewer that did not originate the candidate to try to *refute* each one against the code. A finding that survives a genuine refutation attempt is real; one that cannot be reproduced from its own failure scenario is dropped, and dropping it is a result worth reporting. This is the same contract [`code-review`](../code-review/SKILL.md) uses, and the refuted ones belong in the report.
4. **Plan.** Dispatch the `planner` with the surviving findings. One issue per defect, ordered by severity, with disjoint `ownershipHint`s. Each issue's `acceptanceTests` are written from the failure scenario: the oracle is the specific wrong behaviour, so the test fails today for the right reason. Human approval before any GitHub write.
5. **Execute** exactly as [`build`](../build/SKILL.md) does, both phases intact. This is where the TDD gate earns its keep: the `test-author` turns each failure scenario into a genuinely failing test and seals it, then the `builder` fixes the defect against a Definition of Done it did not write and cannot edit. A "fix" that never had a red test is not a verified fix.
6. **Integrate and open one PR.** Dispatch an `integrator` over the wave, confirm every sealed test now passes and nothing that was green went red, and open a single PR to `main` listing each defect, its failure scenario, and the test that now covers it. Merge on the evidence.

## Boundaries

Never refactor for taste, rename for consistency, or reformat while you are in there — an unrelated change in a bug-fix diff is how a fix gets reverted along with something else six months later; route it to [`code-refactor`](../code-refactor/SKILL.md). Never fix a defect you could not reproduce as a failing test: if the test cannot be written, the finding is not understood yet, and shipping a change to code you do not understand is how the next defect gets made. Never claim a clean bill of health from a partial sweep — say which areas and lenses were actually covered.
