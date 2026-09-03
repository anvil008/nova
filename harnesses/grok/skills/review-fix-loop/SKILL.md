---
name: review-fix-loop
description: Repeatedly review a change-set and have the builder fix what the review finds, on a dedicated loop-branch, bounded to a fixed number of passes. Drive it with the harness `/loop`; this skill is the body of one iteration and owns the stop conditions.
---

# Review-Fix Loop

Review, fix, re-review — on `loop-branch`, up to ten passes, stopping early when there is nothing left to fix or when fixing stops working.

Invocation: `/workcell:review-fix-loop`
Prompting Reference: [`docs/models/grok-4.6/prompting.md`](../../runtime/docs/models/grok-4.6/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_subagent` (running in foreground or with `background: true` tracked via `get_command_or_subagent_output`, or coordinated via `/workflow`), hold human gates, run VCS and shell operations, and read gate evidence and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Iterate through review, fix, and verification cycles on `loop-branch` until findings at or above `--min-severity` are eliminated (`converged`) or honest termination is reached (`stalled` or `exhausted`).
- **Constraints and Boundaries:** Never run on `main`, never merge `loop-branch`, never push without explicit user request, and never alter `--max-iterations` to bypass a stall.
- **Success Criteria:** Verified fix commit for each productive iteration, clean termination via `loop_state.py`, and lessons consolidated into the project wiki.

## Ordered Gates

Execution proceeds through four strict, ordered gates:

1. **review**: Run multi-lens review over current changes on `loop-branch` and adversarially verify all candidate findings.
2. **fix**: Dispatch a builder to resolve substantiated findings at or above minimum severity.
3. **verify**: Execute the project verification suite to ensure fixes are passing and cause no regressions.
4. **bounded stop**: Evaluate loop convergence state via `loop_state.py` to stop upon convergence, stalling, or pass exhaustion.

## Input and Output Contracts

Subagent dispatch uses native Grok `spawn_subagent` (with `background: true` for parallel tasks, polled via `get_command_or_subagent_output`) or multi-step `/workflow` routines. Each dispatch exchanges structured handoff payloads conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md).

- **Loop Reviewer Inputs and Outputs:**
  - **Inputs:** `loop-branch` diff against base, target files, and review lenses.
  - **Outputs:** Deduplicated, substantiated findings JSON with file, line, and severity rankings.
- **Builder Fix Inputs and Outputs:**
  - **Inputs:** Active findings list at or above minimum severity, `loop-branch` workspace, and verification command.
  - **Outputs:** Verified code changes addressing findings, clean test execution logs, and commit record.
- **Loop State Evaluator Inputs and Outputs:**
  - **Inputs:** Previous loop iteration state JSON and newly generated review findings.
  - **Outputs:** Updated loop state JSON and termination directive (`continue`, `converged`, `stalled`, or `exhausted`).

## Procedure

1. **Initialize state.** Run once to create the loop branch and state file:

   ```bash
   jj bookmark create loop-branch -r @
   python3 skills/review-fix-loop/scripts/loop_state.py init --branch loop-branch --max-iterations 10 --min-severity high
   ```

2. **Review.** Execute [`code-review`](../code-review/SKILL.md) over changes between `loop-branch` and its base: dispatch `reviewer` agents via `spawn_subagent`, verify candidates adversarially, and merge findings with `merge_findings.py --verification`.
3. **Fix.** If substantiated findings at or above `--min-severity` exist, dispatch a `builder` via `spawn_subagent` to implement targeted fixes against the findings.
4. **Verify.** Run the project test suite to verify fixes and ensure no regressions occurred.
5. **Bounded stop evaluation.** Advance loop state:

   ```bash
   python3 skills/review-fix-loop/scripts/loop_state.py advance --findings review.json
   ```

   Stop when state indicates `converged` (no remaining findings at or above threshold), `stalled` (no progress across iterations), or `exhausted` (max iterations reached). Report the ending status, pass count, and findings that remain.

## Stopping Well

The bound is the point. Ten passes of an agent editing code against its own reviewer is a lot of unsupervised change, so the loop is designed to end early and honestly rather than to reach ten:

- `converged` is a real result — hand over the branch, together with the findings below the threshold that the last merged review still lists.
- `stalled` usually means the finding needs a human decision, or the builder cannot reach it from the findings alone. Report the repeated finding set verbatim; do not retry it.
- `exhausted` means ten passes did not clear the findings. That is a signal about the change, not a reason to re-run the loop.

In all three cases the work sits on `loop-branch` and nothing has merged. Opening a PR, filing the remaining findings as issues (`reconcile_findings.py`), or discarding the branch is the human's call.

## Harness Limitations

Skill frontmatter fields `allowed-tools`, `model`, `effort`, `license`, and `compatibility` are unsupported for capability enforcement or routing under Grok Build; execution relies on native CLI flags (`--tools`, `--disallowed-tools`), agent definitions, capability modes, and specialist dispatch. API-only model controls and programmatic tool calling are unsupported in skill prompts.
