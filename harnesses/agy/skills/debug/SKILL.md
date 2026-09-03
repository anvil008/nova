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

## Critical Constraints

- **Goal:** Reproduce the reported defect reliably, isolate its root cause, seal a failing test, and deliver a verified minimal fix via a single PR to `main`.
- **Constraints:** Never guess or attempt fixes before the failure is reliably reproduced. Never dispatch a builder without a specifier RED seal. Never modify tests during the builder phase.
- **Success Criteria:** Deterministic reproduction, verified RED seal, passing GREEN verification, passing review passes, and clean single PR to `main`.

## Reproduction is the gate

**No reproduction, no fix.** If an issue cannot be reproduced, do not let an agent guess at a fix and call it done. Guessing at bugs makes worse bugs, and a fix you cannot prove is a change nobody can trust.

If the report is too thin to reproduce, the missing information is the finding: go back to whoever reported it with the specific gap, rather than inventing a plausible scenario and fixing that instead.

## Ordered Gates

Execution proceeds through six strict, ordered gates:

1. **reproduce symptom**: Reproduce reported failure, incident, or flaky test reliably.
2. **isolate cause**: Debugger isolates root cause through experiment without speculative fixing.
3. **RED seal**: Specifier authors failing regression test and seals it via `tdd-guard seal`.
4. **GREEN**: Builder repairs defect in isolated workspace until sealed tests pass.
5. **review**: Reviewer verifies root cause resolution without side effects.
6. **pull request**: Open single PR to `main` closing the reported defect issue.

## Procedure

1. **Diagnose.** Dispatch a `debugger` agent via `invoke_subagent` with the report. It reproduces the symptom, shrinks it to a minimal case, forms and refutes hypotheses by experiment, bisects history when the code used to work, and returns the root cause with `file:line` evidence, the reproduction command, and a proposed fix location. It fixes nothing and leaves no instrumentation behind.

   For a **flaky** failure it returns a measured rate ("17/200 under `-race`") rather than a verdict, because a single green run proves nothing about nondeterminism.

2. **Decide the scope.** The diagnosis usually names one defect; sometimes it names a class. Fix the reported defect. If the root cause implies siblings, list them and ask the human whether to widen — do not quietly turn a bug fix into a sweep.
3. **Plan** only if the fix spans issues. A single-defect fix needs no folio: take the diagnosis straight to step 4. For a class of defects, dispatch the `planner` with the diagnosis and get approval as usual.
4. **Fix, test-first.** For the single-defect path, use a stable lowercase symptom slug as the single-PR mode's `<planId>`; before dispatching the `specifier`, the orchestrator creates `<planId>-integration` from `trunk()` and uses it as the brief's `base`. Then send both agents a dispatch brief conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md) with `issue: null`. A fix branch is a defect branch, so the brief's `branch` is `bug/<symptom-slug>` ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). Its `brief` carries the debugger's reproduction command and minimal case as the single acceptance test, with `name`, `kind`, and `oracle`; its `ownership` is the debugger's proposed fix location. Dispatch a `specifier` via `invoke_subagent` against that acceptance test — it is already a failing case, which is exactly what a seal wants — then a `builder` to fix it against a sealed test it cannot edit. The builder's intermediate PR body names the symptom and the reproduction instead of `Closes #<n>`.

   For a flaky fix, the acceptance test must run enough repetitions to distinguish "fixed" from "got lucky", and the debugger's measured rate sets that count.

5. **Review** with the usual lens fan-out, weighted to `correctness` and to the area the defect lives in.
6. **Integrate and open final PR.** Run [`build`](../build/SKILL.md) in **single-PR mode**, dispatch the `integrator` via `invoke_subagent` over each wave, and merge intermediate PRs to the integration branch only on the evidence. The final PR from that branch to `main` names the symptom, reproduction, root cause, introducing commit if there was one, and covering test. For the single-defect `issue: null` path it names the symptom and the reproduction instead of `Closes #<n>`; for planned defects it repeats every per-issue `Closes #<n>` line.

## Boundaries

Never ship a fix whose test did not fail first — that is the whole gate, and "the test passes now" is not evidence when it also passed before. Never fix code the diagnosis did not implicate, and never clean up while you are in there: an unrelated change in a fix diff is how a revert takes something else with it. Never close a flaky-test report by re-running until it passes. If the root cause turns out to be a design problem rather than a defect, say so and route it to [`new-feature`](../new-feature/SKILL.md) or [`code-refactor`](../code-refactor/SKILL.md) instead of patching around it.

Based on the requirements and constraints above, execute the debug workflow systematically.
