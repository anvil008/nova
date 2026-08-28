---
name: deploy
description: Ship a verified change safely — pre-flight checks, versioning, CI/CD, an approved deploy, post-deploy verification, and a rollback path. Human-gated; deployment is outward-facing and hard to reverse.
---

# Deploy

Take verified, merged code to a running environment — safely and reversibly. The primary agent owns the gate and is the sole release authority.

## Human gate

Deployment is outward-facing and hard to reverse. **Never deploy without explicit approval**, and approval for one deploy is not standing. Production deploys always require a fresh, explicit go. Never echo secrets; confirm the target (staging vs prod) before every deploy.

## Procedure

1. **Pre-flight.** Full test suite green on the target commit; clean working tree; correct branch; the diff contains no secrets; migrations and dependency/config changes are accounted for. Stop if any fails.
2. **Version + changelog.** Bump semver, update the `CHANGELOG` and release notes (via the `docs` agent), tag the release.
3. **CI/CD.** Ensure or adjust the pipeline; any config/workflow code goes through the `builder` (test-first where testable).
4. **Approve → deploy.** After explicit human approval, deploy via the project's real mechanism; record the exact command and target.
5. **Verify.** Run health/smoke checks; watch error rates, metrics, and logs for a bounded window; confirm the new version is actually serving.
6. **Rollback.** Know the rollback command *before* deploying; on any failed check, roll back immediately and record what happened.
7. **Record.** Write an ADR for a non-trivial release decision and a handover/changelog entry (via the `docs` agent).

## Boundaries

The primary agent never infers approval, never deploys secrets, and never treats a green pre-flight as permission to deploy. Deploy targets, credentials, and rollback steps come from the project — never invented.
