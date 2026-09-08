---
name: refactor
description: Simplify existing code while preserving observable behavior, interfaces, and dependencies; examine, implement authorized changes, verify, and produce a Markdown report.
---

Read [shared development instructions](../../instructions/development.md) when applying this skill; reuse them if already loaded in this conversation.


# Refactor

Use the current conversation and existing decisions. Follow persistent scope, delegation, verification, and report conventions; this skill requires no custom agent.

# Refactoring expertise

Favor changes that make an existing responsibility easier to understand or modify. Ground each candidate in source evidence and a concrete benefit. Line-count reduction alone is not evidence of better design.

## Decide what deserves changing

- Trace callers, configuration, dynamic registration, and supported entry points before declaring code dead. An unused-looking public symbol may still be an external contract.
- Consolidate duplication when the copies represent the same responsibility and should evolve together. Similar syntax with different reasons to change can deserve separate implementations.
- Remove a wrapper when it adds no policy, translation, invariant, or useful boundary. Prefer an interface that hides meaningful complexity over layers that merely forward calls.
- Simplify control flow when it clarifies invariants. Extraction is worthwhile when the new name and boundary explain a responsibility; moving statements into another file is not inherently an improvement.
- Preserve established architecture and recorded decisions unless the assigned scope includes revisiting them. Avoid speculative extensibility, blanket rewrites, and pattern-driven churn.

## Preserve the observable contract

Identify public interfaces, returned values, errors, file formats, side effects, ordering, resource lifetimes, and relevant concurrency behavior. Preserve dependencies and compatibility unless the user explicitly broadens the task. Treat an apparent bug as existing behavior to disclose, not an implicit license to fix it.

Keep existing assertions as evidence. Do not weaken tests or rewrite expected outputs to conceal a change in behavior. Add characterization coverage when a meaningful gap prevents verification; change test wiring only when an internal move requires it, preserving assertions and explaining why. A stricter project or user constraint takes precedence.

## Choose convincing evidence

Use relevant existing tests plus representative public entry points, output comparisons, or characterization cases where tests alone are insufficient. Compare baseline and candidate under equivalent conditions. Normalize only understood nondeterminism and state exactly what was excluded. Test success supports preservation but does not prove every untested contract.

Investigate regressions before continuing dependent edits. Known unrelated baseline failures can remain when the changed behavior is still verifiable; disclose them and honor project-required delivery checks. Prefer small coherent changes whose impact can be assessed and reversed.

## Execution process

1. Examine the requested scope, its callers, contracts, and existing tests. Identify concrete simplification candidates and the evidence for each. Respect an audit-only or plan-only request; it authorizes investigation and the report, not product edits.
2. Develop one ordered task breakdown. Each task states the relevant files, intended simplification, behavior to preserve, dependencies if real, and verification. Keep it in the thread unless a durable plan would help resume substantial work. Select worthwhile tasks within scope; explain rejected or deferred candidates. No worthwhile refactor is a valid result.
3. Establish the relevant baseline, then implement each coherent task when implementation is authorized. Verify incrementally and update task outcomes. Avoid unrelated fixes, dependency changes, and opportunistic scope expansion. Pause dependent work for a material unresolved scope decision, not routine implementation choices.
4. Inspect the combined diff and run applicable final checks. Reuse unchanged evidence. Separate existing failures from regressions and unverified behavior. Distinguish self-review from independent review; if independent review is required, arrange it using available authorized delegation, or disclose the unmet review requirement. Do not claim self-review is independent.
5. Produce the report following the output convention below. Include scope and source revisions, findings, one task breakdown with actual outcomes, representative before/after examples, verification commands and results, limitations, deferred work, and actual delivery state. For incomplete work, mark the report partial; for no changes, explain why. Never fabricate success metrics or test results.

Return a concise summary: completed/deferred tasks, exact verified source revision when available, check outcomes and remaining gaps, delivery state, and the absolute HTML report path. Link detailed logs only where they support review or resumption. If the final report is added after source verification, distinguish the tested source revision from any later report-only revision.

## Report and output format

Write Markdown by default. Generate HTML only when the user explicitly requests a visual or HTML report; do not ask a routine format question. Reuse a combined report where practical instead of generating one per consulted skill. Honor explicit artifact paths/formats and keep small in-conversation work proportional.

Default path: `docs/reports/refactor<NN>-<YYYYMMDD>-<title-slug>.md` in the target repository. Allocate the lowest unused positive number for this type across formats, padded to at least two digits. Use the creation date and a lowercase ASCII title slug, replacing non-alphanumeric runs with hyphens and limiting it to 60 characters at a word boundary. Retain the same basename and creation date when revising a confirmed matching artifact; never overwrite an unrelated report.

Use a descriptive title as the Markdown H1. Include the task-specific outcomes above, source references/revisions, actual verification commands and results, remaining gaps, and delivery state. Do not fabricate evidence or label proposed work completed. Check headings, links, and factual claims. Return a concise outcome and the absolute artifact path.

For a requested visual report, read [assets/report.html](assets/report.html) relative to this skill, or an explicitly supplied template. Use the same basename with `.html`; reuse existing Markdown evidence, and keep any companion formats consistent. Preserve the Foundry Zero layout, numbered sections, sidebar, themes, and print styling. Replace placeholders, escape content, and keep CSS/diagrams inline with accessible labels. Verify desktop/mobile rendering in an available browser or disclose the visual-check gap. A missing HTML asset matters only when HTML is requested. Report creation does not authorize serving, publishing, or merging.

For substantial interrupted work, update the existing task checkpoint with decisions, source/workspace state, evidence, active workers, and the next action. On resume, inspect current state before reusing that evidence; do not restart the workflow from its first step.
