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

## Plan workflow

1. **Dispatch the `planner` agent** via `invoke_subagent` with the goal and any decisions the human has already made. It investigates read-only, defines the architecture delta and dependency-ordered issues, authors each issue's `acceptanceTests`, writes the strict sidecar, renders the folio, and runs the read-only reconciliation preview:

   ```bash
   python3 skills/plan/scripts/render_plan.py plan.sidecar.json
   python3 skills/plan/scripts/render_plan.py plan.sidecar.json --plans-dir docs/plans
   ```

   Omit the output path to get the `docs/plans/` naming convention; pass one explicitly only for a scratch render nobody intends to keep.

   Reviewing the folio, treat a coarse `ownershipHint` as a reason to send the plan back: each issue owns [exactly one narrow path or glob](references/sidecar-contract.md), disjoint from its wave-mates, or the wave's parallelism is lost.

   The plan also assigns each issue its **branch type**, carried as a `type:feature` or `type:bug` label in the sidecar: new behaviour is `type:feature`, a defect being repaired is `type:bug`, and [`build`](../build/SKILL.md) branches the issue as `<type>/<issue-key>` from it ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). An issue with no such label is built as `feature/`.

2. **Resolve open questions with the human before writing the plan.** Carry them yourself — the agent cannot. An agent that returns disposition `needs-decision` found something material undecided — scope boundaries, a choice between two approaches, an unowned dependency, an ambiguous requirement. Put the question to the human, wait for the answer, and re-dispatch the agent with it. Never answer on the human's behalf, and never let an unanswered question through: a plan carrying one is not ready for approval, and the sidecar has nowhere to put it by design.
3. Present the HTML folio for review. You **must stop** here for explicit human approval. Approval to plan is not approval to write GitHub resources.
4. Before approval, a read-only reconciliation preview is allowed — the agent runs one, and you may run another against a captured snapshot:

   ```bash
   python3 skills/plan/scripts/reconcile_github.py plan.sidecar.json --snapshot github-state.json
   python3 skills/plan/scripts/reconcile_github.py plan.sidecar.json
   ```

5. **Only after the human approves the reviewed artifacts**, apply the exact approved sidecar yourself with an approval identity via `run_command`. This write is the orchestrator's, never the agent's:

   ```bash
   python3 -B skills/plan/scripts/reconcile_github.py plan.sidecar.json --apply --approved-by "<github-login>"
   ```

   `--approved-by` must equal the login `gh` is authenticated as (`gh api user`). Apply output records that login as `approvedBy` and the exact approved sidecar bytes as `approvedSha256`.

Do not infer approval from silence, prior approval of another revision, or a request to investigate. If the sidecar changes after approval, present the changed plan and stop for fresh human approval.

## GitHub reconciliation

Use milestones only; never create or modify a GitHub Project. The reconciliation identity, done-state rules, and exact `gh` command shapes are part of the [sidecar contract](references/sidecar-contract.md).

Never run `--apply` merely to test the skill. Use snapshot preview and local rendering for validation.

## Boundaries

Never start execution on an unapproved plan. If changes are requested, re-render the folio and seek fresh approval. Never encode an unresolved decision into the plan.

## Offline Demonstration

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B skills/plan/scripts/render_plan.py skills/plan/examples/plan.sidecar.json /tmp/plan.html
```

Based on the requirements and constraints above, execute the plan workflow systematically.
