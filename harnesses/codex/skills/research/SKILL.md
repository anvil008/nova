---
name: research
description: Investigate a research question across multiple areas with parallel read-only researcher agents, then merge their findings into one deduplicated evidence packet.
---

<!-- generated harness-owned procedure: Codex -->

# Research

Investigate a goal across several areas at once and return one consolidated evidence packet.

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents, hold the human gates, run `git` / `jj` / `gh` for branch, merge, and issue-state operations, and read gate output and handoff records. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator splits the goal into areas, dispatches one read-only `researcher` agent per area, and owns the synthesis and conclusion.

## Area split and fan-out

Decompose the goal into genuinely distinct, real research areas — by subsystem, by source type (code / docs / runtime / prior-art), or by question. The fan-out count equals the number of real areas, never a fixed N.

Spawn one read-only `researcher` agent per area, in parallel. Each agent is blind to the others and is confined to exactly one area. Agents never edit; they return a strict findings envelope.

## Merge, conflicts, and coverage

Collect the per-area envelopes and merge them without dropping evidence:

1. Deduplicate findings by `(area, source, finding)`; group the survivors by area.
2. Surface conflicts: a finding may carry an optional `stance` of `supports`, `contradicts`, or `neutral` (the default) toward its `topic`. A topic is a conflict only when at least one of its findings is `contradicts`; distinct wording of a `position` is not disagreement. Report the conflict with every position on that topic **without dropping** any finding.
3. Assess coverage: report any declared area with no report as a missing area, roll up each area's gaps and open questions, and mark the packet incomplete when an area is missing.

`skills/research/scripts/merge_research.py` performs this deterministically over captured per-area fixtures:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B skills/research/scripts/merge_research.py skills/research/examples/areas.json skills/research/examples/code.json skills/research/examples/docs.json skills/research/examples/runtime.json
```

## Report

Return the consolidated packet: per-area findings with evidence, the conflicts, the coverage summary, the gaps, and the open questions. The orchestrator owns synthesis and decides what the evidence means — deciding is orchestration; gathering is not.

When a shareable report is wanted, write the synthesis as JSON — `{"verdict": "clean|advisory|action-needed", "summary": "...", "recommendations": [{"priority": "high|medium|low", "title", "detail", "refs": ["F1-01"]}]}` — where each `ref` is a finding id (`F<area index>-<finding index>`) from the packet, and render both into a self-contained HTML page in the shared Foundry Zero report style (`docs/research/research<NN>-<YYYYMMDD>-<title>.html`):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B skills/research/scripts/render_research.py packet.json docs/research/research01-20260101-sample.html --synthesis synthesis.json --title "Sample" --repo owner/name --subject "what was researched"
```

The renderer rejects a recommendation that cites an unknown finding and a `clean` verdict that carries recommendations. Maintainers follow the [report-rendering contract](references/report-rendering.md).
