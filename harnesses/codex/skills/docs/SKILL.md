---
name: docs
description: Run a documentation-standardization and review pass — enforce the doc standard, update stale docs, record ADRs, and check instruction-file bloat. Use standalone, or as the final step of build/deploy.
---

# Docs

Bring a repository's documentation up to standard and keep it there.

Invocation: `/workcell:docs`
Prompting Reference: [`docs/models/gpt-5.6-sol/prompting.md`](../../runtime/docs/models/gpt-5.6-sol/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_agent` with native specialist routing from `agents/models.json`, hold human gates, run workspace and VCS operations using shell execution, and read gate evidence and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never author documentation or edit files directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Audit and update documentation so it accurately reflects system behaviour, adheres to documentation standards, and stays within instruction file line budgets.
- **Constraints and Boundaries:** Never author or edit documentation yourself; dispatch the `documenter`. Enforce mechanical verification through `docs_check.py`.
- **Success Criteria:** `docs_check.py` exits zero, required ADRs follow naming/section standards, and instruction files stay within line budgets.

## Ordered Gates

Execution proceeds through four strict, ordered gates:

1. **truth audit**: Documenter audits repository docs against shipped code and invariants.
2. **documentation update**: Update documentation in place, relocate instruction bloat, record ADRs.
3. **docs check**: Execute `docs_check.py` to enforce line budgets, ADR numbering, and skill references.
4. **review**: Review pass confirms documentation clarity and absence of stale claims.

## Procedure

1. **Truth audit.** Dispatch a `documenter` via `spawn_agent` with a brief carrying the documentation goal, changed-file list, and repository root. The documenter audits existing docs against actual code behaviour, reporting stale, missing, or misplaced content.
2. **Documentation update.** Create a workspace on branch `doc/<slug>` via `workcell-ws add doc/<slug>` ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). Dispatch the `documenter` via `spawn_agent` to update documents in place, relocate role-specific material out of global instruction files, and record ADRs under `docs/adr/NNNN-title.md`. Refer to [examples/visual-readme.md](examples/visual-readme.md) and [`ADR 0010`](../../runtime/docs/adr/0010-readme-diagrams-are-generated-svg.md) for README contracts.
3. **Mechanical verification.** Execute `python3 skills/docs/scripts/docs_check.py <repo-root>` to enforce instruction-file line budgets and ADR numbering standards.
4. **Review.** Conduct review pass to ensure updated docs are clear, accurate, and aligned with shipped behavior.

## Offline Demonstration

```bash
PYTHONDONTWRITEBYTECODE=1 python3 skills/docs/scripts/docs_check.py skills/docs/examples/sample-repo
```

## Harness Limitations

API-only model controls (such as dynamic request-level reasoning effort or pro mode toggles) and API-only orchestration features are unsupported in Codex skill prompts; execution relies on native harness tooling and specialist dispatch.
