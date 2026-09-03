---
name: code-review
description: Run a multi-lens, adversarially verified review of a pull request, diff, or change-set before merge — including a read-only frontend lens that inspects rendered UI across a fixed viewport matrix for responsiveness, accessibility, and visual QA.
---

# Code Review

Run a multi-lens, adversarially verified review of a pull request, diff, or change-set before merge.

Invocation: `/workcell:code-review`
Prompting Reference: [`docs/models/gemini-3.7-flash/prompting.md`](../../runtime/docs/models/gemini-3.7-flash/prompting.md)

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents via Antigravity's `invoke_subagent`, hold the human gates, run `git` / `jj` / `gh` and scripts via `run_command` for branch, merge, and issue-state operations, and read gate output and handoff records using the [`anvil.agent-handoff/v1`](../../runtime/handoff.md) schema. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator selects the review lenses, coordinates parallel blind reviewer passes, runs independent adversarial verification, and produces the final review verdict. Per the Gemini 3.7 Flash guide, place critical constraints first, demand strict empirical evidence before confirming findings, and avoid speculative issues.

## Critical Constraints

- **Goal:** Conduct a rigorous, multi-lens, adversarially verified code review producing a deterministic verdict (`block`, `approve-with-nits`, or `approve`).
- **Constraints:** Reviewers never edit code. Each lens reviews independently in parallel and blind to the others. Every finding must undergo independent adversarial verification; unverified or refuted claims are discarded (`DROP`). Stop for explicit human approval before applying issue reconciliation.
- **Success Criteria:** Verified lens reviews, empirical adversarial verification, deduplicated findings JSON, and verified HTML review folio.

## Ordered Gates

Execution proceeds through four strict, ordered gates:

1. **lens reviews**: Dispatch parallel reviewer agents across selected assurance lenses.
2. **adversarial verification**: Independently verify each candidate finding to refute false positives.
3. **deduplication**: Merge verified findings and eliminate duplicates via `merge_findings.py`.
4. **report**: Synthesize findings into review verdict, render HTML report, and prompt human for approval.

## Procedure: Lens Selection and Fan-Out

Select applicable lenses, never a fixed N:
- `correctness` and `tests` are always selected.
- `security` applies when touching trust boundaries, authentication, input handling, or cryptography.
- `performance` applies to hot paths, loops, allocations, or database queries.
- `api-contract` applies to changes altering the public surface or wire contracts.
- `frontend` applies when the change touches user-facing UI (templates, styles, client scripts). If the change touches only backend logic, configuration, or documentation, it is not a frontend change. The frontend lens follows [references/frontend-review.md](references/frontend-review.md) using `agent-browser` against an isolated `devServer`.

Spawn one read-only `reviewer` agent per lens in parallel via `invoke_subagent`. Reviewers inspect the diff and return candidate findings identified by `(file, line, claim)` with code citations and concrete failure scenarios.

## Adversarial Verification

Candidate findings undergo independent adversarial verification. An independent verifier actively tries to refute the claim:
- If the verifier cannot reproduce or confirms the claim is a false positive, the finding is marked `DROP`.
- If the claim is substantiated, it is confirmed with recorded severity (`critical`, `high`, `medium`, `low`, or `nit`).

## Deduplication and Report

1. Deduplicate confirmed findings across lenses using `merge_findings.py`:
   ```bash
   python3 -B skills/code-review/scripts/merge_findings.py --verification review-lens-*.json > review.json
   ```
2. The orchestrator produces the sole synthesis and determines the verdict:
   - `block`: At least one substantiated critical or high finding.
   - `approve-with-nits`: Only low or nit findings remain.
   - `approve`: Zero findings remain.
3. Render the review report following the [report-rendering contract](references/report-rendering.md):
   ```bash
   python3 -B skills/code-review/scripts/render_review.py review.json report.html
   ```

## Issue Reconciliation and Approval Gate

When converting findings into tracked GitHub issues:
- Use `reconcile_findings.py` with `--review-id <slug>` and `--snapshot <state.json>` to preview actions.
- Stop for explicit human approval before creating or closing issues.
- Never run `--apply` merely to test the skill.
- Only with explicit human approval:
  ```bash
  python3 -B skills/code-review/scripts/reconcile_findings.py review.json --repo <owner/name> --review-id <slug> --apply --approved-by "<login>"
  ```
- Use `workcell-review reviewId` metadata to track provenance and ensure `close_resolved_issue` safely closes resolved findings. The matching key is deliberately not the line number, ensuring stability across code edits.

## Boundaries

Reviewers never perform edits. Never accept unverified claims or assume a bug exists without a reproducible path. Never bypass human approval for GitHub issue updates.

Based on the requirements and constraints above, execute the code-review workflow systematically.
