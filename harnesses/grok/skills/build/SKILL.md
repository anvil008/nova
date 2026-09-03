---
name: build
description: Execute an approved planner milestone as resumable dependency waves — a specifier agent seals each issue's failing tests, an isolated builder implements against them, and an integrator verifies each wave.
---

# Build

Execute one approved milestone plan. Inputs are its plan name, GitHub issues, and `plan.sidecar.json`. The sidecar supplies stable `key`, `dependsOn`, `ownershipHint`, `wave`, and the durable planner marker. GitHub is the source of truth for issue state; resume by reading it again and re-deriving the current wave.

Invocation: `/workcell:build`
Prompting Reference: [`docs/models/grok-4.6/prompting.md`](../../runtime/docs/models/grok-4.6/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_subagent` (running in foreground or with `background: true` tracked via `get_command_or_subagent_output`, or coordinated via `/workflow`), hold human gates, run workspace isolation and VCS operations using shell execution, and exchange handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code, run its test suites, or author its artifacts directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Drive an approved planner milestone to completion across resumable dependency waves with strict test-driven development discipline.
- **Constraints and Boundaries:** Never dispatch a builder without a sealed failing test. Never modify sealed tests during implementation. Never merge before combined GREEN evidence. Never commit directly to `main`. Never edit test files as a builder.
- **Success Criteria:** Every milestone issue completed against sealed acceptance tests, verified through clean review passes and green integration runs.

## Ordered Gates

Execution proceeds through five strict, ordered gates:

1. **approved plan**: Validate `plan.sidecar.json` and snapshot GitHub issue state to schedule dependency waves.
2. **specifier RED seal**: Specifier authors failing acceptance tests and seals them with `tdd-guard seal`.
3. **builder GREEN**: Builder implements against sealed tests, verifies green, and conducts self-reviews.
4. **review passes**: Builder completes self-review passes or multi-lens reviewer passes without unaddressed blockers.
5. **integration**: Integrator verifies combined wave state with command-linked test evidence on an integration ref.

## Input and Output Contracts

Subagent dispatch uses native Grok `spawn_subagent` (with `background: true` for parallel tasks, polled via `get_command_or_subagent_output`) or multi-step `/workflow` routines. Each dispatch exchanges structured handoff payloads conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md).

- **Wave Scheduling Inputs and Outputs:**
  - **Inputs:** `plan.sidecar.json`, captured `issue-state.json`, and repository milestone context.
  - **Outputs:** Dependency wave schedule identifying unblocked, in-flight, and deferred candidate issues.
- **Specifier Inputs and Outputs:**
  - **Inputs:** Issue key, description, acceptance tests, base branch/commit, and workspace path.
  - **Outputs:** Sealed failing acceptance test suite with `tdd-guard seal` evidence and honest RED run confirmation.
- **Builder Inputs and Outputs:**
  - **Inputs:** Issue assignment, sealed test manifest, isolated workspace path, and assigned base.
  - **Outputs:** Verified passing implementation, `tdd-guard verify` GREEN evidence, two diff-review passes recorded via `tdd-guard diff-review record`, and opened pull request.
- **Reviewer Inputs and Outputs:**
  - **Inputs:** Issue diff, target workspace, and assurance lenses (`correctness`, `tests`, `security`, `performance`).
  - **Outputs:** Structured review findings and verification verdicts.
- **Integrator Inputs and Outputs:**
  - **Inputs:** Wave pull request list, target integration bookmark, and combined test commands.
  - **Outputs:** Combined build and test execution evidence, gate validation logs, and merge readiness verdict.

## Wave Loop

1. **Snapshot and schedule.** Validate `plan.sidecar.json` and capture GitHub issue state. Run `skills/build/scripts/waves.py` to calculate candidates. GitHub is the source of truth for issue state; resume by reading it again and re-deriving the current wave. An issue is done when closed and either labelled `status:done` or `state_reason == completed`. An issue is unblocked only when every dependency is done.

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

2. **Check ownership and isolate.** Check `ownershipHint` globs across the unblocked candidate set. Independent issues run concurrently, each in an isolated jj workspace via `workcell-ws add <key> --base <base>` ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). Overlapping candidates are deferred to subsequent rounds.

3. **Two-phase dispatch per issue.**
   - **Phase 1 — `specifier`**: Dispatch via `spawn_subagent` (or `/workflow`). The specifier creates the workspace and branch, writes the issue's acceptance tests, proves honest RED, and runs `tdd-guard seal`. If it returns `blocked`, escalate to the human or planner.
   - **Phase 2 — `builder`**: Dispatch via `spawn_subagent` only after the seal exists. The builder enters the workspace, implements the fix or feature against sealed tests, verifies GREEN with `tdd-guard verify --green-command`, conducts self-reviews, and opens the PR. Never edit test files as a builder.

4. **Self-review and collection.** Collect each branch, PR, changed files, command-linked test evidence, and review pass records. Builders review their own change-set before opening a PR and tear down their workspace. Stranded workspaces are inspected with `workcell-ws list` or `jj workspace list` and reclaimed with `workcell-ws forget <name>`.

5. **Wave integration.** Dispatch an `integrator` via `spawn_subagent` to build the combined wave state and execute the full test suite. Accept the wave based on mechanical evidence: combined GREEN commands, fresh `tdd-guard status --json`, and passing CI checks. You are the sole completion authority. Never force-push `main`, never merge before combined GREEN, and never infer completion from an agent's report.

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

Skill frontmatter fields `allowed-tools`, `model`, `effort`, `license`, and `compatibility` are unsupported for capability enforcement or routing under Grok Build; execution relies on native CLI flags (`--tools`, `--disallowed-tools`), agent definitions, capability modes, and specialist dispatch. API-only model controls and programmatic tool calling are unsupported in skill prompts.
