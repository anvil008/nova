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

   Stop when state indicates `converged` (no remaining findings at or above threshold), `stalled` (no progress across iterations), or `exhausted` (max iterations reached). Report the ending status, pass count, and findings that remain.

## Stopping Well

The bound is the point. Ten passes of an agent editing code against its own reviewer is a lot of unsupervised change, so the loop is designed to end early and honestly rather than to reach ten:

- `converged` is a real result — hand over the branch, together with the findings below the threshold that the last merged review still lists.
- `stalled` usually means the finding needs a human decision, or the builder cannot reach it from the findings alone. Report the repeated finding set verbatim; do not retry it.
- `exhausted` means ten passes did not clear the findings. That is a signal about the change, not a reason to re-run the loop.

In all three cases the work sits on `loop-branch` and nothing has merged. Opening a PR, filing the remaining findings as issues (`reconcile_findings.py`), or discarding the branch is the human's call.

## When the Loop Stops — Consolidate What the Passes Learned

The loop's endings are worth remembering: `converged`, `stalled`, and `exhausted` all consolidate here, because a stalled or exhausted ending says more about the change than a clean one does and throwing it away leaves the next loop to rediscover it. It runs once the loop has reported its ending status, pass count, and remaining findings, and it neither changes that report nor stands in for it; it is the only place in this skill that touches the [`wiki`](../wiki/SKILL.md).

1. **Ask whether the project opted in.** This is a command, never a directory test: the store lives outside every repository, so nothing in the working copy can answer it:

   ```bash
   python3 -B skills/wiki/scripts/wiki.py status --repo .
   ```

   It prints the resolved `projectKey`, the namespace path, and `present`. When `present: false` comes back the project has no namespace, and the loop ends immediately — no record, no dispatch, no extra tokens, and nothing changed about what the human was handed. The same command refuses a repository in eval mode, which ends this step the same way.

2. **Record the evidence, before anything is dispatched.** One write-once bundle holds every pass's merged review with the loop state beside them, so the reading that follows has something immutable to point at:

   ```bash
   python3 -B skills/wiki/scripts/wiki.py record --repo . \
     --id <YYYY-MM-DD>-review-fix-loop-<slug> --kind review-fix-loop \
     --summary "<ending status and pass count>" \
     --file .workcell/review-pass-1.json --file .workcell/review-pass-<n>.json \
     --file .workcell/review-fix-loop.json
   ```

   This copies files that already exist and writes no prose, which is why the orchestrator runs it before there is any agent to attribute a write to; every page of prose is composed later, by the agent dispatched in step 3, through this same CLI. `record` prints the raw id it wrote, and the dispatch below cites that printed id rather than a path.

3. **Dispatch the consolidation.** Exactly one `documenter` dispatch via `spawn_agent`, conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md); a fan-out would race on the same append-only pages. Its `ownership` is the namespace path that `status` printed — `~/.workcell/wiki/<project-key>/**` — resolved at dispatch time rather than written here as a literal. The brief carries that ownership, the raw id, the ending status and the pass count, the question worth answering — what recurred across the passes, and what the fixer could not reach from the findings alone — and [`skills/wiki/references/wiki-layout.md`](../wiki/references/wiki-layout.md) as the artifact contract it writes to. The agent composes its own prose and passes it to `wiki.py`, and never edits a file in the namespace directly — one CLI as the sole writer is what keeps write-once bundles, append-only pages, and the invariants `check` re-proves true.

4. **Read the gate.** The exit step is done when `wiki.py check` exits zero, having re-hashed every recorded file against its manifest and re-linked every citation. The orchestrator never reads the pattern pages to judge them; it sends each offender `check` names back to the same agent instead of repairing a namespace itself.

## Boundaries

Never run on `main`, never merge `loop-branch`, never push without being asked, and never raise `--max-iterations` to get past a `stalled` or `exhausted` ending — both mean the loop has told you something. Restarting a finished loop needs an explicit `init --force`.

## Offline Demonstration

Reads and writes a scratch state file under the gitignored `.workcell/` directory only; no GitHub, no subagents, no tracked repository changes:

```bash
python3 skills/review-fix-loop/scripts/loop_state.py --state .workcell/demo/loop.json init --max-iterations 3 --min-severity medium
python3 skills/review-fix-loop/scripts/loop_state.py --state .workcell/demo/loop.json record skills/code-review/examples/expected-review.json
python3 skills/review-fix-loop/scripts/loop_state.py --state .workcell/demo/loop.json status
```

## Harness Limitations

API-only model controls (such as dynamic request-level reasoning effort or pro mode toggles) and API-only orchestration features are unsupported in Codex skill prompts; execution relies on native harness tooling and specialist dispatch.
