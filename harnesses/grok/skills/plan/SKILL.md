---
name: plan
description: Investigate a repository task and produce an offline HTML implementation plan plus a strict JSON sidecar, then—only after explicit human approval—idempotently reconcile the plan into a GitHub milestone and issues. Use for substantial coding work that should be reviewed before GitHub tracking is created; do not use for direct implementation or GitHub Projects.
---

# Planner

Turn a repository change into an evidence-backed, reviewable plan.

Invocation: `/workcell:plan`
Prompting Reference: [`docs/models/grok-4.6/prompting.md`](../../runtime/docs/models/grok-4.6/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_subagent` (running in foreground or with `background: true` tracked via `get_command_or_subagent_output`, or coordinated via `/workflow`), hold human gates, run VCS and issue-state operations using shell execution, and read gate evidence and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Transform a complex feature, refactor, or overhaul into an evidence-backed HTML folio, strict JSON sidecar, and idempotent GitHub tracking.
- **Constraints and Boundaries:** Stop for explicit human approval before running `--apply`; never infer approval. Each planned issue must have disjoint `ownershipHint` globs. Milestones only; never touch GitHub Projects.
- **Success Criteria:** Verified offline folio and sidecar, explicit human sign-off, and idempotent reconciliation into GitHub milestone and issues.

## Ordered Gates

Execution proceeds through five strict, ordered gates:

1. **investigation**: Planner investigates repository read-only to identify architecture delta and issues.
2. **offline folio**: Generate self-contained HTML implementation plan with `render_plan.py`.
3. **strict sidecar**: Produce machine-readable `plan.sidecar.json` with narrow disjoint ownership hints.
4. **human approval**: Stop and present HTML folio for explicit human approval before any external writes.
5. **GitHub reconciliation**: Reconcile approved plan idempotently into GitHub milestone and issues via `reconcile_github.py`.

## Input and Output Contracts

Subagent dispatch uses native Grok `spawn_subagent` (with `background: true` for parallel tasks, polled via `get_command_or_subagent_output`) or multi-step `/workflow` routines. Each dispatch exchanges structured handoff payloads conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md).

- **Planner Investigation Inputs and Outputs:**
  - **Inputs:** Feature or architectural change goal, constraints, and read-only repository context.
  - **Outputs:** Architectural gap analysis, dependency-ordered milestones, and strict `plan.sidecar.json`.
- **Folio Renderer Inputs and Outputs:**
  - **Inputs:** `plan.sidecar.json` and destination path.
  - **Outputs:** Self-contained visual HTML plan folio with embedded diagrams and issue breakdown.
- **GitHub Reconciler Inputs and Outputs:**
  - **Inputs:** Approved `plan.sidecar.json`, target repository name, and human sign-off login.
  - **Outputs:** Idempotently created or updated GitHub milestone and issue URLs.

## Plan workflow

1. **Investigation.** Dispatch a `planner` via `spawn_subagent` with the target goal and human requirements. The planner investigates the repository read-only, determines architecture deltas, specifies dependency-ordered issues with disjoint `ownershipHint` globs, and writes `plan.sidecar.json` conforming to [`references/sidecar-contract.md`](references/sidecar-contract.md).
2. **Offline folio rendering.** Render the HTML plan folio:

   ```bash
   python3 skills/plan/scripts/render_plan.py plan.sidecar.json --plans-dir docs/plans
   ```

   Renderer contracts conform to [`references/report-rendering.md`](references/report-rendering.md).

3. **Reconciliation preview.** Run a read-only reconciliation preview:

   ```bash
   python3 skills/plan/scripts/reconcile_github.py plan.sidecar.json --snapshot github-state.json
   ```

4. **Human approval checkpoint.** Present the HTML plan folio to the user and stop execution. Explicit human approval is required before writing any GitHub resources.
5. **Idempotent GitHub reconciliation.** After approval, apply the sidecar:

   ```bash
   python3 skills/plan/scripts/reconcile_github.py plan.sidecar.json --apply --approved-by "<login>"
   ```

   `--approved-by` must equal the login `gh` is authenticated as (`gh api user`). Apply output records that login as `approvedBy` and the exact approved sidecar bytes as `approvedSha256`.

   Do not infer approval from silence, prior approval of another revision, or a request to investigate. If the sidecar changes after approval, present the changed plan and stop for fresh human approval.

## GitHub reconciliation

Use milestones only; never create or modify a GitHub Project. The reconciliation identity, done-state rules, and exact `gh` command shapes are part of the [`references/sidecar-contract.md`](references/sidecar-contract.md).

Never run `--apply` merely to test the skill. Use snapshot preview and local rendering for validation.

## Offline Demonstration

```bash
PYTHONDONTWRITEBYTECODE=1 python3 skills/plan/scripts/render_plan.py skills/plan/examples/plan.sidecar.json /tmp/plan.html
```

## Harness Limitations

Skill frontmatter fields `allowed-tools`, `model`, `effort`, `license`, and `compatibility` are unsupported for capability enforcement or routing under Grok Build; execution relies on native CLI flags (`--tools`, `--disallowed-tools`), agent definitions, capability modes, and specialist dispatch. API-only model controls and programmatic tool calling are unsupported in skill prompts.
