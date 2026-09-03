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

## Procedure

1. **Sweep and plan.** Dispatch a `debugger` or `researcher` agent via `invoke_subagent` to formulate a concrete failure scenario for each potential bug and try to refute false alarms. Where an issue is merely cosmetic or architectural cleanup without a bug, route it to [`code-refactor`](../code-refactor/SKILL.md). Dispatch a `debugger` or `researcher` agent via `invoke_subagent` to sweep target subsystems for demonstrable bugs (e.g. edge-case panics, race conditions, leakages, or unhandled errors). Dispatch the `planner` agent to organize confirmed defects into dependency-ordered issues with disjoint `ownershipHint` globs and explicit `acceptanceTests`.
2. **Approve.** Stop and present the plan folio for explicit human approval before creating issues or branches.
3. **Execute in single-PR mode.** Run [`build`](../build/SKILL.md) in single-PR mode on the integration branch:
   - For each issue, dispatch a `specifier` via `invoke_subagent` to author reproduction tests and establish a RED seal (`tdd-guard seal --test-command <cmd>`).
   - Dispatch a `builder` via `invoke_subagent` with `mode: standard` in an isolated workspace (`workcell-ws add bug/<issue-key> --base <integration-base>`) to implement the fix against the sealed tests without modifying them.
   - Run multi-lens review via `reviewer` agents before merging to the integration branch.
4. **Integrate.** Dispatch an `integrator` via `invoke_subagent` over each wave to verify combined correctness.
5. **Open final PR.** Open a single PR to `main` linking all closed issues.

## Boundaries

Never claim a defect without an automated failing test. If an anomaly cannot be reliably reproduced, document it and stop rather than guessing a fix. Never introduce drive-by stylistic edits or unsolicited architectural shifts.

Based on the requirements and constraints above, execute the code-analysis workflow systematically.
