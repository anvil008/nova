---
name: review
description: Review a diff, pull request, or scoped codebase for concrete defects, verify findings, and produce a Markdown review report.
---

Read [shared development instructions](../../instructions/development.md) when applying this skill; reuse them if already loaded in this conversation.


# Review

When independent delegation is useful and authorized, the optional reviewer helper can inspect a bounded candidate without modifying it. Pass the exact source/base, requirements, evidence, and relevant review criteria; do not dispatch its author as an independent reviewer. Scout may answer a separate discovery question. Native workers or direct review remain available if helper definitions are absent, but direct review must not be mislabeled independent. The main conversation consolidates findings and owns the report and any authorized repairs.

Work in the current conversation. Preserve the user's scope, decisions, and authorization. Delegate independent investigation only when useful and permitted; no prescribed team or role pipeline is required.

1. Pin the reviewed source and comparison base. Identify scope, exclusions, public contracts, and relevant risks. Choose lenses such as correctness, security, tests, compatibility, performance, and frontend behavior from the actual change. An audit is not permission to repair the repository.
2. Trace candidates through callers, data flow, configuration, and tests. Each finding needs a reachable failure scenario, precise source location, impact, severity, confidence, and evidence. Check counterexamples and existing mitigations. Distinguish demonstrated defects from preferences and unresolved questions. Exercise relevant UI interactions in an available browser; report missing runtime access honestly.
3. Deduplicate by underlying cause and rank by impact and likelihood. Try to refute consequential findings before accepting them. Arrange independent review where required or warranted and authorized; do not describe your own second pass as independent. No mandatory refutation agent is needed for every candidate.
4. Report actionable findings first, then coverage, verification commands/results, unresolved or refuted candidates, and a qualified verdict. No findings means none established within the inspected scope, not proof the repository is defect-free. Changes to reviewed source invalidate affected evidence.
5. If review and repair are already authorized, implement selected in-scope corrections, run reproductions and relevant checks, and update resolved/open status. Otherwise leave product source unchanged. Issue creation, remote comments, publication, and merge require corresponding authorization.
## Report and output format

Write Markdown by default. Generate HTML only when the user explicitly requests a visual or HTML report; do not ask a routine format question. Reuse a combined report where practical instead of generating one per consulted skill. Honor explicit artifact paths/formats and keep small in-conversation work proportional.

Default path: `docs/reports/review<NN>-<YYYYMMDD>-<title-slug>.md` in the target repository. Allocate the lowest unused positive number for this type across formats, padded to at least two digits. Use the creation date and a lowercase ASCII title slug, replacing non-alphanumeric runs with hyphens and limiting it to 60 characters at a word boundary. Retain the same basename and creation date when revising a confirmed matching artifact; never overwrite an unrelated report.

Use a descriptive title as the Markdown H1. Include the task-specific outcomes above, source references/revisions, actual verification commands and results, remaining gaps, and delivery state. Do not fabricate evidence or label proposed work completed. Check headings, links, and factual claims. Return a concise outcome and the absolute artifact path.

For a requested visual report, read [assets/report.html](assets/report.html) relative to this skill, or an explicitly supplied template. Use the same basename with `.html`; reuse existing Markdown evidence, and keep any companion formats consistent. Preserve the Foundry Zero layout, numbered sections, sidebar, themes, and print styling. Replace placeholders, escape content, and keep CSS/diagrams inline with accessible labels. Verify desktop/mobile rendering in an available browser or disclose the visual-check gap. A missing HTML asset matters only when HTML is requested. Report creation does not authorize serving, publishing, or merging.

For substantial interrupted work, update the existing task checkpoint with decisions, source/workspace state, evidence, active workers, and the next action. On resume, inspect current state before reusing that evidence; do not restart the workflow from its first step.
