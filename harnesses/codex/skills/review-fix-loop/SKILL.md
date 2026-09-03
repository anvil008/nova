---
name: review-fix-loop
description: Repeatedly review a change-set and have the builder fix what the review finds, on a dedicated loop-branch, bounded to a fixed number of passes. Drive it with the harness `/loop`; this skill is the body of one iteration and owns the stop conditions.
---

# Review-Fix Loop

Review, fix, re-review — on `loop-branch`, up to ten passes, stopping early when there is nothing left to fix or when fixing stops working.

Invocation: `/workcell:review-fix-loop`
Prompting Reference: [`docs/models/gpt-5.6-sol/prompting.md`](../../runtime/docs/models/gpt-5.6-sol/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_agent` with native specialist routing from `agents/models.json`, hold human gates, run VCS and shell operations, and read gate evidence and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

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

## Procedure

1. **Initialize state.** Run once to create the loop branch and state file:

   ```bash
   jj bookmark create loop-branch -r @
   python3 skills/review-fix-loop/scripts/loop_state.py init --branch loop-branch --max-iterations 10 --min-severity high
   ```

2. **Review.** Execute [`code-review`](../code-review/SKILL.md) over changes between `loop-branch` and its base: dispatch `reviewer` agents via `spawn_agent`, verify candidates adversarially, and merge findings with `merge_findings.py --verification`.
3. **Fix.** If substantiated findings at or above `--min-severity` exist, dispatch a `builder` via `spawn_agent` to implement targeted fixes against the findings.
4. **Verify.** Run the project test suite to verify fixes and ensure no regressions occurred.
5. **Bounded stop evaluation.** Advance loop state:

   ```bash
   python3 skills/review-fix-loop/scripts/loop_state.py advance --findings review.json
   ```

   Stop when state indicates `converged` (no remaining findings at or above threshold), `stalled` (no progress across iterations), or `exhausted` (max iterations reached).

## Harness Limitations

API-only model controls (such as dynamic request-level reasoning effort or pro mode toggles) and API-only orchestration features are unsupported in Codex skill prompts; execution relies on native harness tooling and specialist dispatch.
