---
name: deploy
description: Ship a verified change safely — pre-flight checks, versioning, CI/CD, an approved deploy, post-deploy verification, and a rollback path. Human-gated; deployment is outward-facing and hard to reverse.
---

# Deploy

Take verified, merged code to a running environment — safely and reversibly.

Invocation: `/workcell:deploy`
Prompting Reference: [`docs/models/claude-opus-5/prompting.md`](../../runtime/docs/models/claude-opus-5/prompting.md)

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents via Claude Code's `Agent` tool, hold the human gates, run `git` / `jj` / `gh` and scripts via the `Bash` tool for branch, merge, and issue-state operations, and read gate output and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator is the sole release authority and dispatches the `deployer` agent only after approval names the target and commit. In accordance with the Claude Opus 5 guide, structure task specifications comprehensively up front, state exact targets, and prevent runaway subagent delegation.

## Goals and Constraints

- **Goal:** Safely ship verified code to a designated running environment with verified health checks and an immediate rollback path.
- **Constraints:** Never deploy without explicit human approval naming the exact commit and environment target. Never echo or persist secrets. Roll back immediately upon verification failure.
- **Success Criteria:** Pre-flight checks pass, release succeeds, post-deploy verification window observes healthy operations, and rollback readiness is confirmed.

## Ordered Gates

Execution proceeds through five strict, ordered gates:

1. **approval**: Human gate explicitly approves deployment naming target and commit.
2. **preflight**: Deployer agent verifies target readiness, credentials, and environment state.
3. **release**: Deployer performs staged release execution to the target.
4. **verification**: Post-deploy health checks run within the verification window.
5. **rollback readiness**: Tested rollback command confirmed ready and executed immediately if checks fail.

## Human Gate

Deployment is outward-facing and hard to reverse. **Never deploy without explicit approval**, and approval for one deploy is not standing. Production deploys always require a fresh, explicit go. Never echo secrets; confirm the target (staging vs prod) before every deploy.

## Procedure

Every step below is a dispatch. You sequence the agents, read their evidence, and hold the gate; you run none of it yourself.

1. **Version + changelog.** Dispatch the `documenter` agent via the `Agent` tool to bump semver, update the `CHANGELOG`, and write the release notes — a short summary of what the release delivers, the changelog entries for this version, and any breaking-change or upgrade callouts. Where the release needs a branch of its own, it is `release/<slug>` ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). Tag the release yourself, then publish the GitHub release for that tag — `gh release create vX.Y.Z --title "<project> vX.Y.Z" --notes-file <notes>` via `Bash` — from the documenter's release notes. The release title is exactly `<project> vX.Y.Z`: the descriptive strapline belongs to the changelog entry heading, not the title, and the notes never repeat the title as their own first heading. Tagging and publishing a release are git/`gh` operations, not authorship.
2. **CI/CD.** If the pipeline needs creating or adjusting, dispatch a `builder` via the `Agent` tool for it: workflow and config code is code, and goes through the same test-first path where it is testable.
3. **Pre-flight and deploy.** After explicit human approval naming *this* target and *this* commit, dispatch the `deployer` agent via the `Agent` tool with the target, the commit, the verification window, and the approval. It runs pre-flight, confirms the rollback command, deploys, verifies, and rolls back on any failed check. When the project publishes packages (GitHub Packages, npm, a container registry), that publish is part of this gated deploy — never a separate, unapproved step.
4. **Read the evidence, not the summary.** The agent returns exact commands with `commandId`s, what it observed in the verification window, and whether it rolled back. A claim that the deploy "looks good" is not verification. A rollback is a successful outcome of the procedure, not a failure of it.
5. **Record.** Dispatch the `documenter` agent via the `Agent` tool for an ADR on any non-trivial release decision and for the handover entry.

## Boundaries

The orchestrator never infers approval, never deploys secrets, and never treats a green pre-flight as permission to deploy. Deploy targets, credentials, and rollback steps come from the project — never invented.

## Harness Limitations

Native context forks and workflows are omitted with notes in Claude Code; procedures execute sequentially within the primary session.
