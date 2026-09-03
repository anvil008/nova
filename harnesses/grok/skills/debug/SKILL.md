---
name: debug
description: Take one reported symptom — a stack trace, a failing CI job, an incident, a flaky test — reproduce it, find the root cause, fix it test-first, and open one PR. Starts from a known failure, not a sweep.
---

# Debug

Something is known to be broken. Reproduce it, isolate the root cause, fix it, and prove the fix with an acceptance test that failed first. One PR to `main` at the end.

Invocation: `/workcell:debug`
Prompting Reference: [`docs/models/grok-4.6/prompting.md`](../../runtime/docs/models/grok-4.6/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_subagent` (running in foreground or with `background: true` tracked via `get_command_or_subagent_output`, or coordinated via `/workflow`), hold human gates, run VCS and workspace operations using shell execution, and read gate evidence and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

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

## Input and Output Contracts

Subagent dispatch uses native Grok `spawn_subagent` (with `background: true` for parallel tasks, polled via `get_command_or_subagent_output`) or multi-step `/workflow` routines. Each dispatch exchanges structured handoff payloads conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md).

- **Debugger Inputs and Outputs:**
  - **Inputs:** Reported failure symptom, reproduction context, and environment parameters.
  - **Outputs:** Minimal reproduction command, root cause `file:line` citation, and refutation logs without editing code.
- **Specifier Inputs and Outputs:**
  - **Inputs:** Root cause diagnosis, reproduction command, defect workspace path, and integration base.
  - **Outputs:** Failing acceptance test suite verified honest RED and sealed with `tdd-guard seal`.
- **Builder Inputs and Outputs:**
  - **Inputs:** Defect workspace, sealed test manifest, and fix goal.
  - **Outputs:** Verified passing fix, `tdd-guard verify` GREEN evidence, two diff-review passes, and open pull request.
- **Reviewer Inputs and Outputs:**
  - **Inputs:** Defect fix diff and original symptom scenario.
  - **Outputs:** Multi-lens assurance findings and regression checks.

## Procedure

1. **Diagnose.** Dispatch a `debugger` via `spawn_subagent` with the reported failure. The debugger reproduces the symptom, isolates the minimal failing scenario, refutes hypotheses, and returns root cause `file:line` evidence and reproduction command. For flaky failures, it measures and reports the failure rate. It modifies no production code.
2. **Scope decision.** If the failure implies a wider class of defects, ask the human whether to widen before proceeding; do not turn a bug fix into an unapproved sweep.
3. **Fix test-first.** In single-PR mode, create integration branch `<planId>-integration` from `trunk()`. Create defect workspace via `workcell-ws add bug/<symptom-slug> --base <integration-base>` ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). Dispatch a `specifier` via `spawn_subagent` against the reproduction command to write the acceptance test, verify honest RED, and seal it with `tdd-guard seal`.
4. **Implement.** Dispatch a `builder` via `spawn_subagent` in the same workspace. The builder implements the fix, verifies GREEN with `tdd-guard verify --green-command`, performs self-reviews, and records evidence without touching sealed tests.
5. **Review and integrate.** Dispatch multi-lens `reviewer` agents via `spawn_subagent`. Dispatch an `integrator` via `spawn_subagent` over the wave on the integration branch. Merge intermediate PRs on green evidence and open the final PR to `main`.

## Harness Limitations

Skill frontmatter fields `allowed-tools`, `model`, `effort`, `license`, and `compatibility` are unsupported for capability enforcement or routing under Grok Build; execution relies on native CLI flags (`--tools`, `--disallowed-tools`), agent definitions, capability modes, and specialist dispatch. API-only model controls and programmatic tool calling are unsupported in skill prompts.
