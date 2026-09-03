---
name: code-refactor
description: Simplify a codebase end-to-end without changing what it does — consolidate duplicated modules, deepen shallow ones, delete dead paths — then open one PR to main. Behaviour-preserving only; never fixes bugs or changes features.
---

# Code Refactor

Make the code simpler while it keeps doing exactly what it did. Combine modules that were split for no reason, deepen ones whose interface is wider than their substance, collapse indirection that earns nothing, and delete dead code. One PR to `main` at the end.

Invocation: `/workcell:code-refactor`
Prompting Reference: [`docs/models/gpt-5.6-sol/prompting.md`](../../runtime/docs/models/gpt-5.6-sol/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_agent` with native specialist routing from `agents/models.json`, hold human gates, run workspace and VCS operations using shell commands, and read gate output and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Simplify code architecture and eliminate redundancy while preserving external and observable behaviour identically.
- **Constraints and Boundaries:** Never touch, modify, add, or delete test files. Full test suite must remain identically green before and after every edit. No bug fixes, no new features, and no dependency upgrades.
- **Success Criteria:** Baseline green seal verified, refactor implemented without touching test files, and clean single PR to `main` summarizing simplifications.

## Ordered Gates

Execution proceeds through five strict, ordered gates:

1. **green baseline**: Prove the full test suite is green on untouched tree before making any changes.
2. **behaviour-preserving change**: Implement simplifications without altering existing behaviour or modifying test files.
3. **GREEN**: Verify all existing tests remain green under a baseline seal.
4. **review**: Multi-lens review verifies behaviour preservation and confirms no test edits occurred.
5. **pull request**: Open single PR to `main` with verified simplifications and identical test outcomes.

## Procedure

1. **Baseline.** Dispatch an `integrator` via `spawn_agent` with a brief conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md) carrying `mode: baseline`: verify the untouched tree at `base`, return command-linked evidence, and perform no merge. If the suite is not green before starting, stop immediately.
2. **Survey.** Dispatch `researcher` agents via `spawn_agent`, one per area, guided by [`references/design-heuristics.md`](references/design-heuristics.md). Candidates include duplicated logic, modules failing deletion tests, single-caller abstractions, and dead exports. Researchers return structured evidence with `file:line` references, never edits.
3. **Plan.** Dispatch a `planner` via `spawn_agent` with survey findings and behaviour-preservation constraints. Each issue represents one independently landable simplification with disjoint `ownershipHint` globs. `acceptanceTests` specify existing tests that must remain green. Stop for human approval before creating GitHub tracking.
4. **Execute.** Run [`build`](../build/SKILL.md) in single-PR mode omitting the specifier phase. For each issue, create a workspace with `workcell-ws add refactor/<issue-key> --base <integration-base>` ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). Dispatch an `integrator` via `spawn_agent` with `mode: baseline` to establish a `kind: baseline` seal and hand off with `tdd-guard handoff --to builder`. Dispatch the `builder` via `spawn_agent` with `mode: refactor`. The builder must never edit a test file.
5. **Review and PR.** Dispatch multi-lens `reviewer` agents via `spawn_agent` to confirm behaviour preservation and verify no test files were touched. Merge intermediate PRs into the integration branch upon green evidence and open the final PR to `main`.

## Harness Limitations

API-only model controls (such as dynamic request-level reasoning effort or pro mode toggles) and API-only orchestration features are unsupported in Codex skill prompts; execution relies on native harness tooling and specialist dispatch.
