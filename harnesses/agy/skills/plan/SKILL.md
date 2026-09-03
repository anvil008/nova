---
name: plan
description: Investigate a repository task and produce an offline HTML implementation plan plus a strict JSON sidecar, then—only after explicit human approval—idempotently reconcile the plan into a GitHub milestone and issues. Use for substantial coding work that should be reviewed before GitHub tracking is created; do not use for direct implementation or GitHub Projects.
---

# Planner

Turn a repository change into an evidence-backed, reviewable plan.

Invocation: `/workcell:plan`
Prompting Reference: [`docs/models/gemini-3.7-flash/prompting.md`](../../runtime/docs/models/gemini-3.7-flash/prompting.md)

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents via Antigravity's `invoke_subagent`, hold the human gates, run `git` / `jj` / `gh` and scripts via `run_command` for branch, merge, and issue-state operations, and read gate output and handoff records using the [`anvil.agent-handoff/v1`](../../runtime/handoff.md) schema. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator dispatches the planner agent, relays open questions to the human, holds approval, and applies the approved plan to GitHub. Per the Gemini 3.7 Flash guide, place critical constraints first, demand explicit human sign-offs, and ensure machine-readable precision.

## Critical Constraints

- **Goal:** Transform a complex feature, refactor, or overhaul into an evidence-backed HTML folio, strict JSON sidecar, and idempotent GitHub tracking.
- **Constraints:** Stop for explicit human approval before running `--apply`; never infer approval. Each planned issue must have disjoint `ownershipHint` globs. Use milestones only; never create or modify a GitHub Project.
- **Success Criteria:** Verified offline folio and sidecar, explicit human sign-off, and idempotent reconciliation into GitHub milestone and issues.

### Antigravity Teamwork (Optional Surface)

Antigravity Teamwork is an optional orchestration surface available in paid subscription tiers and the interactive web interface. In headless environments (such as CLI / eval mode), fall back to standard subagent orchestration via `invoke_subagent`. Teamwork is optional and never required.

## Ordered Gates

Execution proceeds through five strict, ordered gates:

1. **investigation**: Planner investigates repository read-only to identify architecture delta and issues.
2. **offline folio**: Generate self-contained HTML implementation plan with `render_plan.py`.
3. **strict sidecar**: Produce machine-readable `plan.sidecar.json` with narrow disjoint ownership hints.
4. **human approval**: Stop and present HTML folio for explicit human approval before any external writes.
5. **GitHub reconciliation**: Reconcile approved plan idempotently into GitHub milestone and issues via `reconcile_github.py`.

The planner agent follows the [artifact and sidecar contract](references/sidecar-contract.md). Renderer maintainers follow the [report-rendering contract](references/report-rendering.md).

## Procedure

1. **Dispatch planner.** Dispatch the `planner` agent via `invoke_subagent` with the objective. It inspects the codebase read-only, authors dependency-ordered issues with disjoint `ownershipHint` globs and `acceptanceTests`, writes the sidecar, and renders the offline HTML folio using `render_plan.py`.
2. **Resolve open questions with the human before writing the plan.** If the planner returns `needs-decision`, present the question directly to the human, obtain their answer, and re-dispatch. Never guess answers.
3. **Present folio.** Present the generated HTML plan folio to the user. You must stop here for explicit human approval. Approval to plan is not approval to write GitHub resources.
4. **Reconciliation preview.** Prior to approval, preview GitHub reconciliation idempotently:
   ```bash
   python3 -B skills/plan/scripts/reconcile_github.py plan.sidecar.json
   ```
5. **Reconcile to GitHub milestone.** Only after explicit human approval, apply the sidecar with the approver login:
   ```bash
   python3 -B skills/plan/scripts/reconcile_github.py plan.sidecar.json --apply --approved-by "<github-login>"
   ```
   Use milestones only; never create or modify a GitHub Project. Never run `--apply` merely to test the skill.

## Boundaries

Never start execution on an unapproved plan. If changes are requested, re-render the folio and seek fresh approval.

Based on the requirements and constraints above, execute the plan workflow systematically.
