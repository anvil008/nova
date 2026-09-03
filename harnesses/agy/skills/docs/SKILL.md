---
name: docs
description: Run a documentation-standardization and review pass — enforce the doc standard, update stale docs, record ADRs, and check instruction-file bloat. Use standalone, or as the final step of build/deploy.
---

# Docs

Run a documentation audit and update pass: enforce documentation standards, update stale references, record architectural decisions (ADRs), and enforce instruction-file budgets.

Invocation: `/workcell:docs`
Prompting Reference: [`docs/models/gemini-3.7-flash/prompting.md`](../../runtime/docs/models/gemini-3.7-flash/prompting.md)

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents via Antigravity's `invoke_subagent`, hold the human gates, run `git` / `jj` / `gh` and scripts via `run_command` for branch, merge, and issue-state operations, and read gate output and handoff records using the [`anvil.agent-handoff/v1`](../../runtime/handoff.md) schema. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator coordinates the documentation audit and delegates documentation editing to the documenter agent. Per the Gemini 3.7 Flash guide, place critical constraints first, verify truth against running code, and maintain concise, factual prose.

## Critical Constraints

- **Goal:** Ensure all repository documentation reflects current code truth, obeys line and complexity budgets, and passes automated linting.
- **Constraints:** Never document features or commands that do not exist or fail to run. Never duplicate documentation contracts; link to canonical agent specifications.
- **Success Criteria:** Truth audit complete, documentation files updated, `docs_check.py` passing cleanly, and multi-lens review approved.

## Ordered Gates

Execution proceeds through four strict, ordered gates:

1. **truth audit**: Inspect running code and commands to verify that existing docs match actual behaviour.
2. **documentation update**: Documenter updates outdated documentation, records ADRs, and trims bloat.
3. **docs check**: Run automated documentation linters and gate checkers via `docs_check.py`.
4. **review**: Reviewer verifies clarity, accuracy, and adherence to documentation standards.

## Documentation Standard

The canonical documentation standard and README contract live in the [documenter agent body](../../agents/documenter/agent.md); link to that contract rather than duplicating it here.

Every README must answer:

- what the repository does
- why it exists
- shortest viable quickstart
- compact visual accompanied by a nearby textual explanation with meaningful labels and concise, plain-language prose

## Procedure

## Pass

1. **Audit documentation truth.** Dispatch a `researcher` agent via `invoke_subagent` to compare documented commands, workflows, and configurations against actual repository scripts and code.
2. **Update documentation.** A documentation pass works on its own branch, `doc/<slug>`, and the workspace beneath it writes that slash as a dash ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). Dispatch the `documenter` agent via `invoke_subagent` with an explicit docs-only `ownership` glob to update in place, relocate role-specific material out of global instruction files, record required ADRs at the repository root (`docs/adr/NNNN-title.md`), and append the changelog or handover entry. See [examples/visual-readme.md](examples/visual-readme.md) and [`ADR 0010`](../../runtime/docs/adr/0010-readme-diagrams-are-generated-svg.md) for README contracts. Split only genuinely independent doc areas.
3. **Run docs check.** The `documenter` agent runs:
   ```bash
   python3 -B skills/docs/scripts/docs_check.py .
   ```
   and, where the repository generates its README visuals, its diagram freshness verification ([ADR 0010](../../runtime/docs/adr/0010-readme-diagrams-are-generated-svg.md)):
   ```bash
   python3 scripts/render-diagrams.py --check
   ```
   and returns the exact command, exit code, summary, and changed files. The gate is GREEN only when `docs_check` exits zero, diagrams are verified fresh, and the handoff shows every requested doc area covered; otherwise re-dispatch the failed area. The orchestrator reads this evidence and never judges the document contents itself.
4. **Review.** Dispatch a `reviewer` agent via `invoke_subagent` to evaluate the documentation changes for clarity, accuracy, and completeness.

## Boundaries

Documentation must be strictly factual. Do not write aspirational quickstarts or document unreleased flags. Keep instruction files lean and strictly within line limits.

## Offline Demonstration

```bash
python3 -B skills/docs/scripts/docs_check.py skills/docs/examples/sample-repo
```

Based on the requirements and constraints above, execute the docs workflow systematically.
