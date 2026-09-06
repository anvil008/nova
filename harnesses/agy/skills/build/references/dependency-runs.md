# Dependency runs

Use this protocol for a task graph that needs resumable local integration. It is an internal mode of `/build`, with the same verification contract as a single change. Read the [shared build workflow](../SKILL.md) first.

## Wave loop

1. Validate the sidecar and use the saved tracking mode. In GitHub mode, capture fresh GitHub issue state. In local mode, use `build_run.py select --local`; it creates no issue or remote completion claim, returns `number: null`, and uses accepted receipts for completion. External dependencies require an actual GitHub snapshot; local mode fails closed if a dependency key is outside the plan. Never switch a run from GitHub tracking to local mode merely to ignore an unresolved remote dependency. Remote completion means closed **and** (`status:done` or `state_reason == completed`); a `not_planned` closure without that label is housekeeping. Local completion means an accepted receipt in `build_run.py` whose integration bookmark still matches the ledger. A locally integrated issue stays open until the final PR merges, but is excluded from dispatch and satisfies dependencies. The ledger binds the exact approved sidecar and repository identity; never infer local completion from an issue label or a builder's summary.

   Use `build_run.py select` for live resumable builds, with `--snapshot <path>` for GitHub tracking or `--local` for local task keys. `skills/build/scripts/waves.py` remains the offline preview, also supporting `--local`. Selection is dependency-gated regardless of declared wave: `currentWave` is the earliest unfinished declared wave for reporting the current wave, and a later candidate is pulled forward (`pulledForward: true`). Copy approved external `acceptanceTests[].testPath` values into `brief.testOwnership[]` for the specifier. The selector checks implementation hints and declared test paths and conservatively serializes uncertain glob intersections; it never declares independence from sampled filenames.

   For GitHub tracking, capture that snapshot with `REPO` and `MILESTONE` exported (`REPO=owner/repo`, `MILESTONE` the milestone title). It writes `{repo, milestone, issues:[{number, body, labels, state, state_reason}]}` and drops the pull requests the issues endpoint returns alongside issues. The milestone is filtered by title in `jq`, so `--paginate` is not optional — the `100` cap is over every milestoned issue in the repo, not over this milestone's — and `jq -s` is what flattens the one array per page `--paginate` emits into a single snapshot:

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
       }' > "$WORKCELL_RUN/issue-state.json"
   ```

   `waves.py` also accepts gh's raw label objects, so a snapshot captured any other way (`gh issue list --json labels`) validates unchanged.

2. Check ownership before dispatch, across the whole candidate in-flight set rather than per declared wave. Run one issue-pair per unblocked issue in parallel, each in its own **jj workspace**, only when `ownershipHint` globs are genuinely independent. `waves.py` does that check itself: a candidate whose hint overlaps an already-selected one is left out of `unblocked` and named in `deferred` with the `overlapsWith` key it collides with, and you dispatch it in a later round. Overlapping work is never dispatched concurrently. Candidates are considered earliest declared wave first, so a deliberately coarse late hint — a whole-repository documentation pass, say — defers itself rather than starving the issues it overlaps. A declared overlap inside a grouped wave (1 and up) is still rejected outright, because the planner asserted a parallelism the hints cannot deliver; wave 0 is the ungrouped bucket, so an overlap there is warned about rather than rejected, and the colliding candidate is held back by the same in-flight check as any other — the warning names a pair, the deferral is decided against the whole selected set, so which key ends up in `deferred` is `waves.py`'s answer, not the warning's.

   The orchestrator may dispatch any useful subset of `unblocked` for the available runtime capacity and explicit user limits; whatever you hold back simply returns as a candidate in a later round. Dispatch every issue in a round on the same base, pulled-forward issues included — they join the same integration round as the rest. Intermediate PR creation is eliminated: builders commit locally in isolated jj workspaces and never push intermediate branches or open pull requests. The base is the accepted `<planId>-integration` bookmark, initially created from `trunk()`. Handing a builder a sibling's bookmark or an unmerged head puts commits it did not write into its diff.

   Agents share one repo and isolate through one helper, `workcell-ws add <key>`, not through separate clones — one repo, one operation log, many working copies at the sibling path `../<repo>-<key>`. An assignment's branch is `<type>/<task-key>`, with the type coming from its selected verification intent and the planner's `type:feature` / `type:bug` label — `feature/` when there is none, `bug/` where the issue is a defect — and the directory writes that slash as a dash ([`docs/workspaces.md`](../../../runtime/docs/workspaces.md)). It runs `jj workspace add` where the repo is jj-managed and `git worktree add` where it is not, so the naming and the teardown are the same in either (`docs/workspaces.md`). This receipt helper requires Jujutsu. Establish any authorized adoption once before dispatch; do not race specifiers to convert a Git repository. When the user selected plain Git, keep it and execute ordered tasks through the single-change protocol with pinned bases and retained handoffs rather than silently converting the repository.

3. **Dispatch each issue in two phases, in order.** The separation is the point: the agent that defines "done" is not the agent judged against it.

   - **Phase 1 — `specifier`.** It creates the workspace and branch, writes the issue's `acceptanceTests` as real failing tests, proves honest RED, and runs `tdd-guard seal`. A `specifier` that returns `blocked` could not express an acceptance test as a runnable failing test — that is missing or invalid specification evidence; return it for a concrete correction. Do not dispatch the builder; take the unsealed entry back to the planner or the human.
   - **Phase 2 — `builder`.** Only after the seal exists. It enters the same workspace, implements against the sealed tests, and verifies the sealed acceptance tests via `tdd-guard verify --green-command ...` plus relevant targeted regression checks. Do not run broad discovery suites or additional whole-project test runners (`scripts/run-tests.sh`) in every builder; the integrator owns that check set. A baseline seal still requires its exact bound command even when that command is the full suite. Intermediate PR creation is eliminated: builders commit locally in isolated jj workspaces via `jj describe -m "..."`, hand off their local `changeId` and immutable `commitId`, and retain the workspace until acceptance. It cannot edit the sealed tests: the guard denies those edits outright.

   Never run the two phases concurrently, and never dispatch a builder for an issue with no seal — an unsealed builder is a builder grading its own homework.

   A **behaviour-preserving refactor or optimization** replaces the RED requirement with a GREEN one inside the same `tdd-guard` state machine. [`refactor`](../../refactor/SKILL.md) runs without a specifier. In that mode **you create the workspace and branch yourself** with `workcell-ws add refactor/<issue-key> --base <integration-base>` — the `refactor/` type says what the branch is for ([`docs/workspaces.md`](../../../runtime/docs/workspaces.md)) — then dispatch an `integrator` with `mode: baseline`, `workspace`, `sealedTests`, and `baselineCommand`. It returns green evidence plus a `kind: baseline` seal and hands that seal off; only then dispatch the `builder` with `mode: refactor`. The builder verifies GREEN after the seal and records the real diff as usual, so the Stop hook and `status --json` work unchanged.

4. Collect each branch, local `changeId`, immutable `commitId`, changed files, command-linked test evidence, runtime evidence (`evidence.runtime`), and independent review findings. Every critical or high finding must be resolved on the current source before acceptance. Review and repair stay inside this build. The orchestrator chooses follow-up assignments, reviewer lenses, and repetitions from the remaining findings, source changes, and demonstrated progress; no fixed pass count or redispatch maximum applies. Existing findings for unchanged source need no duplicate review. If a run is not making progress, change the approach, re-scope within authorization, or return the concrete unresolved decision; never claim acceptance because a retry count elapsed. A builder completes its assigned task and does not merge or declare the plan done.

   Retain every builder workspace through preparation and acceptance. If an agent dies, inspect `workcell-ws list` and `workcell-ws sweep` without `--apply`, reconcile the live agent and run receipt, and resume from the existing workspace. An unaccepted workspace is evidence, not garbage. Only the orchestrator, from the primary workspace, may run `workcell-ws forget <branch>` after its source is recorded in an accepted receipt. Keep candidate workspaces until acceptance too; retain failed candidates for diagnosis.

5. **Verify the combined candidate.** Dispatch an `integrator` with the run directory, handoff paths, a fresh candidate workspace path, and the project's required check argv arrays. It invokes `build_run.py prepare`. The helper uses `jj duplicate --onto` to apply each source to the preceding candidate and explicitly advances the candidate bookmark after every source. Original builder commits and workspaces remain unchanged. Repeating `jj rebase` onto a fixed bookmark would leave the siblings separate and does not implement this step.

   The helper checks fresh `tdd-guard status --json` in every source workspace, immutable handoff commits, actual changed-file ownership, and overlapping writes. It runs the full project test suite (`scripts/run-tests.sh` + linters) ONCE per unchanged combined wave state, records argv, command IDs, outputs, exit codes, and measured duration, and rejects a candidate changed by a check. Failure leaves the accepted integration bookmark untouched.

   Accept the wave on the **evidence**: inspect the prepared receipt's combined GREEN, current per-source gate output, runtime proof, and independent review outcomes. Then invoke `build_run.py accept --receipt <id>`. Only the orchestrator performs acceptance. The helper rechecks source and candidate commits before advancing `<planId>-integration` and recording local completion. Repeating acceptance after an interruption is idempotent. `gh pr checks` applies to the final remote PR, not local rounds. A prose claim of success from any agent is worth nothing. Return a failed issue to its builder and prepare a fresh combined candidate.

   **Record the accepted wave.** Only when `python3 -B skills/wiki/scripts/wiki.py status --repo .` reports the project's namespace as present do you record anything at all; that same call is what refuses a repository in eval mode, so no eval condition of your own belongs here, and a project with no namespace runs this loop exactly as it does today. Where it is present, write the integrator's handoff record and the gate output you accepted on into a `mktemp -d` scratch directory — never into the repository, so no diff gains a file — and pass those real paths to `python3 -B skills/wiki/scripts/wiki.py record --repo . --id <YYYY-MM-DD>-build-wave-<planId>-<nth-accepted> --kind build-wave --summary "<what this wave did>" [--model <model>] [--effort <effort>] --file <handoff.json> --file <checks.txt>`, repeating `--file` for every piece of evidence you hold. Pass optional `--model` and `--effort` flags extracted from the integrator's handoff record or dispatch brief. Take `<nth-accepted>` from the store, never from memory and never from `currentWave`, which repeats whenever a deferred or bounced issue comes back: `record` refuses an id it already wrote, so read the ids already logged in the namespace `status` printed and use the next unused number, or a resume on the same day drops the trace the wave was meant to keep. `build` records that raw evidence only and never consolidates it — turning traces into pages is the `wiki` skill's job, run outside this loop.

   A record that fails or is skipped never blocks, gates, or delays the merge, which is gated on exactly what it was before: combined GREEN, fresh per-issue guard evidence, and an accepted local receipt. The final remote PR additionally requires passing `gh pr checks`.

   **Speculative specifiers.** While the integrator runs the combined suite, you may dispatch `specifier` agents for issues that are not unblocked yet — the ones that become ready once the in-flight set merges. Each runs the standard Phase 1 unrelaxed: it writes the issue's `acceptanceTests` as real failing tests on the current base, proves honest RED, and seals them. Speculation is opportunistic and never the default; the plain sequence stays correct, and a run that skips speculation is not deficient.

   - **Disqualifier.** An issue whose acceptance tests need the dependency's merged code to import or compile is disqualified from speculation. A test that cannot express its failure on the current base produces a hollow RED, so the `specifier` returns `blocked` rather than sealing one.
   - **Bounce cost.** When a wave bounces — the integrator names an offending PR, a builder redoes work, or the merged base changes what the tests assume — the speculative seal has to be re-proved on the merged base and amended with `tdd-guard reseal --reason <text>`, and a re-scoped issue throws that specifier's work away entirely. The guard binds a seal to the sealed test files and the red command, not to the base it was proved on, so nothing mechanical catches a stale speculative seal: the discipline is textual and lives here.
   - **Never a speculative builder.** Phase 2 for a speculated issue starts only after its dependencies are merged, in a workspace on the merged base, where the builder re-proves that the sealed tests still fail for the right reason before implementing. If they now pass, or fail differently, send the issue back to a `specifier` to reseal.

6. After acceptance, refresh GitHub state when tracking remotely and select again using the ledger and the saved tracking mode. Continue until every planned issue is remotely complete or locally integrated. Local completion permits the next wave; milestone merge completion requires the final PR and its remote checks. Never fast-forward `main` as a substitute for the final PR.

You are the sole completion authority. Never force-push `main`, never merge before combined GREEN, and never infer completion from an agent's report — read the gates.

## Single-PR mode

All local wave builds use one final PR. Entry skills pass the integration bookmark as `base` in [`agents/handoff.md`](../../../runtime/handoff.md).

See [the executable run protocol](../../../runtime/docs/build-runs.md) for complete input examples and recovery. Initialize once, with a durable directory outside the repository (shown as `$WORKCELL_RUN`):

```bash
python3 skills/build/scripts/build_run.py init plan.sidecar.json --state "$WORKCELL_RUN" --repo .
python3 skills/build/scripts/build_run.py select plan.sidecar.json --state "$WORKCELL_RUN" --snapshot "$WORKCELL_RUN/issue-state.json"
```

For a plan without GitHub tracking, use `--local` instead of `--snapshot` and pass `issue: null` to the agents. The sidecar still contains stable task keys, acceptance criteria, and ownership; it does not need fabricated issue numbers. A purely local plan uses `repo: null` in its sidecar.

The integrator prepares; the orchestrator accepts the returned receipt ID:

```bash
python3 skills/build/scripts/build_run.py prepare plan.sidecar.json --state "$WORKCELL_RUN" --sources "$WORKCELL_RUN/sources.json" --checks "$WORKCELL_RUN/checks.json" --workspace ../wave-candidate
python3 skills/build/scripts/build_run.py accept plan.sidecar.json --state "$WORKCELL_RUN" --receipt <id>
```

When no planned task remains, continue the shared build's [finalization](finalization.md). Required documentation must be combined before final verification. If there are no separate docs and a PR is authorized, open the **final PR from the integration branch to `main`**. When `finalization.json` records a verified separate final branch, use that recorded branch and exact head instead; keep the accepted integration bookmark unchanged. Repeat every real `Closes #<n>` line from linked issues in the final PR body. Only this PR is pushed and triggers remote CI. Check `gh pr checks` before merging; GitHub closure then supplies the remote completion record for linked issues. Local-only task completion stays recorded in the accepted receipts.

## Offline demonstration

These commands read fixtures only; they never call or change GitHub. The first is the shipped wave demo — one finished wave, two independent issues dispatchable, nothing deferred:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 skills/build/scripts/waves.py skills/build/examples/plan.sidecar.json skills/build/examples/issue-state.json
```

The second shows dependency-gated selection at work: a later-wave issue pulled forward past an unfinished straggler, and a ready candidate deferred because its coarse hint collides with one already selected:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 skills/build/scripts/waves.py skills/build/examples/pull-forward/plan.sidecar.json skills/build/examples/pull-forward/issue-state.json
```
