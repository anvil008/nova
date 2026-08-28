---
name: planner
description: Investigate a repository task and produce an offline HTML implementation plan plus a strict JSON sidecar, then—only after explicit human approval—idempotently reconcile the plan into a GitHub milestone and issues. Use for substantial coding work that should be reviewed before GitHub tracking is created; do not use for direct implementation or GitHub Projects.
---

# Planner

Turn a repository change into an evidence-backed, reviewable plan. Investigate the target repository and task read-only. Do not modify product code while planning.

## Deliverables

Write both artifacts together:

- `<plan-name>.html`: the self-contained Foundry Zero plan folio.
- `plan.sidecar.json`: the machine-readable source used to render the folio and reconcile GitHub.

The sidecar has exactly these top-level fields:

```json
{
  "planId": "stable-slug",
  "planName": "Milestone title",
  "repo": "owner/name",
  "generatedAt": "2026-08-26T12:00:00Z",
  "summary": "Goal and outcome",
  "architecture": {
    "components": [{"name": "Component", "purpose": "Responsibility"}],
    "diagramsMermaid": {"targetArchitecture": "flowchart LR\n  A --> B"}
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
  }]
}
```

Each issue carries a non-empty `acceptanceTests` list — its TDD **Definition of Done**. Each entry needs `name`, `kind` (`unit`/`integration`/`e2e`), and `oracle` (the observable pass condition); `testPath` and `stub` are optional. These are specifications, not runnable code: they render into the **GitHub issue body** as a "Definition of Done (tests)" checklist (never into the HTML folio), and the builder authors, red-proves, and seals exactly these tests.

Keep `planId` and every issue `key` stable across revisions. `planId` uses the lowercase slug format `[a-z0-9]+(?:-[a-z0-9]+)*`. Issue keys and every `dependsOn` entry use the conservative mixed-case ASCII slug format `[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*`, so identifiers such as `T0` and `T1` are valid. Dependencies name issue keys, not issue numbers. A syntactically valid dependency key that is absent from `issues` is allowed as an external dependency and renders as an unknown neutral node using the `--mut` theme token. Malformed dependency text is rejected before Mermaid source is generated. Each issue body sent to GitHub receives `<!-- swarm-planner planId=<planId> issue=<key> -->`; that marker is the durable reconciliation identity.

Each `architecture.components` entry may be either a `{ "name": "...", "purpose": "..." }` object or a non-empty string shorthand when a named component needs no separate purpose. Both forms are treated as text and HTML-escaped by the renderer.

## Plan workflow

1. Read repository guidance, relevant code, tests, architecture, and current state without changing the target project.
2. Define the goal, target architecture, dependency-ordered issues, ownership hints, execution waves, risks, and open questions. Prefer one independently deliverable concern per issue.
3. Write the strict sidecar, then render it:

   ```bash
   python3 scripts/render_plan.py plan.sidecar.json plan.html
   ```

4. Open or otherwise present the HTML folio for review. The planner **must stop for explicit human approval** here. Approval to plan is not approval to write GitHub resources.
5. Before approval, a read-only reconciliation preview is allowed. Use a captured API snapshot for an offline preview, or omit `--snapshot` to query GitHub read-only:

   ```bash
   python3 scripts/reconcile_github.py plan.sidecar.json --snapshot github-state.json
   python3 scripts/reconcile_github.py plan.sidecar.json
   ```

6. Only after the human approves the reviewed artifacts, apply the exact approved sidecar with an approval identity:

   ```bash
   python3 scripts/reconcile_github.py plan.sidecar.json --apply --approved-by "<human identity>"
   ```

Do not infer approval from silence, prior approval of another revision, or a request to investigate. If the sidecar changes after approval, present the changed plan and stop for fresh human approval.

## GitHub reconciliation

Use milestones only; never create or modify a GitHub Project. The reconciler identifies the milestone by its stable plan marker (falling back to the exact title for adoption), then creates it or updates its title. It scans all repository issues for stable plan/issue markers, creates missing issues, updates changed issues, reopens desired closed issues, closes removed issues, and closes duplicate marked issues. Re-running an unchanged plan produces no issue or milestone mutations.

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

Use [templates/plan.html.tmpl](templates/plan.html.tmpl) through the renderer. Keep the fixed folio section order and all CSS and Mermaid code inline. The HTML must remain useful without JavaScript: every Mermaid diagram starts as a Claude-Artifact-compatible `<pre class="mermaid">` source block and includes a source-details fallback that becomes visible if rendering fails.
