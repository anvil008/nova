# Planning research evidence

Researcher agents provide evidence to planner agents. The planner scopes investigations, owns synthesis, and writes the plan; the orchestrator chooses team size and reviews the resulting plan. There is no standalone `/research` skill. Native research can answer independent research requests without initiating planning or asking to proceed to a plan.

Use this contract when planning needs delegated evidence. The planner dispatches with a supported native agent tool, or asks the orchestrator to dispatch and route the results when nesting is unavailable. Team size follows the orchestrator's judgment, real independent questions, actual capacity, and any explicit user constraints; the contract prescribes no count or retry budget.

## Questions and evidence envelopes

Split work by the actual uncertainty: a subsystem, source, runtime question, compatibility issue, or prior art. Allocate a unique `area` ID to every report expected by the merger, including independently assigned investigations of the same topic. A shared `topic` lets the planner compare evidence across areas. Narrow each brief to the evidence it needs and reuse applicable reports rather than duplicating completed investigations.

Declare questions in an areas manifest:

```json
{
  "areas": [
    {"area": "compatibility", "scope": "Compatibility constraints for the proposed change", "sources": ["relevant source paths or URLs"]}
  ]
}
```

Each researcher is read-only and returns its findings inside the `evidence` field of an `anvil.agent-handoff/v1` record. Save that field as a report JSON file with exactly this shape:

```json
{
  "area": "compatibility",
  "coverage": {
    "scope": "Compatibility constraints for the proposed change",
    "sourcesInspected": ["actual source inspected"]
  },
  "findings": [
    {
      "source": "file:line or URL",
      "finding": "what was learned",
      "evidence": "source location, command output, or a short excerpt",
      "topic": "shared-topic-slug",
      "stance": "neutral",
      "position": "this source's position on the topic"
    }
  ],
  "gaps": ["what the investigation could not resolve"],
  "openQuestions": ["a material question raised by the evidence"]
}
```

Findings distinguish established facts from inference and retain source links. Use empty arrays when no substantiated findings, gaps, or questions apply. Never imply that a planned command ran or an uninspected source was checked.

`stance` is `supports`, `contradicts`, or `neutral` (the default). Use `contradicts` when a source contradicts a position on the same topic, `supports` for corroborating evidence, and `neutral` for context. Wording differences alone do not establish a conflict.

## Merge, conflicts, and coverage

The deterministic merger:

1. Deduplicates findings by `(area, source, finding)` and preserves declared area order.
2. Reports a conflict when a topic has a `contradicts` finding, retaining every position on that topic without dropping any finding.
3. Reports declared areas without an envelope as missing, and retains each area's gaps and open questions. `coverage.complete` means every declared area returned an envelope, not that every question was resolved.

Run it over captured envelopes, not handoff wrappers:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B skills/plan/research/scripts/merge_research.py skills/plan/research/examples/areas.json skills/plan/research/examples/code.json skills/plan/research/examples/docs.json skills/plan/research/examples/runtime.json
```

An empty report list produces an incomplete packet naming all missing areas. No evidence is manufactured for failed or unavailable agents. Keep original envelopes alongside the packet so inspected-source details and provenance remain available. The planner verifies critical findings and writes the synthesis; the merger does not choose a plan or turn agent agreement into proof.

## Optional visual evidence report

The plan always includes a readable Markdown account of its evidence and links to the packet. When the user explicitly requests a visual research companion, preserve the packet and write synthesis JSON as:

```json
{
  "verdict": "advisory",
  "summary": "What the evidence means for the plan",
  "recommendations": [
    {"priority": "low", "title": "Recommendation", "detail": "Evidence-backed action", "refs": ["F1-01"]}
  ]
}
```

Verdicts are `clean`, `advisory`, or `action-needed`; recommendation priorities are `high`, `medium`, or `low`. References use finding IDs (`F<area index>-<finding index>`) from the packet. Render the optional self-contained report with:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B skills/plan/research/scripts/render_research.py packet.json research.html --synthesis synthesis.json --title "Plan evidence" --repo owner/name --subject "what was researched"
```

The renderer rejects unknown finding references and a `clean` verdict carrying recommendations. Maintainers follow the [research report-rendering contract](../research/references/report-rendering.md).
