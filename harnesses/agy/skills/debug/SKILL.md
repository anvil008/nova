---
name: debug
description: Take one reported symptom — a stack trace, a failing CI job, an incident, a flaky test — reproduce it, find the root cause, fix it test-first, and open one PR. Starts from a known failure, not a sweep.
---

# Debug

Isolate and fix a specific reported symptom test-first. Unlike [`code-analysis`](../code-analysis/SKILL.md), this workflow starts from a known failure rather than sweeping for defects.

Invocation: `/workcell:debug`
Prompting Reference: [`docs/models/gemini-3.7-flash/prompting.md`](../../runtime/docs/models/gemini-3.7-flash/prompting.md)

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents via Antigravity's `invoke_subagent`, hold the human gates, run `git` / `jj` / `gh` and scripts via `run_command` for branch, merge, and issue-state operations, and read gate output and handoff records using the [`anvil.agent-handoff/v1`](../../runtime/handoff.md) schema. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator coordinates the reproduction, root cause isolation, specifier sealing, and builder fix. Per the Gemini 3.7 Flash guide, place critical constraints first, demand empirical reproduction before fixes, and enforce strict test sealing.

## No reproduction, no fix

No reproduction, no fix: without an automated reproduction, any repair is speculative. If a defect cannot be reliably reproduced, document the findings, stop, and route to [`code-analysis`](../code-analysis/SKILL.md) or request more context.

## Critical Constraints

- **Goal:** Reproduce the reported defect reliably, isolate its root cause, seal a failing test, and deliver a verified minimal fix via a single PR to `main`.
- **Constraints:** Never guess or attempt fixes before the failure is reliably reproduced. Never dispatch a builder without a specifier RED seal. Never modify tests during the builder phase.
- **Success Criteria:** Deterministic reproduction, verified RED seal, passing GREEN verification, passing review passes, and clean single PR to `main`.

## Ordered Gates

Execution proceeds through six strict, ordered gates:

1. **reproduce symptom**: Reproduce reported failure, incident, or flaky test reliably.
2. **isolate cause**: Debugger isolates root cause through experiment without speculative fixing.
3. **RED seal**: Specifier authors failing regression test and seals it via `tdd-guard seal`.
4. **GREEN**: Builder repairs defect in isolated workspace until sealed tests pass.
5. **review**: Reviewer verifies root cause resolution without side effects.
6. **pull request**: Open single PR to `main` closing the reported defect issue.

## Procedure

1. **Reproduce.** Dispatch a `debugger` agent via `invoke_subagent` to establish an empirical reproduction script or failing invocation matching the reported symptom.
2. **Isolate root cause.** The debugger formulates hypotheses, designs targeted experiments, and isolates the precise line, condition, or mechanism causing the defect without implementing a fix.
3. **Seal RED test.** Dispatch a `specifier` agent via `invoke_subagent` to translate the reproduction into a regression test within the project test suite and seal it using `tdd-guard seal --test-command <cmd>`.
4. **Implement fix.** In an isolated workspace (`workcell-ws add bug/<issue-key> --base main`), dispatch a `builder` agent via `invoke_subagent` with `mode: standard` to fix the defect against the sealed test without touching test files.
5. **Review.** Dispatch `reviewer` agents across relevant lenses (correctness, tests, security) to ensure the repair is minimal and causes no regressions.
6. **Open PR.** Open a single PR to `main` referencing the incident/issue and verifying all checks pass.

## Boundaries

Never attempt speculative fixes before isolating the true root cause. If the symptom cannot be reproduced, halt and solicit additional context from the reporter rather than fixing imagined problems.

Based on the requirements and constraints above, execute the debug workflow systematically.
