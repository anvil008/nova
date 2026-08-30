# 9. Skills are dispatch contracts

## Status

Accepted

## Context

ADR 0007 made the primary agent a pure orchestrator, but the skills still described that boundary in different words and mixed three audiences: the operator holding gates, the dispatched agent producing artifacts, and the maintainer preserving renderer internals. Some agent modes existed only in orchestration prose that dispatched agents are forbidden to read. Entry workflows promised one pull request to `main` even though `build` opened and merged one default-branch pull request per issue. Performance work also reused a RED-test seal that cannot fire when observable behaviour and its tests must remain green.

Those seams made locally plausible procedures compose into contradictory workflows. They also left critical dispatch parameters implicit, so the receiving agent could not tell whether it was running a baseline, a behaviour-preserving refactor, or a review-fix iteration.

## Decision

Every orchestration skill uses one canonical boundary paragraph and acts as a dispatch-and-gate contract. Operator procedure stays in `SKILL.md`; artifact schemas, naming rules, reconciliation shapes, and renderer/template maintenance rules live in linked `references/` files read by the agent or maintainer that owns them.

`build` has two explicit pull-request shapes. Multi-PR mode remains the default. Single-PR mode creates `<planId>-integration` from `trunk()`, passes it through the handoff `base` field, merges mechanically verified per-issue pull requests into it, and finally opens one pull request from that branch to `main`. Default-branch closing lines are repeated in the final pull request.

Execution variants are data in `agents/handoff.md`, not hidden implications in orchestration prose. Dispatch briefs carry `mode: baseline`, `mode: refactor`, or `mode: loop` with their fixed semantics, and carry runtime review setup through `devServer`. Behaviour-preserving performance and refactor work uses a green baseline plus an untouched-tests diff instead of a fabricated RED seal; observable behaviour changes return to the ordinary planner and test-author path.

## Consequences

The primary agent can operate every workflow without inspecting target-project contents, while dispatched agents receive all information needed to select their contract. Entry workflows that promise one PR now share one integration mechanism, and GitHub issue closure remains correct on the default branch.

Skills become shorter for operators and more precise for their specialist readers. Tests must pin moved maintenance prose in the reference file rather than duplicate it in `SKILL.md`, and additions to a dispatch mode or artifact contract require updating the handoff schema or the owning reference instead of adding an informal skill-only exception.
