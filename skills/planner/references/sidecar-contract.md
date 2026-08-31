# Planner artifact and sidecar contract

The planner agent writes both artifacts together:

- `docs/plans/plan<NN>-<YYYYMMDD>-<title>.html`: the self-contained Foundry Zero plan folio.
- `plan.sidecar.json`: the machine-readable source used to render the folio and reconcile GitHub.

The folio filename is derived, not chosen. `<NN>` is a zero-padded sequence number allocated from the plans directory, `<YYYYMMDD>` comes from `generatedAt` (not from the clock, so a render is reproducible), and `<title>` is a slug of `planName`. The renderer stamps `<!-- workcell-planner planId=... -->` into the HTML and reuses the number of any existing folio carrying the same `planId`, so revising a plan **overwrites its own file** instead of scattering `plan02`, `plan03`, … copies of the same plan across the directory.

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

`risks` is a required key and may be an empty array — an explicit "no risks" is a statement a reviewer can act on, silence is not. `likelihood` and `impact` are `1` (low), `2` (med), or `3` (high); the folio plots each risk at that cell and treats the `>= 6` band as needing a named owner. Risk ids use the same mixed-case ASCII slug format as issue keys and must be unique. A risk is something that may go wrong during execution and has a mitigation. It is not a question you have not asked yet.

`ownershipHint` is exactly one path or glob — a single token, never prose, a comma list, or two paths joined by "and". The renderer rejects a value containing whitespace or a comma, naming the offending `issues[i].ownershipHint` and its value, because every consumer treats the field as one literal path: `skills/build/scripts/waves.py` matches globs against it, and it becomes the `ownership` boundary an agent is handed.

Choose the narrowest glob that covers every file the issue changes **and the tests the specifier will write for it**, so place an issue's tests inside the subtree it owns. `skills/build/scripts/**` beats `skills/**`; a pass over root-level documentation declares `*.md`, not `**`.

Hints must be disjoint within a wave. A collision is not merely untidy — it costs the parallelism the wave was for: `waves.py` rejects a declared same-wave overlap outright and defers an overlapping candidate it had pulled forward. When an issue's files span unrelated subtrees, split the issue rather than widening the glob to their common parent. A pass that genuinely spans the repository (documentation across `docs/`, the README, and the changelog) declares the common parent and, because a coarse hint overlaps everything, serializes itself.

Each issue carries a non-empty `acceptanceTests` list — its TDD **Definition of Done**. Each entry needs `name`, `kind` (`unit`/`integration`/`e2e`), and `oracle` (the observable pass condition); `testPath` and `stub` are optional. These are specifications, not runnable code: they render into the **GitHub issue body** as a "Definition of Done (tests)" checklist (never into the HTML folio), and the `specifier` turns exactly these into real failing tests, proves RED, and seals them before any builder starts.

Keep `planId` and every issue `key` stable across revisions. `planId` uses the lowercase slug format `[a-z0-9]+(?:-[a-z0-9]+)*`. Issue keys and every `dependsOn` entry use the conservative mixed-case ASCII slug format `[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*`, so identifiers such as `T0` and `T1` are valid. Dependencies name issue keys, not issue numbers. A syntactically valid dependency key that is absent from `issues` is allowed as an external dependency and renders as an unknown neutral node using the `--mut` theme token. Malformed dependency text is rejected before Mermaid source is generated. Each issue body sent to GitHub receives `<!-- workcell-planner planId=<planId> issue=<key> -->`; that marker is the durable reconciliation identity. Validation stores `planId`, issue keys, `dependsOn` entries, and risk ids stripped of surrounding whitespace, so a padded value never reaches a marker and re-running an unchanged sidecar stays a no-op.

Each `architecture.components` entry may be either a `{ "name": "...", "purpose": "..." }` object or a non-empty string shorthand when a named component needs no separate purpose. Both forms are treated as text and HTML-escaped by the renderer.

Architecture is a required change story, not a decorative target diagram. Model the smallest meaningful system boundary in both `currentArchitecture` and `targetArchitecture`; the folio labels these views **Current** and **Proposed**. Keep nodes and orientation comparable wherever possible so the difference is immediately visible, and explain that difference concisely in `changeSummary`. When work is not structural, use the pair to compare the relevant state transition, request/data flow, responsibility handoff, or user journey instead. Do not invent a wider architecture merely to fill the diagrams.

The reconciler identifies the milestone by its stable plan marker (falling back to the exact title for adoption), then creates it or updates its title. When it adopts a milestone by title, it appends the plan marker to the existing description rather than replacing it. It scans all repository issues for stable plan/issue markers, creates missing issues, updates changed issues, reopens desired closed issues, closes removed issues, and closes duplicate marked issues. An issue that is closed and labelled `status:done`, or was closed as completed (for example by a merged PR), is finished work: the reconciler leaves it untouched unless `--reopen-done` is passed. Re-running an unchanged plan produces no issue or milestone mutations.

Issue identity comes from the last marker in the body. Marker delimiters in quoted sidecar prose are escaped while composing the issue, so an excerpt cannot squat the issue's identity.

The apply path uses these `gh` command shapes:

```text
gh api --method GET --paginate --slurp repos/{owner}/{repo}/milestones?state=all&per_page=100
gh api --method GET --paginate --slurp repos/{owner}/{repo}/issues?state=all&per_page=100
gh api --method POST repos/{owner}/{repo}/milestones --input -
gh api --method PATCH repos/{owner}/{repo}/milestones/{number} --input -
gh api --method POST repos/{owner}/{repo}/issues --input -
gh api --method PATCH repos/{owner}/{repo}/issues/{number} --input -
```

The folio section order and template maintenance rules live in [report-rendering.md](report-rendering.md).
