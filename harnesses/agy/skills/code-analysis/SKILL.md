---
name: code-analysis
description: Hunt real defects across a codebase end-to-end — reproduce each as a failing test, fix it, and open one PR to main. Correctness only; never refactors for taste or adds features.
---

# Code Analysis

Find real defects, reproduce each as a failing test, fix them, and open one PR to `main`. This is the sweeper: it searches across the codebase for bugs rather than starting from a reported symptom.

Invocation: `/workcell:code-analysis`
Prompting Reference: [`docs/models/gemini-3.7-flash/prompting.md`](../../runtime/docs/models/gemini-3.7-flash/prompting.md)

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents via Antigravity's `invoke_subagent`, hold the human gates, run `git` / `jj` / `gh` and scripts via `run_command` for branch, merge, and issue-state operations, and read gate output and handoff records using the [`anvil.agent-handoff/v1`](../../runtime/handoff.md) schema. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator coordinates the defect search, verifies reproduction seals, and opens the consolidated PR. Per the Gemini 3.7 Flash guide, place critical constraints first, demand explicit evidence before state transitions, and enforce honest failure modes.

## Critical Constraints

- **Goal:** Identify, reproduce, seal, and repair genuine defects with zero behavioural regressions, verified through multi-lens review and merged via a single PR to `main`.
- **Constraints:** Never fix without a reproduction test. Every defect must have a sealed failing test from a specifier before a builder touches the code. Never refactor for style or add new features; this skill is for correctness only.
- **Success Criteria:** Verified RED seal for each reproduction, passing GREEN suite after builder repair, passing review passes, and clean single PR to `main`.

## Ordered Gates

Execution proceeds through five strict, ordered gates:

1. **reproduction**: Hunt for real defects and author failing tests reproducing each defect.
2. **RED seal**: Establish a `tdd-guard seal` proving reproduction tests fail honestly.
3. **GREEN**: Builder implements fixes in an isolated workspace until all sealed tests pass.
4. **review**: Multi-lens review verifies defect resolution without side effects.
5. **pull request**: Open single consolidated PR to `main` closing all resolved defect issues.

## What counts as a finding

A defect needs a **concrete failure scenario**: inputs or state that produce a wrong result, a crash, corruption, a leak, or a security hole. "This could be clearer", "this lacks a null check nothing can reach", and "this is not how I would write it" are not defects — the first belongs to [`code-refactor`](../code-refactor/SKILL.md) and the rest belong nowhere.

Rank by what actually goes wrong, not by how alarming it sounds. A `critical` is data loss, corruption, or an exploitable hole; a `high` is a wrong answer users act on; below that, say so honestly rather than inflating to be heard.

## Procedure

1. **Baseline.** Dispatch an `integrator` via `invoke_subagent` with a brief conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md) and carrying `mode: baseline`: run the documented verification on the untouched tree at `base`, return command-linked evidence, and perform no merge. A suite that is already red tells you which failures are pre-existing — that is the map, not a blocker.
2. **Hunt.** Dispatch `reviewer` agents in parallel, one lens each, over the area under analysis: `correctness` and `tests` always, plus `security`, `performance`, `api-contract`, `backend`, `integrations`, or `frontend` as the code warrants. Each returns structured findings with a failure scenario and never edits. Where an issue is merely cosmetic or architectural cleanup without a bug, route it to [`code-refactor`](../code-refactor/SKILL.md).
3. **Verify adversarially before believing anything.** Dispatch a fresh `reviewer` via `invoke_subagent` that did not originate the candidate to try to refute each one against the code. A finding that survives a genuine refutation attempt is real; one that cannot be reproduced from its own failure scenario is dropped, and dropping it is a result worth reporting. This is the same contract [`code-review`](../code-review/SKILL.md) uses, and the refuted ones belong in the report.
4. **Plan.** Dispatch the `planner` via `invoke_subagent` with the surviving findings. One issue per defect, ordered by severity, with disjoint `ownershipHint`s. Each issue's `acceptanceTests` are written from the failure scenario: the oracle is the specific wrong behaviour, so the test fails today for the right reason. Stop for explicit human approval before any GitHub write.
5. **Execute in single-PR mode.** Run [`build`](../build/SKILL.md) in **single-PR mode**, both phases intact:
   - For each issue, dispatch a `specifier` via `invoke_subagent` to author reproduction tests and establish a RED seal (`tdd-guard seal --test-command <cmd>`).
   - Dispatch a `builder` via `invoke_subagent` with `mode: standard` in an isolated workspace (`workcell-ws add bug/<issue-key> --base <integration-base>`) to implement the fix against the sealed tests without modifying them.
   - Run multi-lens review via `reviewer` agents before merging to the integration branch.
6. **Integrate and open final PR.** Dispatch an `integrator` via `invoke_subagent` over each wave, confirm every sealed test now passes and nothing that was green went red, and merge intermediate PRs to the integration branch only on the evidence. The final PR from that branch to `main` lists each defect, its failure scenario, and the test that now covers it, and repeats every per-issue `Closes #<n>` line.

## Boundaries

Never refactor for taste, rename for consistency, or reformat while you are in there — an unrelated change in a bug-fix diff is how a fix gets reverted along with something else six months later; route it to [`code-refactor`](../code-refactor/SKILL.md). Never fix a defect you could not reproduce as a failing test: if the test cannot be written, the finding is not understood yet, and shipping a change to code you do not understand is how the next defect gets made. Never claim a clean bill of health from a partial sweep — say which areas and lenses were actually covered.

Based on the requirements and constraints above, execute the code-analysis workflow systematically.
