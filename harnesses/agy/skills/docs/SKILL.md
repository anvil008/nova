---
name: docs
description: "Orchestrate a standalone documentation-standardization pass: audit stale pages, update API documentation, README examples and architecture decisions or ADRs, enforce the repository documentation standard, run independent validation, and deliver the final docs PR. Assign documenters to scoped areas and decide when documentation is complete. Within build, documenter remains an assigned stage."
---

# Docs

Invocation: `/workcell:docs`
Prompting Reference: [`docs/models/gemini-3.8-flash/prompting.md`](../../runtime/docs/models/gemini-3.8-flash/prompting.md)

Dispatch specialists with Antigravity's `invoke_subagent` and use `run_command` for VCS and validation commands. Reasoning effort is session-wide; respect the configured session settings. Use [anvil.agent-handoff/v1](../../runtime/handoff.md) and configured specialist roles. Resolve bundled helper paths from this skill installation; the `skills/...` command examples are relative to the Workcell package root, while the target repository and run directory are supplied by the brief.

Complete the requested documentation change and deliver its verified final source. Use Markdown for documentation and reports by default; create HTML only when explicitly requested.

The orchestrator owns requirements, authorization, dispatch, and completion. Read source and existing docs to frame the assignment and evaluate the result. Use the shared [planning contract](../plan/SKILL.md) when a new plan or material decision is needed. Delegate documentation writing to the [documenter](../../agents/documenter/agent.md) and independent verification to suitable specialists. Choose team size and iteration from the work and actual runtime capacity; preserve independent evidence without prescribing an inventory agent, a separate update agent, or a fixed number of passes.

The documentation standard and README contract live in the documenter body. See [examples/visual-readme.md](examples/visual-readme.md) for a reference shape; do not duplicate the standard here.


## Ordered Gates

1. **truth audit**: Inspect the requested docs against the source and scope.
2. **scoped documentation**: Have documenter edit the assigned documentation in its workspace.
3. **independent validation**: Verify the complete final source, documentation accuracy, and applicable checks.
4. **delivery**: Record readiness and deliver the authorized final PR; remote checks precede merge.

## Standalone delivery

Save a brief outside source workspaces with the documentation goal, user decisions, allowed paths, exact source base, branch, required checks, and external-write authorization. Inspect the affected behavior and existing documentation before expanding scope. A requested page edit does not authorize a repository-wide standardization pass.

Create an isolated `doc/<slug>` workspace through `workcell-ws` using the repository's existing VCS and a pinned base; follow [workspaces](../../runtime/docs/workspaces.md). Dispatch the documenter with the brief and existing workspace. It updates the assigned docs, checks them against code or other primary evidence, runs the applicable docs checks, and returns its immutable local commit, changed files, evidence, and unresolved questions. It does not open a separate PR.

Validate the complete final source. Require `python3 -B skills/docs/scripts/docs_check.py <repo-root>` and the repository's applicable documentation build, links, examples, and generated-visual checks. Where README visuals are generated, include the project's `render-diagrams.py --check`. An integrator can verify the exact already-combined ref without a milestone ledger. Review source accuracy, coverage of the request, and relevant rendered output independently; `docs_check` checks structure and instruction-file size, not whether the prose is true. Do not require product RED tests for a documentation-only change.

Resolve actionable findings within the authorized documentation scope and reverify changed source. Preserve unresolved or stalled issues with their evidence; the orchestrator chooses useful iterations and respects explicit user limits. Source, base, or documentation changes invalidate evidence that no longer applies.

Record completion outside the workspace with the verified commit and base, handoffs, command IDs and outputs, and the orchestrator's decision. Open or update the final PR only within existing authorization and from that verified head; remote checks must pass before an authorized merge. Local readiness is not a merged PR. Retain workspace and evidence until merge or explicit abandonment, and resume from those records rather than recreating work.

## Documentation within another workflow

A build or deployment dispatches the documenter directly as an assigned stage. That agent follows its role contract and returns control; it does not invoke this standalone `/docs` lifecycle, create another plan, or open another PR. The calling workflow supplies ownership and source evidence, combines the docs commit using its own finalization protocol, and performs final verification after all documentation changes are present. A late docs edit requires verification of the changed final source.

## Offline check

```bash
python3 -B skills/docs/scripts/docs_check.py skills/docs/examples/sample-repo
```
