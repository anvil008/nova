---
name: research
description: Investigate a research question across multiple areas with parallel read-only researcher agents, then merge their findings into one deduplicated evidence packet.
---

# Research

Investigate a goal across several areas at once and return one consolidated evidence packet.

Invocation: `/workcell:research`
Prompting Reference: [`docs/models/gpt-5.6-sol/prompting.md`](../../runtime/docs/models/gpt-5.6-sol/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_agent` with native specialist routing from `agents/models.json`, hold human gates, run VCS and shell operations, and read gate evidence and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Gather comprehensive, evidence-backed findings across distinct investigation domains into a unified report.
- **Constraints and Boundaries:** Researchers are strictly read-only and blind to other areas. Never drop conflicting evidence during merge.
- **Success Criteria:** Deduplicated findings merged deterministically, explicit conflict surfaces reported, and verified HTML report rendered.

## Ordered Gates

Execution proceeds through four strict, ordered gates:

1. **area briefs**: Decompose research goal into distinct, non-overlapping investigation areas with clear briefs.
2. **read-only evidence**: Spawn parallel read-only researcher agents, returning evidence envelopes without edits.
3. **deduplication**: Merge envelopes and eliminate duplicate findings via `merge_research.py`.
4. **packet**: Synthesize verified evidence, conflicts, and gaps into the final evidence packet and HTML report.

## Procedure

1. **Decompose into area briefs.** Break the research goal into non-overlapping domains (e.g., code structure, documentation, runtime behavior, or ecosystem prior art).
2. **Parallel investigation.** Dispatch one read-only `researcher` agent per area via `spawn_agent`. Each researcher investigates independently within its assigned domain and returns a structured findings envelope with `file:line` or citation evidence without modifying code.
3. **Deduplication and conflict detection.** Merge envelopes deterministically using `skills/research/scripts/merge_research.py`:

   ```bash
   python3 skills/research/scripts/merge_research.py areas.json area1.json area2.json area3.json
   ```

   Findings are deduplicated by `(area, source, finding)`. Explicit conflicts (opposing stances on the same topic) are preserved and surfaced.
4. **Packet synthesis and rendering.** Consolidate findings, gaps, and open questions into the final evidence packet. Render the synthesis into an HTML report conforming to [`references/report-rendering.md`](references/report-rendering.md):

   ```bash
   python3 skills/research/scripts/render_research.py packet.json report.html --synthesis synthesis.json --title "Research Report" --repo owner/name
   ```

## Offline Demonstration

```bash
PYTHONDONTWRITEBYTECODE=1 python3 skills/research/scripts/merge_research.py skills/research/examples/areas.json skills/research/examples/code.json skills/research/examples/docs.json skills/research/examples/runtime.json
```

## Harness Limitations

API-only model controls (such as dynamic request-level reasoning effort or pro mode toggles) and API-only orchestration features are unsupported in Codex skill prompts; execution relies on native harness tooling and specialist dispatch.
