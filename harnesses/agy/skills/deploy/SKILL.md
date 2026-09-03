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
2. **Human approval.** Present release details, changelog, target environment, and rollback instructions for explicit human approval. Stop until sign-off is granted.
3. **Execute release.** Dispatch the `deployer` agent via `invoke_subagent` to trigger deployment pipelines or commands to the approved target environment.
4. **Post-deploy verification.** Run automated health checks, smoke test suites, and monitoring validations against the target deployment.
5. **Confirm rollback readiness.** Verify that previous revision artifacts and rollback procedures are accessible and ready in case an operational anomaly is detected.

## Boundaries

Deployment is outward-facing and high-impact. Never infer approval from silence or previous runs. If any post-deployment check fails, immediately notify the human and prepare the rollback path.

Based on the requirements and constraints above, execute the deploy workflow systematically.
