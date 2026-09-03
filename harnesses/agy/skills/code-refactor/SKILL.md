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

## Procedure

1. **Plan refactor scope.** Dispatch the `planner` agent via `invoke_subagent` to map out structural refactoring milestones, identifying disjoint `ownershipHint` boundaries and existing test suites that cover each target area.
2. **Approve.** Present the refactoring plan for explicit human approval before touching code.
3. **Establish baseline and execute.** For each issue:
   - Create an isolated workspace (`workcell-ws add refactor/<issue-key> --base <integration-base>`).
   - Dispatch an `integrator` via `invoke_subagent` with `mode: baseline` to run tests and establish a `kind: baseline` seal via `tdd-guard seal --baseline`.
   - Dispatch a `builder` via `invoke_subagent` with `mode: refactor` to perform the structural changes against the sealed baseline without touching test files.
   - Run multi-lens review via `reviewer` agents checking for behavioral fidelity.
4. **Integrate waves.** Dispatch an `integrator` via `invoke_subagent` over each wave to verify combined correctness.
5. **Open final PR.** Open a single PR to `main` linking all closed refactor issues.

## Boundaries

Never use a refactor to smuggle in behavioral fixes, API modifications, or speculative redesigns. If a bug is uncovered during refactoring, record it for a separate [`debug`](../debug/SKILL.md) or [`code-analysis`](../code-analysis/SKILL.md) workflow and preserve the current behaviour.

Based on the requirements and constraints above, execute the code-refactor workflow systematically.
