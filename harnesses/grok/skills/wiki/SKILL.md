---
name: wiki
description: Consolidate what a project's finished runs taught into its own persistent wiki — a namespace outside the repository holding write-once raw traces, append-only pattern pages, and a catalog. Opt-in per project — no namespace means nothing is recorded and nothing is dispatched; invoke as /workcell:wiki init to opt the current repository in with one confirmed question.
---

# Wiki

Turn what a project's finished runs taught into a durable record of that project, kept in a namespace outside the repository so it outlives every branch, worktree, and clone.

Invocation: `/workcell:wiki`
Prompting Reference: [`docs/models/grok-4.6/prompting.md`](../../runtime/docs/models/grok-4.6/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_subagent` (running in foreground or with `background: true` tracked via `get_command_or_subagent_output`, or coordinated via `/workflow`), hold human gates, run VCS and shell operations, and read gate output and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Consolidate learnings from finished workflow runs into an append-only project wiki outside repository version control.
- **Constraints and Boundaries:** Opt-in only: never create a namespace or record evidence without explicit human opt-in. The runtime agents (`specifier`, `builder`, `reviewer`, `integrator`) neither read nor write the wiki.
- **Success Criteria:** Verified write-once raw bundles, append-only pattern citations, and `wiki.py check` exit zero.

## Ordered Gates

Execution proceeds through four strict, ordered gates:

1. **project opt-in**: Check if project opted in via `wiki.py status`; prompt human if not.
2. **write-once trace**: Documenter records immutable evidence bundles via `wiki.py record`.
3. **append-only pattern**: Documenter appends observed patterns citing raw trace evidence via `wiki.py pattern`.
4. **catalog update**: Verify catalog and links mechanically with `wiki.py check`.

## Procedure

1. **Check project opt-in.** Check status:

   ```bash
   python3 skills/wiki/scripts/wiki.py status --repo .
   ```

   If `present: false`, ask the user whether to opt in. On confirmation, initialize the namespace:

   ```bash
   python3 skills/wiki/scripts/wiki.py init --repo .
   ```

   If the user declines or in non-interactive environments, end the workflow without dispatching agents.
2. **Dispatch consolidation.** Dispatch a single `documenter` via `spawn_subagent` with a brief conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md) whose `ownership` is restricted to the resolved namespace path.
3. **Record immutable traces and append patterns.** The documenter writes immutable bundles via `python3 skills/wiki/scripts/wiki.py record` and appends verified patterns citing trace IDs via `python3 skills/wiki/scripts/wiki.py pattern`. Layout details conform to [`references/wiki-layout.md`](references/wiki-layout.md).
4. **Verify catalog.** Verify catalog consistency and internal link integrity:

   ```bash
   python3 skills/wiki/scripts/wiki.py check --repo .
   ```

## Harness Limitations

Skill frontmatter fields `allowed-tools`, `model`, `effort`, `license`, and `compatibility` are unsupported for capability enforcement or routing under Grok Build; execution relies on native CLI flags (`--tools`, `--disallowed-tools`), agent definitions, capability modes, and specialist dispatch. API-only model controls and programmatic tool calling are unsupported in skill prompts.
