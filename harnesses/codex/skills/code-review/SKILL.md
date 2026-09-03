---
name: code-review
description: Run a multi-lens, adversarially verified review of a pull request, diff, or change-set before merge — including a read-only frontend lens that inspects rendered UI across a fixed viewport matrix for responsiveness, accessibility, and visual QA.
---

# Code Review

Review one pull request, diff, or integrated change-set before merge.

Invocation: `/workcell:code-review`
Prompting Reference: [`docs/models/gpt-5.6-sol/prompting.md`](../../runtime/docs/models/gpt-5.6-sol/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_agent` with native specialist routing from `agents/models.json`, hold human gates, run VCS and shell operations, and read gate output and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Deliver an evidence-backed, multi-lens code review where every candidate finding is independently substantiated against concrete failure scenarios.
- **Constraints and Boundaries:** Reviewers and verifiers are strictly read-only and never edit code. Verification must be adversarial and independent (never verified by the discovering agent). Filing GitHub issues via `--apply` requires explicit human approval.
- **Success Criteria:** Deduplicated findings merged into structured JSON, self-contained HTML report generated, and deterministic verdict (`block` / `approve-with-nits` / `approve`) rendered.

## Ordered Gates

Execution proceeds through four strict, ordered gates:

1. **lens reviews**: Select applicable lenses based on file types and fan out independent read-only reviewers via `spawn_agent`.
2. **adversarial verification**: Dispatch fresh, independent skeptics to substantiate or refute candidate findings against code evidence.
3. **deduplication**: Merge and deduplicate findings deterministically via `merge_findings.py`.
4. **report**: Synthesize verified findings into structured JSON, HTML report, and optional reconciled GitHub issues.

## Procedure

1. **Lens selection and fan-out.** Select applicable lenses from changed files: `correctness` and `tests` always; `security`, `performance`, `api-contract`, `backend`, `integrations`, or `frontend` when applicable. The frontend lens follows [`references/frontend-review.md`](references/frontend-review.md). Spawn one read-only `reviewer` per selected lens in parallel via `spawn_agent`. Each reviewer operates on the same change-set and returns structured findings without modifying code.
2. **Merge and adversarial verification.** Collect per-lens JSON findings and deduplicate by `(file, line, claim)` using `skills/code-review/scripts/merge_findings.py --dedupe-only`. For each candidate finding, dispatch an independent `reviewer` via `spawn_agent` that did not author the finding to attempt refutation against the code. Run the verification merge:

   ```bash
   python3 skills/code-review/scripts/merge_findings.py --verification verification.json correctness.json tests.json security.json
   ```

   Findings that cannot be substantiated are dropped and recorded in `dropped`.
3. **Synthesize report.** Render merged JSON into a self-contained HTML report conforming to [`references/report-rendering.md`](references/report-rendering.md):

   ```bash
   python3 skills/code-review/scripts/render_review.py review.json review.html --title "Review summary" --repo owner/name --subject "PR #123"
   ```

4. **Reconcile GitHub issues (optional).** Stop for explicit human approval before running `--apply`:

   ```bash
   python3 skills/code-review/scripts/reconcile_findings.py review.json --repo owner/name --review-id pr-123 --subject "PR #123" --apply --approved-by "<login>"
   ```

## Offline Demonstration

```bash
PYTHONDONTWRITEBYTECODE=1 python3 skills/code-review/scripts/merge_findings.py --dedupe-only skills/code-review/examples/correctness.json skills/code-review/examples/tests.json skills/code-review/examples/security.json
```

## Harness Limitations

API-only model controls (such as dynamic request-level reasoning effort or pro mode toggles) and API-only orchestration features are unsupported in Codex skill prompts; execution relies on native harness tooling and specialist dispatch.
