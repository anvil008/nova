# Planner artifact and sidecar contract

The assigned final planner authors the reviewed executable plan from a strict sidecar. Early alternative ideas and concise task briefs need no synthetic sidecar. Substantial plans produce:

- `docs/plans/plan<NN>-<YYYYMMDD>-<title>.md`: the default readable plan, including acceptance criteria.
- `plan.sidecar.json`: the machine-readable source for rendering and optional GitHub reconciliation.
- `docs/plans/plan<NN>-<YYYYMMDD>-<title>.html`: an additional self-contained visual folio, only when the user explicitly requests visual/HTML output.

Do not ask a format question. Markdown is always included; an explicit Markdown-only request creates no HTML. The orchestrator reviews the artifacts, returns revisions to the planner, and holds user approval for external writes.

The report filename is derived. `<NN>` is a zero-padded sequence allocated across both Markdown and HTML plans; `<YYYYMMDD>` comes from `generatedAt`, and `<title>` from `planName`. Both formats carry the `<!-- workcell-planner planId=... -->` marker. Revisions and format changes reuse the existing basename for that identity rather than claiming a new number. Render both requested formats from the same sidecar so they agree. Adding HTML later requires an explicit format request and preserves the existing plan identity and execution scope.

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

`repo` is a GitHub `owner/name` when tracking that repository, or `null` for local-only plans. Do not invent a GitHub identity to satisfy the schema. The build workflow can select sidecar tasks and record completion in its local ledger; GitHub reconciliation rejects `repo: null` before any API call.

`risks` is a required key and may be an empty array — an explicit "no risks" is a statement a reviewer can act on, silence is not. `likelihood` and `impact` are `1` (low), `2` (med), or `3` (high); the folio plots each risk at that cell and treats the `>= 6` band as needing a named owner. Risk ids use the same mixed-case ASCII slug format as issue keys and must be unique. A risk is something that may go wrong during execution and has a mitigation. It is not a question you have not asked yet.

`ownershipHint` is exactly one path or glob — a single token, never prose, a comma list, or two paths joined by "and". The renderer rejects a value containing whitespace or a comma, naming the offending `issues[i].ownershipHint` and its value, because every consumer treats the field as one literal path: `skills/build/scripts/waves.py` matches globs against it, and it becomes the `ownership` boundary an agent is handed.

`ownershipHint` and `acceptanceTests[].testPath` must use canonical relative POSIX paths: `/` separates components, and no component may be empty, `.` or `..`. Absolute paths, Windows drive prefixes, backslashes, control characters, surrounding whitespace, and trailing or repeated separators are rejected before rendering or scheduling. `ownershipHint` may contain a glob; `testPath` names one concrete test file and rejects glob metacharacters (`*`, `?`, `[`), so sealed test evidence can authorize the exact file.

Choose the narrowest glob covering the implementation. Tests can live inside it, or name each external test file in `acceptanceTests[].testPath`; the orchestrator copies those approved paths into the specifier's `brief.testOwnership[]`. Do not widen implementation ownership solely to reach a separate test directory. `skills/build/scripts/**` beats `skills/**`; a pass over root-level documentation declares `*.md`, not `**`.

Implementation hints and declared test paths must be disjoint within a wave. The selector checks their combined write targets, including a test file overlapping another issue's implementation hint. A collision is not merely untidy — it costs the parallelism the wave was for: `waves.py` rejects a declared same-wave overlap outright and defers an overlapping candidate it had pulled forward. When an issue's files span unrelated subtrees, split the issue rather than widening the glob to their common parent. A pass that genuinely spans the repository (documentation across `docs/`, the README, and the changelog) declares the common parent and, because a coarse hint overlaps everything, serializes itself.

Each issue carries a non-empty `acceptanceTests` list — its observable **Definition of Done**. Each entry needs `name`, `kind` (`unit`/`integration`/`e2e`), and `oracle` (the observable pass condition); `testPath` and `stub` are optional. These are specifications, not runnable code: they render into the **GitHub issue body** as a "Definition of Done (tests)" checklist (also into the Markdown plan; the HTML folio stays concise), Feature and bug tasks use the `specifier` to turn these into runnable failing tests, prove RED, and seal them before implementation. Behavior-preserving refactors and optimizations use the build workflow's verified baseline path and appropriate regression or performance oracles; they do not manufacture failing tests for unchanged behavior.

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
