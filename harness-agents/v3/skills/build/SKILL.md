---
name: build
description: Execute an approved planner milestone as resumable dependency waves of isolated builders, then integrate and verify each wave.
---

# Build

Execute one approved milestone plan. Inputs are its plan name, GitHub issues, and `plan.sidecar.json`. The sidecar supplies stable `key`, `dependsOn`, `ownershipHint`, `wave`, and the durable planner marker. GitHub is the source of truth for issue state; resume by reading it again and re-deriving the current wave.

## Wave loop

1. Validate the sidecar and capture GitHub issue state. An issue is unblocked only when every dependency issue is closed or marked done. The current wave is every unblocked, not-done issue in the earliest unfinished declared wave. `scripts/waves.py` provides a strict offline dry-run over a captured snapshot.
2. Check ownership before dispatch. Run one builder per unblocked issue in parallel in isolated worktrees only when `ownershipHint` globs are genuinely independent. Serialize overlapping ownership.
3. Collect each branch, PR, changed files, and command-linked test evidence. A builder completes one issue; it does not merge or declare the milestone done.
4. Treat every PR as tested on its old base. The primary agent integrates the wave by serial merge plus retest, or on an integration branch, and runs a combined GREEN verification before marking issues done. Merge only after combined green.
5. Refresh GitHub state, advance, and repeat until no planned issue remains.

The primary agent is the sole synthesis, final verification, and completion authority and must never force-push main, merge before combined GREEN, or infer completion from a builder report alone.

## Offline demonstration

This command reads fixtures only; it never calls or changes GitHub:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/waves.py examples/plan.sidecar.json examples/issue-state.json
```
