---
name: research
description: Investigate a research question across multiple areas with parallel read-only researcher agents, then merge their findings into one deduplicated evidence packet.
---

# Research

Investigate a goal across several areas at once and return one consolidated evidence packet.

Invocation: `/workcell:research`
Prompting Reference: [`docs/models/gemini-3.8-flash/prompting.md`](../../runtime/docs/models/gemini-3.8-flash/prompting.md)

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents via Antigravity's `invoke_subagent`, hold the human gates, run `git` / `jj` / `gh` and scripts via `run_command` for branch, merge, and issue-state operations, and read gate output and handoff records using the [`anvil.agent-handoff/v1`](../../runtime/handoff.md) schema. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator splits the goal into areas, dispatches one read-only `researcher` agent per area in parallel, and owns synthesis. Per the Gemini 3.8 Flash guide, place critical constraints first, demand evidence-based reporting without premature filtering, and retain all conflict positions.

## Critical Constraints

- **Goal:** Gather comprehensive, evidence-backed findings across distinct investigation domains into a unified report.
- **Constraints:** Researchers are strictly read-only and blind to other areas. Never drop conflicting evidence during merge.
- **Success Criteria:** Deduplicated findings merged deterministically, explicit conflict surfaces reported, and verified HTML report rendered.

## Ordered Gates

Execution proceeds through four strict, ordered gates:

1. **area briefs**: Decompose research goal into distinct, non-overlapping investigation areas with clear briefs.
2. **read-only evidence**: Spawn parallel read-only researcher agents, returning evidence envelopes without edits.
3. **deduplication**: Merge envelopes and eliminate duplicate findings via `merge_research.py`.
4. **packet**: Synthesize verified evidence, conflicts, and gaps into the final evidence packet and HTML report.

## Area Split and Fan-Out

Decompose the goal into genuinely distinct, real research areas — by subsystem, by source type (code / docs / runtime / prior-art), or by question. The fan-out count equals the number of real research areas, never a fixed N.

Spawn one read-only `researcher` agent per area in parallel via `invoke_subagent`. Each agent is blind to the others and is confined to exactly one area. Agents never edit; they return a strict findings envelope.

## Merge, Conflicts, and Coverage

Collect the per-area envelopes and merge them without dropping evidence:

1. Deduplicate findings by `(area, source, finding)`; group the survivors by area.
2. Surface conflicts: a finding may carry an optional `stance` of `supports`, `contradicts`, or `neutral` (the default) toward its `topic`. A topic is a conflict only when at least one of its findings is `contradicts`; distinct wording of a position is not disagreement. Report the conflict with every position on that topic without dropping any finding.
3. Assess coverage: report any declared area with no report as a missing area, roll up each area's gaps and open questions, and mark the packet incomplete when an area is missing.

`skills/research/scripts/merge_research.py` performs this deterministically over captured per-area fixtures:

```bash
python3 -B skills/research/scripts/merge_research.py skills/research/examples/areas.json skills/research/examples/code.json skills/research/examples/docs.json skills/research/examples/runtime.json
```

## Report

Return the consolidated packet: per-area findings with evidence, the conflicts, the coverage summary, the gaps, and the open questions. The orchestrator owns synthesis and decides what the evidence means — deciding is orchestration; gathering is not.

When a shareable report is wanted, write the synthesis as JSON — `{"verdict": "clean|advisory|action-needed", "summary": "...", "recommendations": [{"priority": "high|medium|low", "title", "detail", "refs": ["F1-01"]}]}` — where each `ref` is a finding id (`F<area index>-<finding index>`) from the packet, and render both into a self-contained HTML page in the shared Foundry Zero report style (`docs/research/research<NN>-<YYYYMMDD>-<title>.html`):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B skills/research/scripts/render_research.py packet.json docs/research/research01-20260101-sample.html --synthesis synthesis.json --title "Sample" --repo owner/name --subject "what was researched"
```

The renderer rejects a recommendation that cites an unknown finding and a `clean` verdict that carries recommendations. Maintainers follow the [report-rendering contract](references/report-rendering.md).

## Procedure

1. **Formulate area briefs.** Define the research objective and divide it into clear, orthogonal areas.
2. **Dispatch blind researchers.** Run one read-only researcher per area in parallel using `invoke_subagent`.
3. **Merge and deduplicate.** Merge envelope outputs via `merge_research.py` without dropping conflicting stances.
4. **Synthesize report.** Generate the final evidence packet and render the HTML report via `render_research.py` with `--synthesis`, `--title`, `--repo`, and `--subject` flags.

## Boundaries

Researchers never edit repository code. The orchestrator synthesizes findings but never invents findings not present in the agent envelopes.

## Offline Demonstration

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B skills/research/scripts/merge_research.py skills/research/examples/areas.json skills/research/examples/code.json skills/research/examples/docs.json skills/research/examples/runtime.json
```

Based on the requirements and constraints above, execute the research workflow systematically.
