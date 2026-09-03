---
name: code-analysis
description: Hunt real defects across a codebase end-to-end — reproduce each as a failing test, fix it, and open one PR to main. Correctness only; never refactors for taste or adds features.
---

# Code Analysis

Find what is actually broken, prove it, and fix it. Every defect that ships in the PR arrives with a test that failed before the fix and passes after — no speculative defensiveness, no refactoring for taste, and no nearby cleanups. One PR to `main` at the end.

Invocation: `/workcell:code-analysis`
Prompting Reference: [`docs/models/gpt-5.6-sol/prompting.md`](../../runtime/docs/models/gpt-5.6-sol/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_agent` with native specialist routing from `agents/models.json`, hold human gates, run workspace and VCS operations using shell commands, and read gate output and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Hunt down substantiated defects, reproduce them with honest failing tests, implement minimal verified fixes, and deliver a single clean PR to `main`.
- **Constraints and Boundaries:** Correctness only; never refactor for taste or add features. Never implement a fix for an issue that lacks an honest failing test sealed by a specifier.
- **Success Criteria:** Every fixed defect has an honest red test sealed before implementation and green evidence after, validated through independent adversarial review.

## Ordered Gates

Execution proceeds through five strict, ordered gates:

1. **reproduction**: Baseline the tree and reproduce candidate defects with concrete failure scenarios.
2. **RED seal**: A `specifier` agent encodes each reproducible failure as an honest failing test and establishes a `tdd-guard seal`.
3. **GREEN**: A `builder` agent implements the minimal fix against the sealed test in an isolated workspace, confirming passing status without modifying the test.
4. **review**: Independent review passes verify the fix introduces no regressions or unapproved changes.
5. **pull request**: A single, clean pull request to `main` is opened incorporating all verified fixes with their command evidence.

## What counts as a finding

A defect needs a **concrete failure scenario**: inputs or state that produce a wrong result, a crash, corruption, a leak, or a security hole. "This could be clearer", "this lacks a null check nothing can reach", and "this is not how I would write it" are not defects — the first belongs to [`code-refactor`](../code-refactor/SKILL.md) and the rest belong nowhere.

Rank by what actually goes wrong, not by how alarming it sounds. A `critical` is data loss, corruption, or an exploitable hole; a `high` is a wrong answer users act on; below that, say so honestly rather than inflating to be heard.

## Procedure

1. **Baseline.** Dispatch an `integrator` via `spawn_agent` with a brief conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md) carrying `mode: baseline`: run documented verification on the untouched tree at `base`, return command-linked evidence, and perform no merge. A pre-existing failing suite maps existing defects rather than blocking progress.
2. **Hunt.** Dispatch `reviewer` agents in parallel via `spawn_agent`, one lens each over the target area: `correctness` and `tests` always, plus `security`, `performance`, `api-contract`, `backend`, `integrations`, or `frontend` as code warrants. Reviewers return structured findings with concrete failure scenarios and never edit code.
3. **Adversarial verification.** Dispatch a fresh `reviewer` via `spawn_agent` that did not originate the finding to attempt refutation against the code. Only findings that survive genuine refutation advance; refuted findings are documented in the report.
4. **Plan.** Dispatch a `planner` via `spawn_agent` with surviving findings. One issue per defect, ordered by severity, with disjoint `ownershipHint` globs and acceptance tests derived from the reproduction scenarios. Stop for human approval before creating GitHub tracking.
5. **Execute.** Run [`build`](../build/SKILL.md) in single-PR mode. For each issue, a `specifier` seals an honest failing test via `tdd-guard seal`, and a `builder` implements the fix in an isolated workspace without modifying the test.
6. **Integrate and open PR.** Dispatch an `integrator` via `spawn_agent` to confirm all sealed tests pass and no regressions occurred. Open one final PR to `main` referencing closed issues and including all reproduction and test evidence.

## Boundaries

Never refactor for taste, rename for consistency, or reformat while you are in there — an unrelated change in a bug-fix diff is how a fix gets reverted along with something else six months later; route it to [`code-refactor`](../code-refactor/SKILL.md). Never fix a defect you could not reproduce as a failing test: if the test cannot be written, the finding is not understood yet, and shipping a change to code you do not understand is how the next defect gets made. Never claim a clean bill of health from a partial sweep — say which areas and lenses were actually covered.

## Harness Limitations

API-only model controls (such as dynamic request-level reasoning effort or pro mode toggles) and API-only orchestration features are unsupported in Codex skill prompts; execution relies on native harness tooling and specialist dispatch.
