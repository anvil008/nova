---
name: code-review
description: Run a multi-lens, adversarially verified review of a pull request, diff, or change-set before merge — including a read-only frontend lens that inspects rendered UI across a fixed viewport matrix for responsiveness, accessibility, and visual QA.
---

# Code Review

Review one pull request, diff, or integrated change-set before merge.

Invocation: `/workcell:code-review`
Prompting Reference: [`docs/models/claude-sonnet-5/prompting.md`](../../runtime/docs/models/claude-sonnet-5/prompting.md)

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents via Claude Code's `Agent` tool, hold human gates, run `git` / `jj` / `gh` and scripts via the `Bash` tool, and read gate output and handoff records using the [`anvil.agent-handoff/v1`](../../runtime/handoff.md) schema. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator selects the lenses, dispatches the reviewers and verifiers, and owns the consolidated verdict.

## Goals and Constraints

- **Goal:** Deliver an evidence-backed, multi-lens code review where every candidate finding is independently substantiated against concrete failure scenarios.
- **Constraints:** Reviewers and verifiers are strictly read-only and never edit code. Verification must be adversarial and independent (never verified by the discovering agent). Filing GitHub issues via `--apply` requires explicit human approval.
- **Success Criteria:** Deduplicated findings merged into structured JSON, self-contained HTML report generated, and deterministic verdict (`block` / `approve-with-nits` / `approve`) rendered.

## Ordered Gates

Execution proceeds through four strict, ordered gates:

1. **lens reviews**: Select applicable lenses based on file types and fan out independent read-only reviewers via the `Agent` tool.
2. **adversarial verification**: Dispatch fresh, independent skeptics to substantiate or refute candidate findings against code evidence.
3. **deduplication**: Merge and deduplicate findings deterministically via `merge_findings.py`.
4. **report**: Synthesize verified findings into structured JSON, HTML report, and optional reconciled GitHub issues.

## Lens Selection and Fan-Out

Use the change-set's **file list** and diffstat to select lenses from its actual risks:

- correctness and tests are always selected;
- security applies when trust boundaries, authentication or authorization, dependencies, secrets, or input handling change;
- performance applies to hot paths, loops, allocations, concurrency, or materially larger data flow;
- api-contract applies when a public surface, wire format, schema, CLI, or compatibility promise changes;
- backend applies when server-side behaviour changes — request handling, business logic, persistence, migrations, jobs, or caching;
- integrations applies when the change crosses a boundary this repository does not own — a third-party API, message broker, webhook, auth provider, or another internal service — where the failure modes are timeouts, retries, partial writes, and contract drift rather than logic errors;
- frontend applies when the change touches user-facing UI — see below.

The fan-out count equals the applicable lenses, never a fixed N. Spawn one read-only `reviewer` per selected lens in parallel via the `Agent` tool. Give each reviewer the same change-set and exactly one lens. Reviewers return structured findings and never edit. Following the Claude Sonnet 5 guide, request comprehensive reporting and defer severity filtering to the merge phase.

### The Frontend Lens

Select `frontend` when the change-set touches rendered UI: `.tsx` / `.jsx` / `.vue` / `.svelte` / `.astro` components, templates (`.html`, `.hbs`, `.ejs`), stylesheets (`.css` / `.scss` / `.less`), Tailwind or design-token config, or static assets those import. A change confined to server code, build config, or tests is not a frontend change — do not select the lens to be thorough, because a lens with nothing to look at produces noise, not coverage.

That reviewer follows [`references/frontend-review.md`](references/frontend-review.md), which is the frontend lens's method rather than a separate review: a static pass over the changed components and styles, then an `agent-browser` pass that resizes through a fixed viewport matrix — 4K (3840×2160), half-tiled 4K (1920×2160), QHD, 1080p, MacBook 16"/15"/13", a small laptop, tablet, and phone — capturing structure, screenshots, and an objective horizontal-overflow check at each. It returns the same envelope as every other lens, with `lens` set to `frontend`, so its findings dedupe, verify, and rank alongside the rest with no special-casing downstream.

The orchestrator sets `devServer` in the dispatch brief to `none`, a URL, or `start: <command>`; production URLs are never passed. The reviewer never asks. An absent field or `none` means the static pass only, and the reviewer records the runtime gap rather than asserting behaviour it never observed.

## Merge and Adversarial Verification

1. Collect the per-lens JSON files and deduplicate by `(file, line, claim)`. `skills/code-review/scripts/merge_findings.py --dedupe-only` chooses the representative by highest severity, highest confidence, then lexicographically smallest `(lens, failureScenario)`. This full tie-break is independent of parallel collection order; the helper then ranks candidates deterministically.
2. Run an independent adversarial verification of every surviving candidate. Dispatch a fresh read-only reviewer via the `Agent` tool that did not originate the candidate, assign its lens and exact claim, and require a skeptic pass that tries to refute it against the code and concrete failure scenario.
3. Record one verification per candidate with `substantiated`, `refutationAttempt`, and `evidence`. Run the helper again via `Bash` with `--verification`:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/code-review/scripts/merge_findings.py --verification verification.json correctness.json tests.json security.json
   ```

   DROP every finding that the independent pass cannot substantiate; missing, duplicate, or extra verification records are errors.

Only verified findings reach the report. The helper ranks `critical`, `high`, `medium`, `low`, then `nit`; `critical` or `high` yields `block`, remaining findings yield `approve-with-nits`, and no findings yields `approve`.

## Report

Return the verified findings ranked by severity and the verdict: `block` / `approve-with-nits` / `approve`. Include the selected lenses and verification evidence. The orchestrator is the sole synthesis and completion authority; reviewer or verifier output is evidence, not the verdict. Deciding what the evidence means is orchestration; producing it is not.

`--verification` emits both `findings` (substantiated) and `dropped` (refuted), each carrying its `verification{refutationAttempt, evidence}`. Refuted candidates are reported rather than discarded: the evidence that killed a plausible finding is what shows the verification pass did work.

### HTML Report

Render the merged JSON into a self-contained report for a human reviewer:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/code-review/scripts/render_review.py review.json review.html   --title "One-line claim of what this review found"   --repo owner/name --subject "PR #4821" --base a91f3c2   --lenses correctness,tests,security --generated-at 2026-08-28T06:40:00Z
```

Only `review.json` and the output path are required; the rest default to honest placeholders. The renderer re-validates the merged JSON strictly and refuses unknown fields, so a hand-edited report cannot silently diverge from the pipeline that produced it.

Maintainers of the renderer and templates follow the [report-rendering contract](references/report-rendering.md).

## GitHub Issues

Verified findings become tracked work the same way an approved plan does: an idempotent, marker-based reconciliation behind an explicit human gate.

```bash
# Preview — read-only. Omit --snapshot to query GitHub read-only instead.
python3 ${CLAUDE_PLUGIN_ROOT}/skills/code-review/scripts/reconcile_findings.py review.json   --repo owner/name --review-id pr-4821 --subject "PR #4821"   --snapshot github-state.json

# Apply — only after a human approves this exact review.
python3 ${CLAUDE_PLUGIN_ROOT}/skills/code-review/scripts/reconcile_findings.py review.json   --repo owner/name --review-id pr-4821 --subject "PR #4821"   --apply --approved-by "<github-login>"
```

**Stop for explicit human approval before `--apply`.** Issues are outward-facing and land in a shared tracker; approval to review is not approval to file. Do not infer approval from silence or from approval of an earlier revision.

`--approved-by` must equal the login `gh` is authenticated as (`gh api user`). A mismatch exits before any write. Apply output records that login as `approvedBy` and the exact approved review bytes as `approvedSha256`.

`--review-id` is the durable identity of this review — a stable lowercase slug you keep across re-runs (`pr-4821`, not a timestamp). Each issue carries `<!-- workcell-review reviewId=<id> finding=<key> severity=<sev> -->`, and that marker is what makes re-running safe.

Identity comes from the last marker in the body. Marker delimiters in quoted review prose are escaped while composing the issue, so an excerpt cannot squat the issue's identity.

A finding's key is a hash of **(file, claim)** — deliberately not the line. Line numbers move whenever anything above them changes, so keying on them would file a duplicate for the same defect after any unrelated edit and strand the original as never-fixed. The line lives in the issue body.

Reconciliation therefore converges rather than accumulates:

| Situation                                                | Action                  |
| -------------------------------------------------------- | ----------------------- |
| Finding has no issue                                     | `create_issue`          |
| Issue exists, content changed                            | `update_issue`          |
| Finding no longer reported — fixed, or refuted on re-run | `close_resolved_issue`  |
| Two issues carry the same marker                         | `close_duplicate_issue` |
| Nothing changed                                          | no actions at all       |

`--min-severity` (default `medium`) sets the filing threshold; `low` and `nit` stay in the report rather than becoming tracker noise. An open issue is only closed as resolved when its recorded severity (from the marker, or the `severity:<sev>` label) is at or above the current `--min-severity`; a stricter threshold filters findings out of the run, it does not fix them, so their issues stay open. Issues are labelled `code-review`, `severity:<sev>`, and `lens:<lens>`; add more with `--label`, and attach them to a milestone with `--milestone`.

Each issue body carries the failure scenario and the independent verification — the refutation attempt and the evidence — so whoever picks it up sees why it is real without re-reading the diff.

## Offline Demonstration

These commands read local fixtures only and have no GitHub or subagent side effects:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B ${CLAUDE_PLUGIN_ROOT}/skills/code-review/scripts/merge_findings.py --dedupe-only skills/code-review/examples/correctness.json skills/code-review/examples/tests.json skills/code-review/examples/security.json
PYTHONDONTWRITEBYTECODE=1 python3 -B ${CLAUDE_PLUGIN_ROOT}/skills/code-review/scripts/merge_findings.py --verification skills/code-review/examples/verification.json skills/code-review/examples/correctness.json skills/code-review/examples/tests.json skills/code-review/examples/security.json
PYTHONDONTWRITEBYTECODE=1 python3 -B ${CLAUDE_PLUGIN_ROOT}/skills/code-review/scripts/render_review.py skills/code-review/examples/expected-review.json /tmp/review.html --repo acme/platform --subject "PR #4821" --lenses correctness,tests,security
PYTHONDONTWRITEBYTECODE=1 python3 -B ${CLAUDE_PLUGIN_ROOT}/skills/code-review/scripts/reconcile_findings.py skills/code-review/examples/expected-review.json --repo acme/platform --review-id pr-4821 --subject "PR #4821" --snapshot skills/code-review/examples/empty-github-snapshot.json
```

Never run `--apply` merely to test the skill. Use snapshot preview for validation.

## Harness Limitations

Native context forks and workflows are omitted with notes in Claude Code; procedures execute sequentially within the primary session.
