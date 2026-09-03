---
name: code-refactor
description: Simplify a codebase end-to-end without changing what it does — consolidate duplicated modules, deepen shallow ones, delete dead paths — then open one PR to main. Behaviour-preserving only; never fixes bugs or changes features.
---

# Code Refactor

Simplify architecture, consolidate duplicate code, and remove dead paths without altering external behaviour. Behaviour-preserving only; never fixes bugs or changes features.

Invocation: `/workcell:code-refactor`
Prompting Reference: [`docs/models/gemini-3.7-flash/prompting.md`](../../runtime/docs/models/gemini-3.7-flash/prompting.md)

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents via Antigravity's `invoke_subagent`, hold the human gates, run `git` / `jj` / `gh` and scripts via `run_command` for branch, merge, and issue-state operations, and read gate output and handoff records using the [`anvil.agent-handoff/v1`](../../runtime/handoff.md) schema. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator manages the refactoring lifecycle under a green baseline seal. Per the Gemini 3.7 Flash guide, place critical constraints first, demand explicit verification evidence, and avoid unprompted functional changes.

## Critical Constraints

- **Goal:** Simplify code structure and reduce technical debt while guaranteeing strictly byte-identical observable behaviour across all test suites.
- **Constraints:** Never modify existing tests. Never fix bugs or introduce new features under a refactor workflow. All existing tests must remain identically green under a baseline seal.
- **Success Criteria:** Verified green baseline seal prior to editing, clean builder implementation with unchanged test pass status, passing review passes, and single PR to `main`.

## Ordered Gates

Execution proceeds through five strict, ordered gates:

1. **green baseline**: Establish green baseline seal on existing test suite before any changes.
2. **behaviour-preserving change**: Implement structural simplifications in an isolated workspace.
3. **GREEN**: Verify all tests remain green without modifying tests.
4. **review**: Multi-lens review verifies behaviour preservation and clean refactoring.
5. **pull request**: Open single PR to `main` consolidating approved refactoring changes.

## Baseline Seal Gate

Ordinary feature work records a `kind: red` seal after its command fails. A refactor records a `kind: baseline` seal after its command passes. Both kinds digest and protect the same test paths, bind the same command argv, and require post-seal GREEN plus a real diff review. The gate is the same `tdd-guard` state machine with the RED requirement replaced by a GREEN one, so the Stop hook and `status --json` work unchanged. Do not dispatch a `specifier`, and do not let a builder invent a failing test.

## Procedure

1. **Baseline.** Dispatch an `integrator` via `invoke_subagent` with a brief conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md) and carrying `mode: baseline`: run the documented verification on the untouched tree at `base`, return command-linked evidence, and perform no merge. If it is not green before you start, stop: you cannot tell a refactor regression from a pre-existing failure, and you will spend the whole run guessing.
2. **Survey.** Scope before scanning: take the area the human named, or read commit history (`git log --oneline`) for churn hot spots. Dispatch `researcher` agents, one per area, briefed on [`references/design-heuristics.md`](references/design-heuristics.md). Candidates: duplicated logic, modules failing the deletion test, abstractions with a single caller, dead exports, cyclic dependencies, and interfaces wider than their use. Each candidate returns evidence with `file:line` and a strength label (`strong` / `worth-exploring` / `speculative`). They return evidence, never edits.
3. **Plan.** Dispatch the `planner` via `invoke_subagent` with the survey and this skill's invariant. Each issue is one independently landable simplification with a disjoint `ownershipHint`, and carries its candidate's strength label so the human sees it at approval. `acceptanceTests` for a refactor issue name existing tests that must keep passing. Stop for explicit human approval before any GitHub write.
4. **Execute.** Run [`build`](../build/SKILL.md) in **single-PR mode**, with the specifier phase omitted. For each issue, the orchestrator creates its jj workspace and branch on the integration base:

   ```bash
   workcell-ws add refactor/<issue-key> --base <integration-base>
   # = jj workspace add --name refactor-<issue-key> ../<repo>-refactor-<issue-key> -r <integration-base>
   #   + jj bookmark create refactor/<issue-key> -r @   (git worktree add -b <branch> in a git-only repo)
   ```

   Every branch here takes the `refactor/` type, and the directory beneath it writes that slash as a dash ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). Creating a workspace is a branch operation, so it stays inside the orchestrator's boundary. Next dispatch an `integrator` via `invoke_subagent` with a brief conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md) and carrying `mode: baseline`, that `workspace`, the issue's existing tests as `sealedTests`, and the exact suite argv as `baselineCommand`. It runs the green command in the workspace, records a `kind: baseline` seal, runs `tdd-guard handoff --to builder`, and returns green evidence and seal state.

   Only after that handoff dispatch the `builder` via `invoke_subagent` in the same workspace with `mode: refactor`. It never touches a test file; it runs the bound command through `tdd-guard verify --green-command`, retains GREEN evidence postdating the baseline seal, and records `tdd-guard diff-review record`. Reject any change-set whose diff touches a test file, and send it back.

5. **Review.** The usual lens fan-out, weighted to this work: `correctness` (behaviour preserved), `api-contract` (no public surface moved without cause), plus `backend`, `frontend`, or `integrations` where the change lands. A reviewer that finds a behaviour difference is reporting a failed refactor, not a nit.
6. **Integrate and open final PR.** Dispatch an `integrator` via `invoke_subagent` over each wave, compare its run against the step-1 baseline — same tests, same outcomes — and merge intermediate PRs to the integration branch only on the evidence. The final PR from that branch to `main` summarizes what got simpler and what stayed identical, and repeats every per-issue `Closes #<n>` line.

## Boundaries

Never fix a bug, add a feature, change a public contract without saying so plainly in the PR, or upgrade a dependency. Never accept "the tests needed updating" as part of a refactor: that sentence means the behaviour changed, and it belongs in a different skill with a different gate. If simplification is impossible without changing behaviour, stop and return the trade-off to the human rather than quietly taking it.

Based on the requirements and constraints above, execute the code-refactor workflow systematically.
