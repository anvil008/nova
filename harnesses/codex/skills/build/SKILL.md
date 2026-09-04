---
name: build
description: Execute an approved planner milestone as resumable dependency waves — a specifier agent seals each issue's failing tests, an isolated builder implements against them, and an integrator verifies each wave.
---

# Build

Execute one approved milestone plan. Inputs are its plan name, GitHub issues, and `plan.sidecar.json`. The sidecar supplies stable `key`, `dependsOn`, `ownershipHint`, `wave`, and the durable planner marker. GitHub is the source of truth for issue state; resume by reading it again and re-deriving the current wave.

Invocation: `/workcell:build`
Prompting Reference: [`docs/models/gpt-5.6-sol/prompting.md`](../../runtime/docs/models/gpt-5.6-sol/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_agent` with native specialist routing from `agents/models.json`, hold human gates, run workspace isolation and VCS operations using shell execution, and exchange handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code, run its test suites, or author its artifacts directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Drive an approved planner milestone to completion across resumable dependency waves with strict test-driven development discipline.
- **Constraints and Boundaries:** Never dispatch a builder without a sealed failing test. Never modify sealed tests during implementation. Never merge before combined GREEN evidence. Never commit directly to `main`.
- **Success Criteria:** Every milestone issue completed against sealed acceptance tests, verified through clean review passes and green integration runs.

## Ordered Gates

Execution proceeds through five strict, ordered gates:

1. **approved plan**: Validate `plan.sidecar.json` and snapshot GitHub issue state to schedule dependency waves.
2. **specifier RED seal**: Specifier authors failing acceptance tests and seals them with `tdd-guard seal`.
3. **builder GREEN**: Builder implements against sealed tests, verifies green, and conducts self-reviews.
4. **review passes**: Builder completes self-review passes or multi-lens code reviews without unaddressed blockers.
5. **integration**: Integrator verifies combined wave state with command-linked test evidence on an integration ref.

## Wave loop

1. Validate the sidecar and capture GitHub issue state. The one definition implemented by `skills/build/scripts/waves.py` is: an issue is done when it is closed **and** (`status:done` or `state_reason == completed`). The label covers a closed-as-`not_planned` issue that was in fact finished, and it may mark work done before the merged PR auto-closes it; until closure, the issue remains not done. A `not_planned` closure without that label is housekeeping, never finished work (`skills/plan/scripts/reconcile_github.py` closes stale issues that way on purpose). An issue is unblocked only when every dependency issue is done. Selection is gated on that, not on the declared wave: every not-done issue whose dependencies are all done is a candidate for this round, regardless of declared wave, so one straggler never freezes work whose own dependencies are already merged. A candidate declared later than `currentWave` is reported as pulled forward (`pulledForward: true`). `currentWave` keeps its meaning — the earliest unfinished declared wave — as reporting and resume, never as a filter. `waves.py` provides a strict offline dry-run over a captured snapshot.

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

2. Check ownership before dispatch, across the whole candidate in-flight set rather than per declared wave. Run one issue-pair per unblocked issue in parallel, each in its own **jj workspace**, only when `ownershipHint` globs are genuinely independent. `waves.py` does that check itself: a candidate whose hint overlaps an already-selected one is left out of `unblocked` and named in `deferred` with the `overlapsWith` key it collides with, and you dispatch it in a later round. Overlapping work is never dispatched concurrently. Candidates are considered earliest declared wave first, so a deliberately coarse late hint — a whole-repository documentation pass, say — defers itself rather than starving the issues it overlaps. A declared overlap inside a grouped wave (1 and up) is still rejected outright, because the planner asserted a parallelism the hints cannot deliver; wave 0 is the ungrouped bucket, so an overlap there is warned about rather than rejected, and the colliding candidate is held back by the same in-flight check as any other — the warning names a pair, the deferral is decided against the whole selected set, so which key ends up in `deferred` is `waves.py`'s answer, not the warning's.

   You may dispatch a subset of `unblocked` when you want to cap concurrency; whatever you hold back simply returns as a candidate in a later round. Dispatch every issue in a round on the same base, pulled-forward issues included — they join the same integration round as the rest. Intermediate PR creation is eliminated: builders commit locally in isolated jj workspaces and never push intermediate branches or open pull requests. In single-PR mode the base is the integration bookmark defined below (<planId>-integration), while in default mode that base is `trunk()` unless you are deliberately stacking. Handing a builder a sibling's bookmark or an unmerged head puts commits it did not write into its diff.

   Agents share one repo and isolate through one helper, `workcell-ws add <key>`, not through separate clones — one repo, one operation log, many working copies at the sibling path `../<repo>-<key>`. An issue's key is `<type>/<issue-key>`, the type coming from the planner's `type:feature` / `type:bug` label — `feature/` when there is none, `bug/` where the issue is a defect — and the directory writes that slash as a dash ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). It runs `jj workspace add` where the repo is jj-managed and `git worktree add` where it is not, so the naming and the teardown are the same in either ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). Ensure the repo is jj-managed before the first wave dispatches; a `specifier` landing in a git-only repo will adopt it with `jj git init --colocate`, and it is cheaper to do that once up front than to race two of them doing it at the same moment.

3. **Dispatch each issue in two phases, in order.** The separation is the point: the agent that defines "done" is not the agent judged against it.

   - **Phase 1 — `specifier`.** Dispatch via `spawn_agent`. It creates the workspace and branch, writes the issue's `acceptanceTests` as real failing tests, proves honest RED, and runs `tdd-guard seal`. A `specifier` that returns `blocked` could not express an acceptance test as a runnable failing test — that is a **plan** defect, not a build one. Do not dispatch the builder; take the unsealed entry back to the planner or the human.
   - **Phase 2 — `builder`.** Dispatch via `spawn_agent` only after the seal exists. It enters the same workspace, implements against the sealed tests, and is instructed to verify ONLY sealed acceptance tests via `tdd-guard verify --green-command ...` (~5s), explicitly forbidding broad test suites or whole-project discovery suites (`scripts/run-tests.sh`). Intermediate PR creation is eliminated: builders commit locally in isolated jj workspaces via `jj describe -m "..."`, hand off their local `changeId`, and tear the workspace down. It cannot edit the sealed tests: the guard denies those edits outright.

   Never run the two phases concurrently, and never dispatch a builder for an issue with no seal — an unsealed builder is a builder grading its own homework.

   A **behaviour-preserving refactor** replaces the RED requirement with a GREEN one inside the same `tdd-guard` state machine. [`code-refactor`](../code-refactor/SKILL.md) runs without a specifier. In that mode **you create the workspace and branch yourself** with `workcell-ws add refactor/<issue-key> --base <integration-base>` — the `refactor/` type says what the branch is for ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)) — then dispatch an `integrator` with `mode: baseline`, `workspace`, `sealedTests`, and `baselineCommand`. It returns green evidence plus a `kind: baseline` seal and hands that seal off; only then dispatch the `builder` with `mode: refactor`. The builder verifies GREEN after the seal and records the real diff as usual, so the Stop hook and `status --json` work unchanged.

4. Collect each branch, local `changeId`, changed files, command-linked test evidence, the runtime evidence (`evidence.runtime`: the surface the builder exercised, the commands it ran, and its console-error count), and the outcome of the builder's two review passes. A builder reviews its own change-set before committing locally and stops after two passes; one that returns `blocked` has unresolved `critical`/`high` findings and hands off no commit — decide whether to re-dispatch, re-scope, or escalate. A builder that returns `blocked` may be re-dispatched at most twice per issue; after the second re-dispatch still returns `blocked`, mark the issue **stalled** in the wave summary and escalate to the human instead of dispatching again. A builder completes one issue; it does not merge or declare the milestone done.

   Builders tear down their own workspace after committing locally and handing off their `changeId`. If an agent dies mid-issue, its workspace is left behind: `workcell-ws list` shows it and `workcell-ws forget <name>` reclaims it — the same `jj workspace list` and `jj workspace forget <name>` plus removing the directory — and the bookmark and commits survive that. Before resuming a wave, and after any run that crashed, run `workcell-ws sweep`; it names every stranded workspace and every bookmark already merged into the default branch, and `--apply` removes exactly those.

5. **Treat every PR as tested on its old base.** Dispatch an `integrator` via `spawn_agent` to combine the wave changes onto the integration trunk. The integrator uses `jj rebase -s <changeId> -d <planId>-integration` to instantly combine wave changes onto the integration trunk in 50ms with zero network roundtrips (or onto a scratch ref in default mode). The integrator runs the full project test suite (`scripts/run-tests.sh` + linters) ONCE on the combined wave state. It returns command-linked evidence and the mechanical gate output; it does not decide anything.

   Accept the wave on the **evidence**, not on the summary: a combined GREEN run whose `commandId`s you can see, `tdd-guard status --json` fresh for every issue, and `gh pr checks` passing. A prose claim of success from any agent is worth nothing. If the integrator names an offending PR, send that issue back to its builder and re-integrate; do not merge a wave around it.

   **Record the accepted wave.** Only when `python3 -B skills/wiki/scripts/wiki.py status --repo .` reports the project's namespace as present do you record anything at all; that same call is what refuses a repository in eval mode, so no eval condition of your own belongs here, and a project with no namespace runs this loop exactly as it does today. Where it is present, write the integrator's handoff record and the gate output you accepted on into a `mktemp -d` scratch directory — never into the repository, so no diff gains a file — and pass those real paths to `python3 -B skills/wiki/scripts/wiki.py record --repo . --id <YYYY-MM-DD>-build-wave-<planId>-<nth-accepted> --kind build-wave --summary "<what this wave did>" [--model <model>] [--effort <effort>] --file <handoff.json> --file <checks.txt>`, repeating `--file` for every piece of evidence you hold. Pass optional `--model` and `--effort` flags extracted from the integrator's handoff record or dispatch brief. Take `<nth-accepted>` from the store, never from memory and never from `currentWave`, which repeats whenever a deferred or bounced issue comes back: `record` refuses an id it already wrote, so read the ids already logged in the namespace `status` printed and use the next unused number, or a resume on the same day drops the trace the wave was meant to keep. `build` records that raw evidence only and never consolidates it — turning traces into pages is the `wiki` skill's job, run outside this loop. A record that fails or is skipped never blocks, gates, or delays the merge, which is gated on exactly what it was before: combined GREEN, plus `tdd-guard status --json` fresh for every issue, plus `gh pr checks` passing.

   **Speculative specifiers.** While the integrator runs the combined suite, you may dispatch `specifier` agents for issues that are not unblocked yet — the ones that become ready once the in-flight set merges. Each runs the standard Phase 1 unrelaxed: it writes the issue's `acceptanceTests` as real failing tests on the current base, proves honest RED, and seals them. Speculation is opportunistic and never the default; the plain sequence stays correct, and a run that skips speculation is not deficient.

   - **Disqualifier.** An issue whose acceptance tests need the dependency's merged code to import or compile is disqualified from speculation. A test that cannot express its failure on the current base produces a hollow RED, so the `specifier` returns `blocked` rather than sealing one.
   - **Bounce cost.** When a wave bounces — the integrator names an offending PR, a builder redoes work, or the merged base changes what the tests assume — the speculative seal has to be re-proved on the merged base and amended with `tdd-guard reseal --reason <text>`, and a re-scoped issue throws that specifier's work away entirely. The guard binds a seal to the sealed test files and the red command, not to the base it was proved on, so nothing mechanical catches a stale speculative seal: the discipline is textual and lives here.
   - **Never a speculative builder.** Phase 2 for a speculated issue starts only after its dependencies are merged, in a workspace on the merged base, where the builder re-proves that the sealed tests still fail for the right reason before implementing. If they now pass, or fail differently, send the issue back to a `specifier` to reseal.

6. Merge only after combined green, then refresh GitHub state, advance, and repeat until no planned issue remains. In default mode, fast-forward or merge onto `main`; in single-PR mode, wave commits advance on `<planId>-integration`. Only the final milestone integration PR targeting main is pushed to GitHub and triggers remote CI.

You are the sole completion authority. Never force-push `main`, never merge before combined GREEN, and never infer completion from an agent's report — read the gates.

## Single-PR mode

Entry skills that promise one PR opt into this mode; the default multi-PR mode above is unchanged.

1. Before the first wave, create an integration branch from `trunk()` named `<planId>-integration`:

   ```bash
   jj bookmark create <planId>-integration -r trunk()
   ```

2. In every dispatch brief defined by [`agents/handoff.md`](../../runtime/handoff.md), pass that branch as the `base` field. Intermediate PR creation is eliminated: builders commit locally in isolated jj workspaces via `jj describe -m "..."` and hand off their local `changeId` without pushing intermediate branches or opening intermediate PRs.
3. After each wave, the integrator uses `jj rebase -s <changeId> -d <planId>-integration` to instantly combine wave changes onto the integration trunk in 50ms with zero network roundtrips, and runs the full project test suite (`scripts/run-tests.sh` + linters) ONCE on the combined wave state. On combined GREEN, advance the integration branch.
4. When no planned issue remains, open the **final PR from the integration branch to `main`**. Repeat every `Closes #<n>` line from the planned issues in the final PR body, because GitHub auto-closes issues only when a PR merges to the default branch. Only the final milestone integration PR targeting main is pushed to GitHub and triggers remote CI.

## Offline demonstration

These commands read fixtures only; they never call or change GitHub. The first is the shipped wave demo — one finished wave, two independent issues dispatchable, nothing deferred:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 skills/build/scripts/waves.py skills/build/examples/plan.sidecar.json skills/build/examples/issue-state.json
```

The second shows dependency-gated selection at work: a later-wave issue pulled forward past an unfinished straggler, and a ready candidate deferred because its coarse hint collides with one already selected:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 skills/build/scripts/waves.py skills/build/examples/pull-forward/plan.sidecar.json skills/build/examples/pull-forward/issue-state.json
```

## Harness Limitations

API-only model controls (such as dynamic request-level reasoning effort or pro mode toggles) and API-only orchestration features are unsupported in Codex skill prompts; execution relies on native harness tooling and specialist dispatch.
