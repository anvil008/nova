---
name: docs
description: Run a documentation-standardization and review pass — enforce the doc standard, update stale docs, record ADRs, and check instruction-file bloat. Use standalone, or as the final step of build/deploy.
---

# Docs

Bring a repository's documentation up to standard and keep it there.

Invocation: `/workcell:docs`
Prompting Reference: [`docs/models/claude-sonnet-5/prompting.md`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents, hold the human gates, run `git` / `jj` / `gh` for branch, merge, and issue-state operations, and read gate output and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator scopes one coherent documentation pass, dispatches the `documenter` agent, and judges completion from the mechanical docs gate and handoff evidence.

The canonical documentation standard and README contract live in the [`documenter` agent body](../../agents/documenter.md); link to that contract rather than duplicating it here. See [examples/visual-readme.md](examples/visual-readme.md) for the reference shape.

## Ordered Gates

Execution proceeds through four strict, ordered gates:
1. **truth audit**: Inventory documentation to identify stale, inaccurate, missing, or bloated content against current code reality.
2. **documentation update**: Author precise updates in place, recording needed ADRs and updating changelogs/handovers.
3. **docs check**: Execute `python3 -B skills/docs/scripts/docs_check.py` and diagram validation to mechanically verify compliance.
4. **review**: Peer review verifies clarity, consistency, and adherence to the documentation standard.

## Pass

1. **Dispatch the inventory.** Send one `documenter` agent a brief carrying the documentation goal, the changed-file list or release handoff, the allowed ownership paths, the repository root, and the canonical [`documenter` agent contract](../../agents/documenter.md). The agent inventories the documentation and reports stale, duplicate, missing, and misplaced material before writing.
2. **Dispatch the update.** A documentation pass works on its own branch, `doc/<slug>`, and the workspace beneath it writes that slash as a dash ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). After confirming the ownership is coherent, dispatch the same role to update in place, relocate role-specific material out of global instruction files, record required ADRs at the repository root (`docs/adr/NNNN-title.md`), and append the changelog or handover entry. Split only genuinely independent doc areas.
3. **Gate the result.** The `documenter` agent runs `python3 -B skills/docs/scripts/docs_check.py <repo-root>` — and, where the repository generates its README visuals, its `render-diagrams.py --check` ([ADR 0010](../../runtime/docs/adr/0010-readme-diagrams-are-generated-svg.md)) — and returns the exact command, exit code, summary, and changed files. The gate is GREEN only when `docs_check` exits zero and the handoff shows every requested doc area covered; otherwise re-dispatch the failed area. The orchestrator reads this evidence and never judges the document contents itself.

## Harness Limitations

Native context forks and workflows are omitted with notes in Claude Code; procedures execute sequentially within the primary session.

## Offline Demonstration

```bash
python3 -B skills/docs/scripts/docs_check.py skills/docs/examples/sample-repo
```
