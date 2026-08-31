---
name: build
description: Execute an approved planner milestone as resumable dependency waves — a specifier agent seals each issue's failing tests, an isolated builder implements against them, and an integrator verifies each wave.
---

# Build

Execute one approved milestone plan. Inputs are its plan name, GitHub issues, and `plan.sidecar.json`. The sidecar supplies stable `key`, `dependsOn`, `ownershipHint`, `wave`, and the durable planner marker. GitHub is the source of truth for issue state; resume by reading it again and re-deriving the current wave.

You are the orchestrator ([ADR 0007](../../docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents, hold the human gates, run `git` / `jj` / `gh` for branch, merge, and issue-state operations, and read gate output and handoff records. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator schedules waves, creates integration branches when requested, and accepts or rejects each wave from mechanical evidence.

## Wave loop

1. Validate the sidecar and capture GitHub issue state. The one definition implemented by `skills/build/scripts/waves.py` is: an issue is done when it is closed **and** (`status:done` or `state_reason == completed`). The label covers a closed-as-`not_planned` issue that was in fact finished, and it may mark work done before the merged PR auto-closes it; until closure, the issue remains not done. A `not_planned` closure without that label is housekeeping, never finished work (`skills/planner/scripts/reconcile_github.py` closes stale issues that way on purpose). An issue is unblocked only when every dependency issue is done. The current wave is every unblocked, not-done issue in the earliest unfinished declared wave. `waves.py` provides a strict offline dry-run over a captured snapshot.

   Capture that snapshot with `REPO` and `MILESTONE` exported (`REPO=owner/repo`, `MILESTONE` the milestone title). It writes `{repo, milestone, issues:[{number, body, labels, state, state_reason}]}` and drops the pull requests the issues endpoint returns alongside issues. The milestone is filtered by title in `jq`, so `--paginate` is not optional — the `100` cap is over every milestoned issue in the repo, not over this milestone's — and `jq -s` is what flattens the one array per page `--paginate` emits into a single snapshot:

   ```bash
   gh api --paginate "repos/$REPO/issues?milestone=*&state=all&per_page=100" \
     | jq -s --arg repo "$REPO" --arg milestone "$MILESTONE" '{
         repo: $repo,
         milestone: $milestone,
         issues: [
           .[][]
           | select(has("pull_request") | not)
           | select(.milestone.title == $milestone)
           | {number, body, labels: [.labels[].name], state, state_reason}
         ] | sort_by(.number)
       }' > issue-state.json
   ```

   `waves.py` also accepts gh's raw label objects, so a snapshot captured any other way (`gh issue list --json labels`) validates unchanged.

2. Check ownership before dispatch. Run one issue-pair per unblocked issue in parallel, each in its own **jj workspace**, only when `ownershipHint` globs are genuinely independent. Serialize overlapping ownership. `waves.py` rejects a sidecar whose grouped wave (1 and up) has overlapping hints; wave 0 is the ungrouped bucket, so an overlap there is warned about, not rejected, and must be serialized by hand.

   Dispatch every issue in a wave on the same base. In default multi-PR mode that base is `trunk()` unless you are deliberately stacking, and builders open their PRs against `main` with an explicit `--base`. In single-PR mode the base is the integration bookmark defined below. Handing a builder a sibling's bookmark or an unmerged PR head puts commits it did not write into its diff.

   Agents share one repo and isolate through one helper, `workcell-ws add <key>`, not through separate clones — one repo, one operation log, many working copies at the sibling path `../<repo>-<key>`. It runs `jj workspace add` where the repo is jj-managed and `git worktree add` where it is not, so the naming and the teardown are the same in either (`docs/workspaces.md`). Ensure the repo is jj-managed before the first wave dispatches; a `specifier` landing in a git-only repo will adopt it with `jj git init --colocate`, and it is cheaper to do that once up front than to race two of them doing it at the same moment.

3. **Dispatch each issue in two phases, in order.** The separation is the point: the agent that defines "done" is not the agent judged against it.

   - **Phase 1 — `specifier`.** It creates the workspace and branch, writes the issue's `acceptanceTests` as real failing tests, proves honest RED, and runs `tdd-guard seal`. A `specifier` that returns `blocked` could not express an acceptance test as a runnable failing test — that is a **plan** defect, not a build one. Do not dispatch the builder; take the unsealed entry back to the planner or the human.
   - **Phase 2 — `builder`.** Only after the seal exists. It enters the same workspace, implements, verifies GREEN, self-reviews, opens the PR, and tears the workspace down. It cannot edit the sealed tests: the guard denies those edits outright.

   Never run the two phases concurrently, and never dispatch a builder for an issue with no seal — an unsealed builder is a builder grading its own homework.

   A **behaviour-preserving refactor** replaces the RED requirement with a GREEN one inside the same `tdd-guard` state machine. [`code-refactor`](../code-refactor/SKILL.md) runs without a specifier. In that mode **you create the workspace and branch yourself** with `workcell-ws add <issue-key> --base <integration-base>`, then dispatch an `integrator` with `mode: baseline`, `workspace`, `sealedTests`, and `baselineCommand`. It returns green evidence plus a `kind: baseline` seal and hands that seal off; only then dispatch the `builder` with `mode: refactor`. The builder verifies GREEN after the seal and records the real diff as usual, so the Stop hook and `status --json` work unchanged.

4. Collect each branch, PR, changed files, command-linked test evidence, the runtime evidence (`evidence.runtime`: the surface the builder exercised, the commands it ran, and its console-error count), and the outcome of the builder's two review passes. A builder reviews its own change-set before opening a PR and stops after two passes; one that returns `blocked` has unresolved `critical`/`high` findings and **no PR** — decide whether to re-dispatch, re-scope, or escalate. A builder that returns `blocked` may be re-dispatched at most twice per issue; after the second re-dispatch still returns `blocked`, mark the issue **stalled** in the wave summary and escalate to the human instead of dispatching again. A builder completes one issue; it does not merge or declare the milestone done.

   Builders tear down their own workspace once their PR is open. If an agent dies mid-issue, its workspace is left behind: `workcell-ws list` shows it and `workcell-ws forget <name>` reclaims it — the same `jj workspace list` and `jj workspace forget <name>` plus removing the directory — and the bookmark and commits survive that. Before resuming a wave, and after any run that crashed, run `workcell-ws sweep`; it names every stranded workspace and every bookmark already merged into the default branch, and `--apply` removes exactly those.
5. **Treat every PR as tested on its old base.** Dispatch an `integrator` to build the combined state — serial merge onto a scratch ref in default mode, or the named integration branch in single-PR mode — and to run the full suite there. It returns command-linked evidence and the mechanical gate output; it does not decide anything.

   Accept the wave on the **evidence**, not on the summary: a combined GREEN run whose `commandId`s you can see, `tdd-guard status --json` fresh for every issue, and `gh pr checks` passing. A prose claim of success from any agent is worth nothing. If the integrator names an offending PR, send that issue back to its builder and re-integrate; do not merge a wave around it.
6. Merge only after combined green, then refresh GitHub state, advance, and repeat until no planned issue remains. In default mode, merge the wave PRs to `main`; in single-PR mode, merge them into the integration branch.

You are the sole completion authority. Never force-push `main`, never merge before combined GREEN, and never infer completion from an agent's report — read the gates.

## Single-PR mode

Entry skills that promise one PR opt into this mode; the default multi-PR mode above is unchanged.

1. Before the first wave, create an integration branch from `trunk()` named `<planId>-integration`:

   ```bash
   jj bookmark create <planId>-integration -r trunk()
   ```

2. In every dispatch brief defined by [`agents/handoff.md`](../../agents/handoff.md), pass that branch as the `base` field. Builders open their per-issue PRs against `<planId>-integration`, never `main`.
3. After each wave, the `integrator` verifies the combined wave on the integration branch. On combined GREEN, merge the wave's PRs into that branch and advance from it.
4. When no planned issue remains, open the **final PR from the integration branch to `main`**. Repeat every `Closes #<n>` line from the per-issue PR bodies in the final PR body, because GitHub auto-closes issues only when a PR merges to the default branch. This final PR is the single PR to `main`; the intermediate PRs are integration-branch mechanics.

## Offline demonstration

This command reads fixtures only; it never calls or changes GitHub:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 skills/build/scripts/waves.py skills/build/examples/plan.sidecar.json skills/build/examples/issue-state.json
```
