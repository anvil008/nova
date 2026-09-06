---
name: plan
description: Develop a repository change plan before execution. Ask whether the user wants one plan or multiple plan ideas, delegate authorship and supporting research, and return a reviewed Markdown plan with a strict sidecar for substantial work. Add HTML only when requested; hand the accepted plan to build when authorized.
---

# Plan

Invocation: `/workcell:plan`
Prompting Reference: [`docs/models/gpt-6-astra/prompting.md`](../../runtime/docs/models/gpt-6-astra/prompting.md)

Dispatch planner agents with Codex's native `spawn_agent` tool, applying configured role models and reasoning effort. Use the available agent lifecycle and messaging tools for follow-ups. Planner-owned researchers use native nested dispatch where available; otherwise route their assignments and evidence through the orchestrator. Use `agents/models.json` and [`anvil.agent-handoff/v1`](../../runtime/handoff.md).

Turn a repository change into a reviewable plan. The orchestrator frames the goal, carries user decisions, chooses the team, compares proposals, and judges the result. Planner agents own investigation, research direction, and plan authorship ([ADR 0029](../../runtime/docs/adr/0029-composable-workflows-and-native-research.md)).

Follow the [planning choice and resume contract](references/planning-modes.md). Ask **one plan or multiple plan ideas** unless the request or saved choice already answers it. This chooses the output, not a prescribed number of agents. The orchestrator decides how many planners and researchers the work needs, using available capacity and any limits the user actually supplied.

Markdown is the default: **do not ask a format question**. An explicit visual/HTML request adds an HTML companion; an explicit Markdown-only request does not.

## Ordered Gates

1. **plan choice**: Reuse the request or saved choice; otherwise ask one plan versus multiple plan ideas.
2. **planner investigation**: The orchestrator chooses the team; planners direct research and author the proposed approaches.
3. **plan artifacts**: Produce Markdown and the applicable strict sidecar; add HTML only when requested.
4. **orchestrator review**: Compare proposals, assign coherent final plan authorship, and accept, revise, or raise a material user decision.
5. **build transition**: Present artifacts, then ask a standalone planning user about build or continue under an existing plan-and-implement request.

## Workflow

1. **Frame and delegate.** Supply the goal, non-goals, constraints, user decisions, pinned source, relevant paths, output ownership, planning choice, and review criteria. For multiple ideas, give planners distinct design directions and common constraints. Planner-owned research uses the [evidence contract](references/research.md); the standalone research skill is retired. Use the actual harness delegation capability, with orchestrator dispatch on the planner's behalf where nested delegation is unavailable.
2. **Collect proposals and evidence.** Planners return source-backed approaches, tradeoffs, and gaps. Reuse shared evidence instead of repeating the same investigation for every proposal. For multiple ideas, the orchestrator compares them, explains its recommendation or combination, and sends material user decisions through the human. Assign a planner to author the coherent final plan from that decision.
3. **Review the executable plan.** Follow the [artifact and sidecar contract](references/sidecar-contract.md). Substantial plans include a strict sidecar and Markdown report; a concise task brief needs no synthetic milestone or multi-issue sidecar. Check requirements, evidence, feasibility, dependencies, narrow ownership, risks, and observable acceptance criteria. The planner authors test specifications, never runnable tests. Accept the result, return concrete revisions, or surface a material unresolved decision. Resolve material open questions before finalizing the plan. A polished report is not verification evidence.
4. **Present artifacts and transition.** Link the reviewed Markdown and requested HTML. For standalone `/plan`, ask whether to proceed to `/build` after the artifacts are ready. If the user already requested planning and implementation, continue to build without asking again. Carry the existing plan, source revision, evidence, decisions, and authorization into build; do not restart planning. Plan acceptance alone does not authorize external writes or deployment.

The planner renders substantial plans using:

```bash
python3 skills/plan/scripts/render_plan.py plan.sidecar.json
python3 skills/plan/scripts/render_plan.py plan.sidecar.json --format html
```

The first command writes Markdown. The second writes Markdown and HTML with the same stable plan number. Use `--plans-dir` for an alternate directory. Renderer maintainers follow the [report-rendering contract](references/report-rendering.md).

## Optional GitHub reconciliation

Local plans use `repo: null` and need no GitHub resources. Use milestones only; never create or modify a GitHub Project. Tracking uses a GitHub milestone. When tracking is requested, preview the exact sidecar read-only, using a captured snapshot when available:

```bash
python3 skills/plan/scripts/reconcile_github.py plan.sidecar.json --snapshot github-state.json
python3 skills/plan/scripts/reconcile_github.py plan.sidecar.json
```

The orchestrator alone applies the reviewed sidecar after explicit human approval of that write:

```bash
python3 skills/plan/scripts/reconcile_github.py plan.sidecar.json --apply --approved-by "<github-login>"
```

`--approved-by` must match `gh api user`; the receipt records that login and the exact sidecar digest. Planning approval does not by itself authorize GitHub resources. You must stop before an unapproved write. If the approved sidecar changes, present it for fresh approval before applying. Never run `--apply` to test the skill.
