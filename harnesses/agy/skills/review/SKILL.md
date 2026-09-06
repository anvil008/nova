---
name: review
description: "Orchestrate an entire multi-lens review of a PR, diff, change-set, or scoped codebase audit. Assign read-only reviewers, independently verify candidate defects, deduplicate findings, and produce a consolidated verdict and Markdown report. Include correctness, security, frontend, and test lenses as relevant. Selected fixes continue through build only when authorized."
---

# Review

Invocation: `/workcell:review`
Prompting Reference: [`docs/models/gemini-3.8-flash/prompting.md`](../../runtime/docs/models/gemini-3.8-flash/prompting.md)

Dispatch specialists with Antigravity's `invoke_subagent` and use `run_command` for VCS and validation commands. Reasoning effort is session-wide; respect the configured session settings. Use [anvil.agent-handoff/v1](../../runtime/handoff.md) and configured specialist roles. Resolve bundled helper paths from this skill installation; the `skills/...` command examples are relative to the Workcell package root, while the target repository and run directory are supplied by the brief.

Deliver an evidence-backed review of the requested change or code area. The report is the standalone outcome. Produce Markdown by default; render HTML only when explicitly requested.

The orchestrator owns scope, dispatch, user decisions, and the final verdict. Choose reviewers, lenses, and verification work from the actual risks and available runtime capacity. Assignments may cover several bounded lenses or areas; there is no prescribed team size, fan-out, or pass count. Specialists provide independent evidence and do not change the reviewed source.


## Ordered Gates

1. **scope and lenses**: Pin the requested source and choose risk-based review coverage.
2. **evidence verification**: Deduplicate findings and independently substantiate or refute each candidate.
3. **report**: Deliver the verified Markdown report with refutations and coverage limits.
4. **build transition**: Offer selected fixes through build, or continue existing review-and-fix authorization without reasking.

## Scope and evidence

Pin the reviewed source commit and, for a diff, its comparison base. Record the requested scope, exclusions, selected lenses, commands, and coverage gaps in a run directory outside source workspaces. A codebase audit also follows [codebase-audit.md](references/codebase-audit.md); it does not silently become a fix campaign.

Select relevant assurance lenses: correctness, tests, security, performance, api-contract, backend, integrations, and frontend. Match them to concrete risks rather than selecting a team by file count. For rendered UI, use the [frontend method](references/frontend-review.md) and a permitted development server; absent runtime access is a reported coverage gap.

Each reviewer returns the [reviewer contract](../../agents/reviewer/agent.md). Save one `{lens, findings}` envelope per lens, even when a specialist covers several lenses. Every finding needs a reachable failure scenario, a source location, severity, and confidence. Distinguish demonstrated defects from design preferences and unknowns.

## Verify and consolidate

Use [merge_findings.py](scripts/merge_findings.py) to deduplicate by `(file, line, claim)`. Equal candidates resolve by severity, confidence, and lexicographic `(lens, failureScenario)`, so collection order does not change the result.

```bash
python3 -B skills/review/scripts/merge_findings.py --dedupe-only correctness.json tests.json
python3 -B skills/review/scripts/merge_findings.py --verification verification.json correctness.json tests.json > review.json
```

Before the second command, obtain an independent refutation attempt for every surviving candidate from a reviewer who did not originate it. Record `substantiated`, `refutationAttempt`, and `evidence`. Reviewers may verify a bounded batch; independence is about who established the claim, not a fixed number of agents. Missing, duplicate, or extra verification records fail validation. Refuted findings remain visible in `dropped`; they do not enter the actionable findings.

The helper ranks verified findings and derives `block`, `approve-with-nits`, or `approve`. For a codebase audit, this is the severity summary for the covered scope, not a claim that the whole repository is defect-free. The orchestrator evaluates the evidence and states any unresolved uncertainty. A changed source or comparison base needs an updated review before claiming the old verdict applies.

## Report and next action

```bash
python3 -B skills/review/scripts/render_review.py review.json review.md --repo owner/name --subject "Orders export" --base <reviewed-base> --lenses correctness,tests
```

The renderer defaults to Markdown and validates the same merged JSON for both formats. An explicit `.html` output path or `--format html` produces the optional self-contained HTML report. Keep the report's coverage and remaining uncertainties alongside verified and refuted findings. See the [rendering contract](references/report-rendering.md) for maintenance.

Offer the shared [build](../build/SKILL.md) workflow for selected actionable findings. A review request alone authorizes a report, not implementation. When the user already authorized review and fix, continue through build for that scope without asking again; carry the findings, source identity, reproduction evidence, and existing decisions into its brief. The builder never writes or weakens its own acceptance oracle.

Build may reuse [loop_state.py](scripts/loop_state.py) and its [progress record](references/fix-progress.md) while repairing findings. This is an internal helper, not a separate public workflow. The orchestrator chooses useful iterations, respects explicit user limits, and surfaces stalled or unresolved work; a repeated finding set is evidence to assess, not an automatic retry quota.

## Optional issue tracking

File or reconcile issues only when the user authorized those external writes. Review approval does not imply permission to create tracker entries; existing explicit authorization for the exact reviewed scope does not need to be requested again. First prepare a concrete preview:

```bash
python3 -B skills/review/scripts/reconcile_findings.py review.json --repo owner/name --review-id orders-export --subject "Orders export" --snapshot github-state.json
```

Omit `--snapshot` for a read-only live preview. Apply the exact authorized review with `--apply --approved-by <github-login>`; the login must match `gh api user`, and the output binds the approved review bytes. Never use `--apply` as a test.

The durable `workcell-review` marker and `(file, claim)` identity preserve idempotency when lines move. `--min-severity` defaults to `medium`. A stricter threshold filters findings; it does not resolve them, so lower-severity open issues remain open. Existing `code-review`, `severity:<level>`, and `lens:<lens>` labels remain compatible with earlier tracking.
