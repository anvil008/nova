---
name: deploy
description: Ship a verified change safely — pre-flight checks, versioning, CI/CD, an approved deploy, post-deploy verification, and a rollback path. Human-gated; deployment is outward-facing and hard to reverse.
---

# Deploy

Prepare and release the exact verified source to the named environment. The orchestrator owns scope, user decisions, dispatch, and final evaluation. Specialists perform source changes and verification; team size follows useful work and explicit user constraints. See [ADR 0029](../../docs/adr/0029-composable-workflows-and-native-research.md).

## Human gate

Deployment requires explicit authorization naming the target environment and exact final commit. Reuse applicable authorization already supplied for that target and commit; a different commit or target needs a new decision. A green preflight is evidence, not release permission. Production releases require an explicit go. Never echo secrets.

## Source changes

Route authorized version changes, CI pipelines, build files, and source configuration through [build](../build/SKILL.md), carrying existing requirements and decisions. Package manifests and version constants are source configuration; a documenter does not edit them. Build establishes workspace isolation, independently protected tests, implementation, review, relevant documentation, and final combined verification. Do not dispatch an unprepared builder directly.

## Procedure

1. **Prepare the release source.** Inspect the requested target and source, version policy, existing CI/CD, and rollback mechanism. If a semver bump or pipeline change is required, use the shared build path above. Reuse the verified source otherwise. Relevant CHANGELOG and migration-guide changes are documenter assignments inside build and must be included before its final verification. A release-specific branch uses `release/<slug>` ([workspaces](../../docs/workspaces.md)).
2. **Prepare release notes.** Dispatch documenters for prose artifacts only, using [`agents/handoff.md`](../../agents/handoff.md) and `anvil.agent-handoff/v1`. Notes contain a short summary of what the release delivers, the changelog entries for this version, and breaking-change or upgrade callouts. The release title is exactly `<project> vX.Y.Z`; the descriptive strapline belongs in the changelog heading. Notes do not repeat the title as their first heading. Verify CI against the exact combined source, including version and documentation changes; capture that immutable commit.
3. **Authorize the concrete release.** Present the final source commit, target, version, notes, publishing actions, and rollback steps. Obtain any missing authorization before tagging, publishing a GitHub release or package, or deploying. Earlier approval of the base commit does not authorize a newly built commit automatically.
4. **Preflight, publish, and deploy.** Dispatch deployers with the final commit, target, approval, checks, and verification window. Confirm preflight and rollback readiness before release. Tag the approved commit and publish its release with `gh release create vX.Y.Z --target <approved-commit> --title "<project> vX.Y.Z" --notes-file <notes>` when those actions are authorized. Package publishing belongs to this gated release. Use the project's actual commands and targets; never invent them.
5. **Verify and recover.** Deployer checks the running release throughout the specified window and executes the rollback procedure on failure. Return command IDs, observed health, the deployed source, and any rollback result. Report a rollback as recovery rather than claiming the intended release succeeded.
6. **Record the handover.** Documenters record release evidence and non-trivial decisions. Keep reports outside the tested source or deliver later repository documentation through its own validated docs change. Do not add an unverified source commit to the completed release.

## Boundaries

The orchestrator judges command-linked evidence and preserves user authorization. Source changes use build; release prose uses documenters; deployers operate the named target. No source mutation, model summary, or stale green result can replace verification of the final release commit.
