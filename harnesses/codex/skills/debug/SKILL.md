---
name: debug
description: Take one reported symptom — a stack trace, a failing CI job, an incident, a flaky test — reproduce it, find the root cause, fix it test-first, and open one PR. Starts from a known failure, not a sweep.
---

# Debug

Something is known to be broken. Reproduce it, isolate the root cause, fix it, and prove the fix with an acceptance test that failed first. One PR to `main` at the end.

Invocation: `/workcell:debug`
Prompting Reference: [`docs/models/gpt-5.6-sol/prompting.md`](../../runtime/docs/models/gpt-5.6-sol/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_agent` with native specialist routing from `agents/models.json`, hold human gates, run VCS and workspace operations using shell execution, and read gate evidence and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Reproduce a reported symptom on demand, isolate its root cause, seal an honest failing test, and verify a minimal fix in a single PR to `main`.
- **Constraints and Boundaries:** No reproduction, no fix. Never touch or weaken sealed tests during implementation. Never close a flaky failure by merely re-running until green.
- **Success Criteria:** Verified root cause evidence, specifier RED seal, builder GREEN verification, clean review passes, and merged or open PR with symptom and reproduction details.

## Ordered Gates

Execution proceeds through six strict, ordered gates:

1. **reproduce symptom**: Establish a reproducible symptom command and minimal reproduction scenario.
2. **isolate cause**: Isolate root cause with file:line evidence and minimal experimental hypotheses.
3. **RED seal**: Specifier encodes failure scenario as a failing acceptance test and seals it with `tdd-guard seal`.
4. **GREEN**: Builder implements the fix against the sealed test in an isolated workspace, confirming passing status without modifying the test.
5. **review**: Multi-lens review verifies the fix addresses the root cause without regressions.
6. **pull request**: Open single clean PR to `main` with symptom details, reproduction command, and covering test.

## Reproduction is the gate

**No reproduction, no fix.** A `debugger` that cannot make the failure happen on demand returns what it tried and what it could not establish, and the run stops there. Do not route an unreproduced report to a builder: a change to code nobody has seen fail is a guess that will be believed because it shipped.

If the report is too thin to reproduce, the missing information is the finding — go back to whoever reported it with the specific gap, rather than inventing a plausible scenario and fixing that instead.

## Procedure

1. **Diagnose.** Dispatch a `debugger` via `spawn_agent` with the reported failure. The debugger reproduces the symptom, isolates the minimal failing scenario, refutes hypotheses, and returns root cause `file:line` evidence and reproduction command. For flaky failures, it measures and reports the failure rate. It modifies no production code.
2. **Scope decision.** If the failure implies a wider class of defects, ask the human whether to widen before proceeding; do not turn a bug fix into an unapproved sweep.
3. **Fix test-first.** In single-PR mode, create integration branch `<planId>-integration` from `trunk()`. Create defect workspace via `workcell-ws add bug/<symptom-slug> --base <integration-base>` ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). Dispatch a `specifier` via `spawn_agent` against the reproduction command to write the acceptance test, verify honest RED, and seal it with `tdd-guard seal`.
4. **Implement.** Dispatch a `builder` via `spawn_agent` in the same workspace. The builder implements the fix, verifies GREEN with `tdd-guard verify --green-command`, performs self-reviews, and records evidence without touching sealed tests.
5. **Review and integrate.** Dispatch multi-lens `reviewer` agents via `spawn_agent`. Dispatch an `integrator` via `spawn_agent` over the wave on the integration branch. Merge intermediate PRs on green evidence and open the final PR to `main`.

## Boundaries

Never ship a fix whose test did not fail first — that is the whole gate, and "the test passes now" is not evidence when it also passed before. Never fix code the diagnosis did not implicate, and never clean up while you are in there: an unrelated change in a fix diff is how a revert takes something else with it. Never close a flaky-test report by re-running until it passes. If the root cause turns out to be a design problem rather than a defect, say so and route it to [`new-feature`](../new-feature/SKILL.md) or [`code-refactor`](../code-refactor/SKILL.md) instead of patching around it.

## Harness Limitations

API-only model controls (such as dynamic request-level reasoning effort or pro mode toggles) and API-only orchestration features are unsupported in Codex skill prompts; execution relies on native harness tooling and specialist dispatch.
