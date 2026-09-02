---
name: code-analysis
description: Hunt real defects across a codebase end-to-end — reproduce each as a failing test, fix it, and open one PR to main. Correctness only; never refactors for taste or adds features.
---

<!-- generated harness-owned procedure: Antigravity -->

# Code analysis

Find what is actually broken, prove it, and fix it. Every defect that ships in the PR arrives with a test that failed before the fix and passes after — no "hardening", no speculative defensiveness, no cleanup that happened to be nearby. One PR to `main` at the end.

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents, hold the human gates, run `git` / `jj` / `gh` for branch, merge, and issue-state operations, and read gate output and handoff records. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator scopes the hunt and advances only findings that survive adversarial reproduction.

## What counts as a finding

A defect needs a **concrete failure scenario**: inputs or state that produce a wrong result, a crash, corruption, a leak, or a security hole. "This could be clearer", "this lacks a null check nothing can reach", and "this is not how I would write it" are not defects — the first belongs to [`code-refactor`](../code-refactor/SKILL.md) and the rest belong nowhere.

Rank by what actually goes wrong, not by how alarming it sounds. A `critical` is data loss, corruption, or an exploitable hole; a `high` is a wrong answer users act on; below that, say so honestly rather than inflating to be heard.

## Procedure

1. **Baseline.** Dispatch an `integrator` with a brief conforming to [`agents/handoff.md`](../../runtime/handoff.md) and carrying `mode: baseline`: run the documented verification on the untouched tree at `base`, return command-linked evidence, and perform no merge. A suite that is already red tells you which failures are pre-existing — that is the map, not a blocker.
2. **Hunt.** Dispatch `reviewer` agents in parallel, one lens each, over the area under analysis: `correctness` and `tests` always, plus `security`, `performance`, `api-contract`, `backend`, `integrations`, or `frontend` as the code warrants. Each returns structured findings with a failure scenario and never edits.
3. **Verify adversarially before believing anything.** Dispatch a fresh reviewer that did not originate the candidate to try to *refute* each one against the code. A finding that survives a genuine refutation attempt is real; one that cannot be reproduced from its own failure scenario is dropped, and dropping it is a result worth reporting. This is the same contract [`code-review`](../code-review/SKILL.md) uses, and the refuted ones belong in the report.
4. **Plan.** Dispatch the `planner` with the surviving findings. One issue per defect, ordered by severity, with disjoint `ownershipHint`s. Each issue's `acceptanceTests` are written from the failure scenario: the oracle is the specific wrong behaviour, so the test fails today for the right reason. Human approval before any GitHub write.
5. **Execute** [`build`](../build/SKILL.md) in **single-PR mode**, both phases intact. This is where the TDD gate earns its keep: the `specifier` turns each failure scenario into a genuinely failing test and seals it, then the `builder` fixes the defect against a Definition of Done it did not write and cannot edit. A "fix" that never had a red test is not a verified fix.
6. **Integrate and open the final PR.** Dispatch an `integrator` over each wave, confirm every sealed test now passes and nothing that was green went red, and merge intermediate PRs to the integration branch only on the evidence. The final PR from that branch to `main` lists each defect, its failure scenario, and the test that now covers it, and repeats every per-issue `Closes #<n>` line.

## Boundaries

Never refactor for taste, rename for consistency, or reformat while you are in there — an unrelated change in a bug-fix diff is how a fix gets reverted along with something else six months later; route it to [`code-refactor`](../code-refactor/SKILL.md). Never fix a defect you could not reproduce as a failing test: if the test cannot be written, the finding is not understood yet, and shipping a change to code you do not understand is how the next defect gets made. Never claim a clean bill of health from a partial sweep — say which areas and lenses were actually covered.
