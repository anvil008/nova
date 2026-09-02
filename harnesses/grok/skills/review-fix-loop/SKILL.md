---
name: review-fix-loop
description: Repeatedly review a change-set and have the builder fix what the review finds, on a dedicated loop-branch, bounded to a fixed number of passes. Drive it with the harness `/loop`; this skill is the body of one iteration and owns the stop conditions.
---

<!-- generated harness-owned procedure: Grok Build -->

# Review-fix loop

Review, fix, re-review — on `loop-branch`, up to ten passes, stopping early when there is nothing
left to fix or when fixing stops working.

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents, hold the human gates, run `git` / `jj` / `gh` for branch, merge, and issue-state operations, and read gate output and handoff records. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator owns `loop-branch`, the iteration bound, and the stop decision returned by `loop_state.py`.

The harness `/loop` provides the repetition. This skill provides what one iteration _does_ and,
more importantly, when the loop must stop. Loop state lives in a file rather than in the session,
because `/loop` re-invokes with a fresh context each tick and an agent that cannot remember which
pass it is on will happily run forever.

## Harness requirement

This skill requires a harness with a `/loop` driver that re-invokes a prompt on a schedule.
Today that is Claude Code (`/loop <interval> <prompt>`). Codex and Antigravity have no equivalent,
so on those harnesses there is no automatic repetition: drive the loop manually by running the
"Every tick" section below as one complete iteration per invocation, and re-invoke it yourself
until `loop_state.py record` reports a stop. The state file makes this safe — every iteration
reads the pass count from disk, so a manual driver gets the same bound and the same stop
conditions as `/loop` does.

## First tick — set up

Do this once, then never again for the life of the loop.

1. Put the work on its own branch. Never run this loop on `main`. The repository is
   jj-colocated (see the `jj` skill), so the branch is a bookmark on the current change:

   ```bash
   jj bookmark create loop-branch -r @
   ```

   Colocation keeps `.git/` in step, so git-based tooling sees `loop-branch` as an ordinary
   branch without any plain-git checkout step.

2. Initialise the state:

   ```bash
   python3 skills/review-fix-loop/scripts/loop_state.py init \
     --branch loop-branch --max-iterations 10 --min-severity high
   ```

   `--min-severity` is the lowest severity that still blocks convergence (`critical`, `high`,
   `medium`, `low`, or `nit`; default `high`). Findings below it are counted and reported on
   every pass but never keep the loop running — pick `medium` when the change should leave with
   no medium findings either, and `nit` only when a fully clean review is the requirement.

   `.workcell/review-fix-loop.json` is working state, not a deliverable — add `.workcell/` to
   `.gitignore` if it is not there already.

## Every tick — one iteration

1. **Review.** Run the [`code-review`](../code-review/SKILL.md) skill over the diff between
   `loop-branch` and its base: select lenses from the change, fan out one read-only
   `reviewer` per lens, then run the independent adversarial verification. Merge to a single
   review JSON with `merge_findings.py --verification`. Do not skip verification to save a pass —
   an unverified finding sends the builder chasing something that is not there.

2. **Decide.** Feed the merged review to the state file and obey the answer:

   ```bash
   python3 skills/review-fix-loop/scripts/loop_state.py record .workcell/review-pass-<n>.json
   ```

   Give each pass's merged review its own pass number and keep it. The state file holds counts
   and a fingerprint, never the findings, so a single overwritten `review.json` would leave the
   loop with only its last pass to account for.

   It prints `continue`, plus the iteration count and a reason. It stops the loop on:

   | Status      | Meaning                                                                                                                                                                         |
   | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
   | `converged` | No findings at or above `--min-severity`. Lower findings may remain — `latest.findings` counts them, and the merged review JSON lists them. This is the good ending.            |
   | `stalled`   | Two consecutive passes reported an _identical_ set of findings at or above `--min-severity` — the fixer is not moving. Clearing only lower findings does not count as movement. |
   | `exhausted` | Hit the iteration bound.                                                                                                                                                        |

3. **Fix — only if `continue` is true.** Dispatch the `builder` to fix the reported findings,
   ranked by severity, `critical` and `high` first. Findings below `--min-severity` are optional
   for the builder; fixing them is welcome but not what the loop is waiting on. Its dispatch brief conforms to [`agents/handoff.md`](../../runtime/handoff.md) and carries `mode: loop`: use the existing working copy on `loop-branch`, open no PR, and run no self-review passes. The `mode: loop` brief carries the findings, the implicated ownership, the documented verification command, and any sealed-test paths — and never the wiki or a namespace path, because the store sits outside every repository and the brief is the only way it could reach the fixer. Everything else holds, including `tdd-guard reseal --reason <text>` for a justified sealed-test amendment.

4. **Verify and commit.** Read the builder's command-linked verification evidence. A red suite ends the iteration — commit nothing, and let the next pass see the same findings, which is exactly the signal `stalled` is designed to catch. On green, commit the iteration with the pass number in the message.

5. Stop when `record` says stop. Report the ending status, the pass count, and the findings that
   remain.

## Stopping well

The bound is the point. Ten passes of an agent editing code against its own reviewer is a lot of
unsupervised change, so the loop is designed to end early and honestly rather than to reach ten:

- `converged` is a real result — hand over the branch, together with the findings below the
  threshold that the last merged review still lists.
- `stalled` usually means the finding needs a human decision, or the builder cannot reach it from
  the findings alone. Report the repeated finding set verbatim; do not retry it.
- `exhausted` means ten passes did not clear the findings. That is a signal about the change, not
  a reason to re-run the loop.

In all three cases the work sits on `loop-branch` and nothing has merged. Opening a PR, filing the
remaining findings as issues (`reconcile_findings.py`), or discarding the branch is the human's
call.

## When the loop stops — consolidate what the passes learned

The loop's endings are worth remembering: `converged`, `stalled`, and `exhausted` all consolidate
here, because a stalled or exhausted ending says more about the change than a clean one does and
throwing it away leaves the next loop to rediscover it. It runs once the loop has reported its
ending status, pass count, and remaining findings, and it neither changes that report nor stands in
for it; it is the only place in this skill that touches the [`wiki`](../wiki/SKILL.md).

1. **Ask whether the project opted in.** This is a command, never a directory test: the store
   lives outside every repository, so nothing in the working copy can answer it.

   ```bash
   python3 -B skills/wiki/scripts/wiki.py status --repo .
   ```

   It prints the resolved `projectKey`, the namespace path, and `present`. When `present: false`
   comes back the project has no namespace, and the loop ends exactly as it ends today — no
   record, no dispatch, no extra tokens, and nothing changed about what the human was handed. The
   same command refuses a repository in eval mode, which ends this step the same way.

2. **Record the evidence, before anything is dispatched.** One write-once bundle holds every pass's
   merged review with the loop state beside them, so the reading that follows has something
   immutable to point at:

   ```bash
   python3 -B skills/wiki/scripts/wiki.py record --repo . \
     --id <YYYY-MM-DD>-review-fix-loop-<slug> --kind review-fix-loop \
     --summary "<ending status and pass count>" \
     --file .workcell/review-pass-1.json --file .workcell/review-pass-<n>.json \
     --file .workcell/review-fix-loop.json
   ```

   This copies files that already exist and writes no prose, which is why the orchestrator runs it
   before there is any agent to attribute a write to; every page of prose is composed later, by the
   agent dispatched in step 3, through this same CLI. `record` prints the raw id it wrote, and the
   dispatch below cites that printed id rather than a path.

3. **Dispatch the consolidation.** Exactly one `documenter` dispatch, conforming to
   [`agents/handoff.md`](../../runtime/handoff.md); a fan-out would race on the same append-only
   pages. Its `ownership` is the namespace path that `status` printed —
   `~/.workcell/wiki/<project-key>/**` — resolved at dispatch time rather than written here as a
   literal. The brief carries that ownership, the raw id, the ending status and the pass count,
   the question worth answering — what recurred across the passes, and what the fixer could not
   reach from the findings alone — and
   [`skills/wiki/references/wiki-layout.md`](../wiki/references/wiki-layout.md) as the artifact
   contract it writes to. The agent composes its own prose and passes it to `wiki.py`, and never
   edits a file in the namespace directly — one CLI as the sole writer is what keeps write-once
   bundles, append-only pages, and the invariants `check` re-proves true.

4. **Read the gate.** The exit step is done when `wiki.py check` exits zero, having re-hashed
   every recorded file against its manifest and re-linked every citation. The orchestrator never
   reads the pattern pages to judge them; it sends each offender `check` names back to the same
   agent instead of repairing a namespace itself.

## Boundaries

Never run on `main`, never merge `loop-branch`, never push without being asked, and never raise
`--max-iterations` to get past a `stalled` or `exhausted` ending — both mean the loop has told you
something. Restarting a finished loop needs an explicit `init --force`.

## Offline demonstration

Reads and writes a scratch state file under the gitignored `.workcell/` directory only; no GitHub,
no subagents, no tracked repository changes:

```bash
python3 skills/review-fix-loop/scripts/loop_state.py --state .workcell/demo/loop.json init --max-iterations 3 --min-severity medium
python3 skills/review-fix-loop/scripts/loop_state.py --state .workcell/demo/loop.json record skills/code-review/examples/expected-review.json
python3 skills/review-fix-loop/scripts/loop_state.py --state .workcell/demo/loop.json status
```
