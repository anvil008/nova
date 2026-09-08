---
name: docs
description: Write or audit scoped project documentation against current source and reader needs, validate it, and produce a Markdown change report.
---

Read [shared development instructions](../../instructions/development.md) when applying this skill; reuse them if already loaded in this conversation.


# Docs

Use the current conversation and existing decisions. Follow persistent scope, delegation, verification, and report conventions; this skill requires no custom agent.

# Documentation expertise

Write for the intended reader and task. Inspect the behavior being documented and use current source, runnable commands, or supplied primary evidence for factual claims. Name uncertainty rather than inventing commands, APIs, output, or capabilities.

Update the existing canonical page rather than creating competing documentation. Preserve requested structure, terminology, and repository conventions. A page edit does not authorize a repository-wide reorganization. Keep global working conventions, repository instructions, and task expertise in their appropriate locations; do not install or rewrite global configuration as a side effect.

For README work, lead with purpose and the shortest viable quickstart. Move deeper explanation into existing documentation where appropriate. Add a compact visual when relationships benefit from it, with meaningful labels and a nearby text explanation. Prefer existing diagram tooling; do not introduce a rendering stack merely to decorate a page.

Use plain, concise prose and examples that reflect real entry points. Keep related README, API docs, changelog, and architecture notes aligned only where the requested change affects them. Record a new ADR only for an actual architectural decision; follow repository numbering and status/context/decision/consequences conventions. Preserve accepted decision history and supersede it when appropriate.

Structural checks do not prove prose is true. Validate changed claims against source and relevant examples against actual behavior. Do not run destructive, external, or expensive example commands without the relevant authorization. Product code and tests are read-only during documentation work; report a discovered product defect rather than repairing it as documentation work.

When a change makes an actual architectural decision, record it in `docs/adr/NNNN-title.md` using the repository's numbering and Status, Context, Decision, and Consequences sections. Preserve accepted ADRs; supersede them with a new decision record when necessary. Routine implementation choices do not require an ADR. Keep affected README, API docs, changelog, and architecture notes aligned within scope, before final verification. Do not document a proposed spec or plan as an accepted decision.

## Execution process

1. Identify the audience, requested outcome, allowed documentation paths, and authoritative source revision. Inspect the existing pages and relevant code. For an audit-only request, investigate and report without editing documentation.
2. Develop one proportional task breakdown connecting each requested documentation change to its source evidence and validation. Reuse an existing plan and avoid unrelated standardization.
3. Make the authorized edits using the project's document format. Markdown remains the default for project prose; the completion report is a separate artifact. Preserve existing useful content and links.
4. Run applicable docs lint/build/link checks and relevant example or generated-diagram checks. Use the Nova docs checker only when it exists in the target project and applies; do not assume this repository's tooling exists everywhere. Inspect rendered pages at useful viewport sizes. Separate source accuracy, structural validity, and visual checks.
5. Inspect the final diff for unintended product edits and unresolved claims. Produce a Markdown report covering changed pages, reader benefit, task outcomes, source references, representative before/after prose, validation evidence, and limitations. Follow the user's delivery authorization; do not initiate another docs workflow or an intermediate PR.

## Report and output format

Write Markdown by default. Generate HTML only when the user explicitly requests a visual or HTML report; do not ask a routine format question. Reuse a combined report where practical instead of generating one per consulted skill. Honor explicit artifact paths/formats and keep small in-conversation work proportional.

Default path: `docs/reports/docs<NN>-<YYYYMMDD>-<title-slug>.md` in the target repository. Allocate the lowest unused positive number for this type across formats, padded to at least two digits. Use the creation date and a lowercase ASCII title slug, replacing non-alphanumeric runs with hyphens and limiting it to 60 characters at a word boundary. Retain the same basename and creation date when revising a confirmed matching artifact; never overwrite an unrelated report.

Use a descriptive title as the Markdown H1. Include the task-specific outcomes above, source references/revisions, actual verification commands and results, remaining gaps, and delivery state. Do not fabricate evidence or label proposed work completed. Check headings, links, and factual claims. Return a concise outcome and the absolute artifact path.

For a requested visual report, read [assets/report.html](assets/report.html) relative to this skill, or an explicitly supplied template. Use the same basename with `.html`; reuse existing Markdown evidence, and keep any companion formats consistent. Preserve the Foundry Zero layout, numbered sections, sidebar, themes, and print styling. Replace placeholders, escape content, and keep CSS/diagrams inline with accessible labels. Verify desktop/mobile rendering in an available browser or disclose the visual-check gap. A missing HTML asset matters only when HTML is requested. Report creation does not authorize serving, publishing, or merging.

For substantial interrupted work, update the existing task checkpoint with decisions, source/workspace state, evidence, active workers, and the next action. On resume, inspect current state before reusing that evidence; do not restart the workflow from its first step.
