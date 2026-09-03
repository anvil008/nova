---
name: deploy
description: Ship a verified change safely — pre-flight checks, versioning, CI/CD, an approved deploy, post-deploy verification, and a rollback path. Human-gated; deployment is outward-facing and hard to reverse.
---

# Deploy

Safely deploy verified changes to production or target environments with human approval, post-deploy verification, and verified rollback readiness.

Invocation: `/workcell:deploy`
Prompting Reference: [`docs/models/gemini-3.7-flash/prompting.md`](../../runtime/docs/models/gemini-3.7-flash/prompting.md)

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents via Antigravity's `invoke_subagent`, hold the human gates, run `git` / `jj` / `gh` and scripts via `run_command` for branch, merge, and issue-state operations, and read gate output and handoff records using the [`anvil.agent-handoff/v1`](../../runtime/handoff.md) schema. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator enforces mandatory human approval gates, coordinates pre-flight validation, and dispatches the deployer. Per the Gemini 3.7 Flash guide, place critical constraints first, never bypass explicit human sign-offs, and maintain operational transparency.

## Critical Constraints

- **Goal:** Execute a safe, zero-downtime deployment of approved software revisions with verified health checks and an intact rollback plan.
- **Constraints:** Never deploy without explicit human approval. Never skip pre-flight checks or post-deploy health verification. A verified rollback path is mandatory before proceeding.
- **Success Criteria:** Pre-flight checks green, explicit human approval obtained, deployment successful, post-deploy smoke tests passing, and rollback readiness verified.

## Ordered Gates

Execution proceeds through five strict, ordered gates:

1. **approval**: Obtain explicit human approval for release target and version.
2. **preflight**: Run preflight checks ensuring clean tree, passed CI, and release readiness.
3. **release**: Deploy verified build to named target environment.
4. **verification**: Run post-deploy smoke tests and health checks to confirm availability.
5. **rollback readiness**: Confirm rollback artifacts and instructions are verified and intact.

## Procedure

1. **Pre-flight verification.** Dispatch an `integrator` agent via `invoke_subagent` to confirm that all target CI checks pass, the git working tree is clean, and the target release revision is fully green.
2. **Human approval.** Present release details, changelog, target environment, and rollback instructions for explicit human approval. Stop until sign-off is granted. The orchestrator never infers approval, never deploys secrets, and never treats a green pre-flight as permission to deploy.
3. **Execute release.** Dispatch the `deployer` agent via `invoke_subagent` with a brief conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md) to execute the release. Where the release needs a branch of its own, it is `release/<slug>` ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). Tag the release yourself, then publish the GitHub release for that tag:
   ```bash
   gh release create vX.Y.Z --title "<project> vX.Y.Z" --notes-file <notes>
   ```
   from the documenter's release notes. The release title is exactly `<project> vX.Y.Z`: the descriptive strapline belongs to the changelog entry heading, not the title, and the notes never repeat the title as their own first heading. Tagging and publishing a release are git/`gh` operations, not authorship. When the project publishes packages (GitHub Packages, npm, a container registry), that publish is part of this gated deploy — never a separate, unapproved step.
4. **Post-deploy verification.** The deployer agent returns exact commands with `commandId`s, what it observed in the verification window, and whether it rolled back. A claim that the deploy "looks good" is not verification.
5. **Confirm rollback readiness.** Verify that previous revision artifacts and rollback procedures are accessible and ready. A rollback is a successful outcome of the procedure, not a failure of it. Dispatch the `documenter` agent for an ADR on any non-trivial release decision and for the handover entry.

## Boundaries

The orchestrator never infers approval, never deploys secrets, and never treats a green pre-flight as permission to deploy. Deploy targets, credentials, and rollback steps come from the project — never invented. If any post-deployment check fails, trigger rollback immediately rather than attempting hot-fixes in place.

Based on the requirements and constraints above, execute the deploy workflow systematically.
