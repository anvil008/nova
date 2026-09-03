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

## Wave Loop

1. **Snapshot and schedule.** Validate `plan.sidecar.json` and capture GitHub issue state. Run `skills/build/scripts/waves.py` to calculate candidates. An issue is done when closed and either labelled `status:done` or `state_reason == completed`. An issue is unblocked only when every dependency is done.

   Capture the snapshot with `REPO` and `MILESTONE` exported:

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

2. **Check ownership and isolate.** Check `ownershipHint` globs across the unblocked candidate set. Independent issues run concurrently, each in an isolated working copy via `workcell-ws add <key> --base <base>` ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). Overlapping candidates are deferred to subsequent rounds.

3. **Two-phase dispatch per issue.**
   - **Phase 1 — `specifier`**: Dispatch via `spawn_agent`. The specifier creates the workspace and branch, writes the issue's acceptance tests, proves honest RED, and runs `tdd-guard seal`. If it returns `blocked`, escalate to the human or planner.
   - **Phase 2 — `builder`**: Dispatch via `spawn_agent` only after the seal exists. The builder enters the workspace, implements the fix or feature against sealed tests, verifies GREEN with `tdd-guard verify --green-command`, conducts self-reviews, and opens the PR. The builder cannot edit sealed tests.

4. **Self-review and collection.** Collect each branch, PR, changed files, command-linked test evidence, and review pass records. Builders review their own change-set before opening a PR and tear down their workspace.

5. **Wave integration.** Dispatch an `integrator` via `spawn_agent` to build the combined wave state and execute the full test suite. Accept the wave based on mechanical evidence: combined GREEN commands, fresh `tdd-guard status --json`, and passing CI checks.

6. **Merge and advance.** Merge verified PRs, refresh GitHub state, and advance to the next dependency wave until all issues are completed.

## Single-PR Mode

Entry skills that promise one PR opt into single-PR mode:
1. Create an integration branch from `trunk()` named `<planId>-integration`:
   ```bash
   jj bookmark create <planId>-integration -r trunk()
   ```
2. Pass `<planId>-integration` as the `base` in every dispatch brief conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). Builders open PRs against `<planId>-integration`, never `main`.
3. The `integrator` verifies combined waves on the integration branch.
4. When all issues finish, open the final PR from `<planId>-integration` to `main`, repeating all `Closes #<n>` markers.

## Offline Demonstration

Run the dry-run demonstration using local fixtures:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 skills/build/scripts/waves.py skills/build/examples/plan.sidecar.json skills/build/examples/issue-state.json
```

## Harness Limitations

API-only model controls (such as dynamic request-level reasoning effort or pro mode toggles) and API-only orchestration features are unsupported in Codex skill prompts; execution relies on native harness tooling and specialist dispatch.
