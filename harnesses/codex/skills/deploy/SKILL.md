---
name: deploy
description: Ship a verified change safely — pre-flight checks, versioning, CI/CD, an approved deploy, post-deploy verification, and a rollback path. Human-gated; deployment is outward-facing and hard to reverse.
---

# Deploy

Take verified, merged code to a running environment — safely and reversibly.

Invocation: `/workcell:deploy`
Prompting Reference: [`docs/models/gpt-5.6-sol/prompting.md`](../../runtime/docs/models/gpt-5.6-sol/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you hold the human gates, run VCS and release commands using shell execution, dispatch specialists using `spawn_agent`, and read gate output and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Safely ship verified code to a designated running environment with verified health checks and an immediate rollback path.
- **Constraints and Boundaries:** Never deploy without explicit human approval naming the exact commit and environment target. Never echo or persist secrets. Roll back immediately upon verification failure.
- **Success Criteria:** Pre-flight checks pass, release succeeds, post-deploy verification window observes healthy operations, and rollback readiness is confirmed.

## Ordered Gates

Execution proceeds through five strict, ordered gates:

1. **approval**: Human gate explicitly approves deployment naming target and commit.
2. **preflight**: Deployer agent verifies target readiness, credentials, and environment state.
3. **release**: Deployer performs staged release execution to the target.
4. **verification**: Post-deploy health checks run within the verification window.
5. **rollback readiness**: Tested rollback command confirmed ready and executed immediately if checks fail.

## Human gate

Deployment is outward-facing and hard to reverse. **Never deploy without explicit approval**, and approval for one deploy is not standing. Production deploys always require a fresh, explicit go. Never echo secrets; confirm the target (staging vs prod) before every deploy.

## Procedure

1. **Version and changelog.** Dispatch a `documenter` via `spawn_agent` to bump semantic version, update `CHANGELOG`, and generate release notes. Tag the release and publish the GitHub release with `gh release create vX.Y.Z --title "<project> vX.Y.Z" --notes-file <notes>`.
2. **CI/CD pre-check.** Verify that CI/CD pipelines are passing for the target release commit.
3. **Approval checkpoint.** Stop for explicit human approval naming the target environment (e.g., staging vs prod) and the exact commit hash before triggering release.
4. **Preflight and release.** Dispatch a `deployer` via `spawn_agent` with target, commit, and approval details. The deployer verifies target state, executes the release, and confirms rollback command readiness.
5. **Post-deploy verification.** Run health checks throughout the verification window. If any verification step fails, trigger the immediate rollback procedure.
6. **Record handover.** Dispatch a `documenter` via `spawn_agent` to record architectural decision records (ADRs) for non-trivial release events.

## Boundaries

The orchestrator never infers approval, never deploys secrets, and never treats a green pre-flight as permission to deploy. Deploy targets, credentials, and rollback steps come from the project — never invented.

## Harness Limitations

API-only model controls (such as dynamic request-level reasoning effort or pro mode toggles) and API-only orchestration features are unsupported in Codex skill prompts; execution relies on native harness tooling and specialist dispatch.
