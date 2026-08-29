---
name: build
description: Execute an approved planner milestone as resumable dependency waves of isolated builders, then integrate and verify each wave.
---

# Build

Execute one approved milestone plan. Inputs are its plan name, GitHub issues, and `plan.sidecar.json`. The sidecar supplies stable `key`, `dependsOn`, `ownershipHint`, `wave`, and the durable planner marker. GitHub is the source of truth for issue state; resume by reading it again and re-deriving the current wave.

## Wave loop

1. Validate the sidecar and capture GitHub issue state. An issue is done when it is closed or carries the `status:done` label; the label lets the primary agent mark an issue done after combined GREEN without closing it yet, and `waves.py` treats both identically. An issue is unblocked only when every dependency issue is done. The current wave is every unblocked, not-done issue in the earliest unfinished declared wave. `skills/build/scripts/waves.py` provides a strict offline dry-run over a captured snapshot.
2. Check ownership before dispatch. Run one builder per unblocked issue in parallel, each in its own **jj workspace**, only when `ownershipHint` globs are genuinely independent. Serialize overlapping ownership. `waves.py` rejects a sidecar whose grouped wave (1 and up) has overlapping hints; wave 0 is the ungrouped bucket, so an overlap there is warned about, not rejected, and must be serialized by hand.

   Dispatch every builder in a wave on the same integration base, and make that base `trunk()` unless you are
   deliberately stacking. Builders open their PRs against `main` with an explicit `--base`, so handing one a
   sibling's bookmark or an unmerged PR head puts commits it did not write into its diff.

   Builders share one repo and isolate through `jj workspace add`, not through separate clones or git worktrees — one repo, one operation log, many working copies. Ensure the repo is jj-managed before the first wave dispatches; a builder landing in a git-only repo will adopt it with `jj git init --colocate`, and it is cheaper to do that once up front than to race two builders doing it at the same moment.

3. Collect each branch, PR, changed files, command-linked test evidence, and the outcome of the builder's two review passes. A builder reviews its own change-set before opening a PR and stops after two passes; one that returns `blocked` has unresolved `critical`/`high` findings and **no PR** — decide whether to re-dispatch, re-scope, or escalate. A builder that returns `blocked` may be re-dispatched at most twice per issue; after the second re-dispatch still returns `blocked`, mark the issue **stalled** in the wave summary and the loop escalates to the human instead of dispatching again. A builder completes one issue; it does not merge or declare the milestone done.

   Builders tear down their own workspace once their PR is open. If a builder dies mid-issue, its workspace is left behind: `jj workspace list` shows it, `jj workspace forget <name>` plus removing the directory reclaims it, and the bookmark and commits survive that.
4. Treat every PR as tested on its old base. The primary agent integrates the wave by serial merge plus retest, or on an integration branch, and runs a combined GREEN verification before marking issues done. Merge only after combined green.
5. Refresh GitHub state, advance, and repeat until no planned issue remains.

The primary agent is the sole synthesis, final verification, and completion authority and must never force-push main, merge before combined GREEN, or infer completion from a builder report alone.

## Offline demonstration

This command reads fixtures only; it never calls or changes GitHub:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 skills/build/scripts/waves.py skills/build/examples/plan.sidecar.json skills/build/examples/issue-state.json
```
