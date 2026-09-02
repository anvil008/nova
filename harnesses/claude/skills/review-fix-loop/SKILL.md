---
name: review-fix-loop
description: Repeatedly review a change-set and have the builder fix what the review finds, on a dedicated loop-branch, bounded to a fixed number of passes. Drive it with the harness `/loop`; this skill is the body of one iteration and owns the stop conditions.
---

# Review-Fix Loop

Review, fix, re-review — on `loop-branch`, up to ten passes, stopping early when there is nothing left to fix or when fixing stops working.

Invocation: `/workcell:review-fix-loop`
Prompting Reference: [`docs/models/claude-sonnet-5/prompting.md`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents, hold the human gates, run `git` / `jj` / `gh` for branch, merge, and issue-state operations, and read gate output and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator owns `loop-branch`, the iteration bound, and the stop decision returned by `loop_state.py`.

The harness `/loop` provides the repetition. This skill provides what one iteration _does_ and, more importantly, when the loop must stop. Loop state lives in a file rather than in the session, because `/loop` re-invokes with a fresh context each tick and an agent that cannot remember which pass it is on will happily run forever.

## Ordered Gates

Execution proceeds through four strict, ordered gates:
1. **review**: Run multi-lens review over current changes on `loop-branch` and adversarially verify all candidate findings.
2. **fix**: Dispatch a builder to resolve substantiated findings at or above minimum severity.
3. **verify**: Execute the project verification suite to ensure fixes are passing and cause no regressions.
4. **bounded stop**: Evaluate loop convergence state via `loop_state.py` to stop upon convergence, stalling, or pass exhaustion.

## Harness Requirement

This skill requires a harness with a `/loop` driver that re-invokes a prompt on a schedule. Today that is Claude Code (`/loop <interval> <prompt>`).

## First Tick — Set Up

Do this once, then never again for the life of the loop.

1. Put the work on its own branch. Never run this loop on `main`. The repository is jj-colocated (see the `jj` skill), so the branch is a bookmark on the current change:

   ```bash
   jj bookmark create loop-branch -r @
   ```

   Colocation keeps `.git/` in step, so git-based tooling sees `loop-branch` as an ordinary branch without any plain-git checkout step.

2. Initialise the state:

   ```bash
   python3 skills/review-fix-loop/scripts/loop_state.py init      --branch loop-branch --max-iterations 10 --min-severity high
   ```

   `--min-severity` is the lowest severity that still blocks convergence (`critical`, `high`, `medium`, `low`, or `nit`; default `high`). Findings below it are counted and reported on every pass but never keep the loop running — pick `medium` when the change should leave with no medium findings either, and `nit` only when a fully clean review is the requirement.

   `.workcell/review-fix-loop.json` is working state, not a deliverable — add `.workcell/` to `.gitignore` if it is not there already.

## Every Tick — One Iteration

1. **Review.** Run the [`code-review`](../code-review/SKILL.md) skill over the diff between `loop-branch` and its base: select lenses from the change, fan out one read-only `reviewer` per lens, then run the independent adversarial verification. Merge to a single review JSON with `merge_findings.py --verification`. Do not skip verification to save a pass — an unverified finding sends the builder chasing something that is not there.

2. **Decide.** Feed the merged review to the state file and obey the answer:

   ```bash
   python3 skills/review-fix-loop/scripts/loop_state.py record .workcell/review-pass-<n>.json
   ```

   Give each pass's merged review its own pass number and keep it. The state file holds counts and a fingerprint, never the findings, so a single overwritten `review.json` would leave the loop with only its last pass to account for.

   It prints `continue`, plus the iteration count and a reason. It stops the loop on:

   | Status      | Meaning                                                                                                                                                                         |
   | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
   | `converged` | No findings at or above `--min-severity`. Lower findings may remain — `latest.findings` counts them, and the merged review JSON lists them. This is the good ending.            |
   | `stalled`   | Two consecutive passes reported an _identical_ set of findings at or above `--min-severity` — the fixer is not moving. Clearing only lower findings does not count as movement. |
   | `exhausted` | Hit the iteration bound.                                                                                                                                                        |

3. **Fix — only if `continue` is true.** Dispatch the `builder` to fix the reported findings, ranked by severity, `critical` and `high` first. Findings below `--min-severity` are optional for the builder; fixing them is welcome but not what the loop is waiting on. Its dispatch brief conforms to [`anvil.agent-handoff/v1`](../../runtime/handoff.md) and carries `mode: loop`: use the existing working copy on `loop-branch`, open no PR, and run no self-review passes. The `mode: loop` brief carries the findings, the implicated ownership, the documented verification command, and any sealed-test paths — and never the wiki or a namespace path, because the store sits outside every repository and the brief is the only way it could reach the fixer. Everything else holds, including `tdd-guard reseal --reason <text>` for a justified sealed-test amendment.

4. **Verify and commit.** Read the builder's command-linked verification evidence. A red suite ends the iteration — commit nothing, and let the next pass see the same findings, which is exactly the signal `stalled` is designed to catch. On green, commit the iteration with the pass number in the message.

5. Stop when `record` says stop. Report the ending status, the pass count, and the findings that remain.

## Harness Limitations

Native context forks and workflows are omitted with notes in Claude Code; procedures execute sequentially within the primary session.
