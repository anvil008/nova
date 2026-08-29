---
name: planner
description: Investigate a repository task and produce an offline HTML implementation plan plus a strict JSON sidecar, then—only after explicit human approval—idempotently reconcile the plan into a GitHub milestone and issues. Use for substantial coding work that should be reviewed before GitHub tracking is created; do not use for direct implementation or GitHub Projects.
---

# Planner

Turn a repository change into an evidence-backed, reviewable plan.

You are the orchestrator. The `planner` agent does the investigating and writes both artifacts; you relay its open questions to the human, hold the approval gate, and are the only one who writes GitHub ([ADR 0007](../../docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)). Nothing here has you read the target project yourself.

## Deliverables

Write both artifacts together:

- `docs/plans/plan<NN>-<YYYYMMDD>-<title>.html`: the self-contained Foundry Zero plan folio.
- `plan.sidecar.json`: the machine-readable source used to render the folio and reconcile GitHub.

The folio filename is derived, not chosen. `<NN>` is a zero-padded sequence number allocated from
the plans directory, `<YYYYMMDD>` comes from `generatedAt` (not from the clock, so a render is
reproducible), and `<title>` is a slug of `planName`. The renderer stamps
`<!-- swarm-planner planId=... -->` into the HTML and reuses the number of any existing folio
carrying the same `planId`, so revising a plan **overwrites its own file** instead of scattering
`plan02`, `plan03`, … copies of the same plan across the directory.

The sidecar has exactly these top-level fields:

```json
{
  "planId": "stable-slug",
  "planName": "Milestone title",
  "repo": "owner/name",
  "generatedAt": "2026-08-26T12:00:00Z",
  "summary": "Goal and outcome",
  "architecture": {
    "changeSummary": "Concise explanation of what changes and why",
    "components": [{"name": "Component", "purpose": "Responsibility"}],
    "diagramsMermaid": {
      "currentArchitecture": "flowchart LR\n  A --> B",
      "targetArchitecture": "flowchart LR\n  A --> C"
    }
  },
  "issues": [{
    "key": "stable-issue-key",
    "title": "Issue title",
    "body": "Complete acceptance-oriented scope",
    "labels": ["planning"],
    "dependsOn": [],
    "ownershipHint": "path/or/module",
    "wave": 1,
    "acceptanceTests": [
      {"name": "slug", "kind": "unit|integration|e2e", "oracle": "observable pass condition", "testPath": "optional/path", "stub": "optional skeleton"}
    ]
  }],
  "risks": [{
    "id": "R-01",
    "title": "What could go wrong",
    "likelihood": 1,
    "impact": 3,
    "owner": "who carries it",
    "mitigation": "the concrete thing that reduces it"
  }]
}
```

`risks` is a required key and may be an empty array — an explicit "no risks" is a statement a
reviewer can act on, silence is not. `likelihood` and `impact` are `1` (low), `2` (med), or `3`
(high); the folio plots each risk at that cell and treats the `>= 6` band as needing a named owner.
Risk ids use the same mixed-case ASCII slug format as issue keys and must be unique.

A risk is something that may go wrong during execution and has a mitigation. It is not a question
you have not asked yet — see below.

Each issue carries a non-empty `acceptanceTests` list — its TDD **Definition of Done**. Each entry needs `name`, `kind` (`unit`/`integration`/`e2e`), and `oracle` (the observable pass condition); `testPath` and `stub` are optional. These are specifications, not runnable code: they render into the **GitHub issue body** as a "Definition of Done (tests)" checklist (never into the HTML folio), and the `test-author` agent turns exactly these into real failing tests, proves RED, and seals them before any builder starts.

Keep `planId` and every issue `key` stable across revisions. `planId` uses the lowercase slug format `[a-z0-9]+(?:-[a-z0-9]+)*`. Issue keys and every `dependsOn` entry use the conservative mixed-case ASCII slug format `[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*`, so identifiers such as `T0` and `T1` are valid. Dependencies name issue keys, not issue numbers. A syntactically valid dependency key that is absent from `issues` is allowed as an external dependency and renders as an unknown neutral node using the `--mut` theme token. Malformed dependency text is rejected before Mermaid source is generated. Each issue body sent to GitHub receives `<!-- swarm-planner planId=<planId> issue=<key> -->`; that marker is the durable reconciliation identity. Validation stores `planId`, issue keys, `dependsOn` entries, and risk ids stripped of surrounding whitespace, so a padded value never reaches a marker and re-running an unchanged sidecar stays a no-op.

Each `architecture.components` entry may be either a `{ "name": "...", "purpose": "..." }` object or a non-empty string shorthand when a named component needs no separate purpose. Both forms are treated as text and HTML-escaped by the renderer.

Architecture is a required change story, not a decorative target diagram. Model the smallest
meaningful system boundary in both `currentArchitecture` and `targetArchitecture`; the folio labels
these views **Current** and **Proposed**. Keep nodes and orientation comparable wherever possible so
the difference is immediately visible, and explain that difference concisely in `changeSummary`.
When work is not structural, use the pair to compare the relevant state transition, request/data
flow, responsibility handoff, or user journey instead. Do not invent a wider architecture merely
to fill the diagrams.

## Plan workflow

1. **Dispatch the `planner` agent** with the goal and any decisions the human has already made. It investigates read-only, defines the architecture delta and dependency-ordered issues, authors each issue's `acceptanceTests`, writes the strict sidecar, renders the folio, and runs the read-only reconciliation preview.

   ```bash
   python3 skills/planner/scripts/render_plan.py plan.sidecar.json
   python3 skills/planner/scripts/render_plan.py plan.sidecar.json --plans-dir docs/plans
   ```

   Omit the output path to get the `docs/plans/` naming convention; pass one explicitly only for a scratch render nobody intends to keep.

2. **Resolve open questions with the human before writing the plan.** Carry them yourself — the agent cannot. An agent that returns disposition `needs-decision` found something material undecided — scope boundaries, a choice between two approaches, an unowned dependency, an ambiguous requirement. Put the question to the human, wait for the answer, and re-dispatch the agent with it. Never answer on the human's behalf, and never let an unanswered question through: a plan carrying one is not ready for approval, and the sidecar has nowhere to put it by design.
3. Present the HTML folio for review. You **must stop** here for explicit human approval. Approval to plan is not approval to write GitHub resources.
4. Before approval, a read-only reconciliation preview is allowed — the agent runs one, and you may run another against a captured snapshot:

   ```bash
   python3 skills/planner/scripts/reconcile_github.py plan.sidecar.json --snapshot github-state.json
   python3 skills/planner/scripts/reconcile_github.py plan.sidecar.json
   ```

5. **Only after the human approves the reviewed artifacts**, apply the exact approved sidecar yourself with an approval identity. This write is the orchestrator's, never the agent's:

   ```bash
   python3 skills/planner/scripts/reconcile_github.py plan.sidecar.json --apply --approved-by "<human identity>"
   ```

Do not infer approval from silence, prior approval of another revision, or a request to investigate. If the sidecar changes after approval, present the changed plan and stop for fresh human approval.

## GitHub reconciliation

Use milestones only; never create or modify a GitHub Project. The reconciler identifies the milestone by its stable plan marker (falling back to the exact title for adoption), then creates it or updates its title. When it adopts a milestone by title, it appends the plan marker to the existing description rather than replacing it. It scans all repository issues for stable plan/issue markers, creates missing issues, updates changed issues, reopens desired closed issues, closes removed issues, and closes duplicate marked issues. An issue that is closed and labelled `status:done`, or was closed as completed (for example by a merged PR), is finished work: the reconciler leaves it untouched unless `--reopen-done` is passed. Re-running an unchanged plan produces no issue or milestone mutations.

The apply path uses these `gh` command shapes:

```text
gh api --method GET --paginate --slurp repos/{owner}/{repo}/milestones?state=all&per_page=100
gh api --method GET --paginate --slurp repos/{owner}/{repo}/issues?state=all&per_page=100
gh api --method POST repos/{owner}/{repo}/milestones --input -
gh api --method PATCH repos/{owner}/{repo}/milestones/{number} --input -
gh api --method POST repos/{owner}/{repo}/issues --input -
gh api --method PATCH repos/{owner}/{repo}/issues/{number} --input -
```

Never run `--apply` merely to test the skill. Use snapshot preview and local rendering for validation.

## Report contract

Use [templates/plan.html.tmpl](templates/plan.html.tmpl) through the renderer. Keep the fixed folio
section order — 01 Overview, 02 Architecture, 03 Task Breakdown, 04 Execution Waves, 05 Risks,
06 Milestone & Execution — and all CSS and Mermaid code inline. The HTML must
remain useful without JavaScript: every Mermaid diagram starts as a Claude-Artifact-compatible
`<pre class="mermaid">` source block and includes a source-details fallback that becomes visible if
rendering fails.

Section 02 renders the strict `currentArchitecture` and `targetArchitecture` pair side by side as
**Current** and **Proposed**, followed by responsive stacking on narrow screens. It also renders the
escaped `changeSummary`, so the visual remains understandable to people while the sidecar remains
precise enough for machine consumers.

Styling comes from two files. [templates/report.css](templates/report.css) is the shared Foundry
Zero report design system — colour tokens, severity ramp, chrome, print rules — and is
**byte-identical** to `skills/code-review/templates/report.css`; a test enforces that, so change
both together or neither. [templates/plan.css](templates/plan.css) holds planner-only components
(approval gate, wave lanes, risk matrix). The report is theme-aware, responsive,
and prints: disclosure rows open for print and the chrome is suppressed.

The folio never renders acceptance tests; they belong to the GitHub issue body. Section 00 states
the approval gate, and it always reads "Proposed — awaiting explicit human approval" because the
folio is the artifact a human reads *before* approving.
