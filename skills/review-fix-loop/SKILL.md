---
name: review-fix-loop
description: Repeatedly review a change-set and have the builder fix what the review finds, on a dedicated loop-branch, bounded to a fixed number of passes. Drive it with the harness `/loop`; this skill is the body of one iteration and owns the stop conditions.
---

# Review-fix loop

Review, fix, re-review — on `loop-branch`, up to ten passes, stopping early when there is nothing
left to fix or when fixing stops working.

The harness `/loop` provides the repetition. This skill provides what one iteration *does* and,
more importantly, when the loop must stop. Loop state lives in a file rather than in the session,
because `/loop` re-invokes with a fresh context each tick and an agent that cannot remember which
pass it is on will happily run forever.

## First tick — set up

Do this once, then never again for the life of the loop.

1. Put the work on its own branch. Never run this loop on `main`.

   ```bash
   jj bookmark create loop-branch -r @   # jj repos — see the `jj` skill
   git switch -c loop-branch             # plain git repos
   ```

2. Initialise the state:

   ```bash
   python3 skills/review-fix-loop/scripts/loop_state.py init \
     --branch loop-branch --max-iterations 10
   ```

   `.swarm/review-fix-loop.json` is working state, not a deliverable — add `.swarm/` to
   `.gitignore` if it is not there already.

## Every tick — one iteration

1. **Review.** Run the [`code-review`](../code-review/SKILL.md) skill over the diff between
   `loop-branch` and its base: select lenses from the change, fan out one read-only
   `code-reviewer` per lens, then run the independent adversarial verification. Merge to a single
   review JSON with `merge_findings.py --verification`. Do not skip verification to save a pass —
   an unverified finding sends the builder chasing something that is not there.

2. **Decide.** Feed the merged review to the state file and obey the answer:

   ```bash
   python3 skills/review-fix-loop/scripts/loop_state.py record review.json
   ```

   It prints `continue`, plus the iteration count and a reason. It stops the loop on:

   | Status | Meaning |
   |---|---|
   | `converged` | The review reported no findings. This is the good ending. |
   | `stalled` | Two consecutive passes reported an *identical* finding set — the fixer is not moving. |
   | `exhausted` | Hit the iteration bound. |

3. **Fix — only if `continue` is true.** Dispatch the `builder` to fix the reported findings,
   ranked by severity, `critical` and `high` first. The builder runs in a reduced mode here:

   - it works on `loop-branch` in the existing working copy, taking no new jj workspace, since
     the loop owns the branch;
   - there is no GitHub issue and no PR per iteration — the loop opens one at the end, if at all;
   - it does **not** run its own two review passes; this loop is that review;
   - everything else holds: tests stay green, no sealed test is touched except through
     `tdd-guard reseal --reason <text>`, and it writes only what the findings implicate.

4. **Verify and commit.** Run the project's test command. A red suite ends the iteration — commit
   nothing, and let the next pass see the same findings, which is exactly the signal `stalled` is
   designed to catch. On green, commit the iteration with the pass number in the message.

5. Stop when `record` says stop. Report the ending status, the pass count, and the findings that
   remain.

## Stopping well

The bound is the point. Ten passes of an agent editing code against its own reviewer is a lot of
unsupervised change, so the loop is designed to end early and honestly rather than to reach ten:

- `converged` is a real result — hand over the branch.
- `stalled` usually means the finding needs a human decision, or the builder cannot reach it from
  the findings alone. Report the repeated finding set verbatim; do not retry it.
- `exhausted` means ten passes did not clear the findings. That is a signal about the change, not
  a reason to re-run the loop.

In all three cases the work sits on `loop-branch` and nothing has merged. Opening a PR, filing the
remaining findings as issues (`reconcile_findings.py`), or discarding the branch is the human's
call.

## Boundaries

Never run on `main`, never merge `loop-branch`, never push without being asked, and never raise
`--max-iterations` to get past a `stalled` or `exhausted` ending — both mean the loop has told you
something. Restarting a finished loop needs an explicit `init --force`.

## Offline demonstration

Reads and writes a temporary state file only; no GitHub, no subagents, no repository changes:

```bash
python3 skills/review-fix-loop/scripts/loop_state.py --state /tmp/loop.json init --max-iterations 3
python3 skills/review-fix-loop/scripts/loop_state.py --state /tmp/loop.json record skills/code-review/examples/expected-review.json
python3 skills/review-fix-loop/scripts/loop_state.py --state /tmp/loop.json status
```
