---
name: deploy
description: Prepare and execute an authorized release to a named environment, verify the deployed version and health, and recover using the agreed rollback procedure.
---

Read [shared development instructions](../../instructions/development.md) when applying this skill; reuse them if already loaded in this conversation.


# Deploy

Identify the environment, source candidate, version policy, release commands, credentials availability, and rollback mechanism. Reuse verified source and applicable authorization. Prepare needed in-scope version, release-note, or pipeline changes before presenting the concrete release for any missing approval. No mandatory specialist handoffs are required.

Bind release actions to the exact final candidate and target. Existing authorization applies according to its scope; do not ask again when it already covers the action. A green preflight does not grant publication or production-deployment permission. Never expose credentials in commands, logs, or reports.

Release notes describe delivered behavior and breaking changes. Follow Workcell's title convention `<project> vX.Y.Z`; put a descriptive strapline in the changelog, and do not repeat the title as the notes' first heading. Use the project's actual tag, package, and deployment commands.

Before release, verify CI and artifacts against final source. Inspect migration sequencing, compatibility, rollout health criteria, observation window, and recovery steps. Do not assume application rollback reverses a destructive database migration. Resolve missing operational decisions before the affected action.

Execute the authorized release and verify the running version plus meaningful health/user behavior throughout the agreed window. On failure, halt expansion and follow the authorized recovery procedure; identify any concrete recovery action needing additional authority. Report failed rollout and recovery honestly rather than claiming the intended deployment succeeded.

Record source/artifact identity, target, version, commands, observed health, recovery outcome, and actual release state. Keep later report-only changes distinct from the deployed candidate. Previous deployment authorization does not imply permission to release again.
## Report and output format

Write Markdown by default. Generate HTML only when the user explicitly requests a visual or HTML report; do not ask a routine format question. Reuse a combined report where practical instead of generating one per consulted skill. Honor explicit artifact paths/formats and keep small in-conversation work proportional.

Default path: `docs/reports/deploy<NN>-<YYYYMMDD>-<title-slug>.md` in the target repository. Allocate the lowest unused positive number for this type across formats, padded to at least two digits. Use the creation date and a lowercase ASCII title slug, replacing non-alphanumeric runs with hyphens and limiting it to 60 characters at a word boundary. Retain the same basename and creation date when revising a confirmed matching artifact; never overwrite an unrelated report.

Use a descriptive title as the Markdown H1. Include the task-specific outcomes above, source references/revisions, actual verification commands and results, remaining gaps, and delivery state. Do not fabricate evidence or label proposed work completed. Check headings, links, and factual claims. Return a concise outcome and the absolute artifact path.

For a requested visual report, read [assets/report.html](assets/report.html) relative to this skill, or an explicitly supplied template. Use the same basename with `.html`; reuse existing Markdown evidence, and keep any companion formats consistent. Preserve the Foundry Zero layout, numbered sections, sidebar, themes, and print styling. Replace placeholders, escape content, and keep CSS/diagrams inline with accessible labels. Verify desktop/mobile rendering in an available browser or disclose the visual-check gap. A missing HTML asset matters only when HTML is requested. Report creation does not authorize serving, publishing, or merging.

For substantial interrupted work, update the existing task checkpoint with decisions, source/workspace state, evidence, active workers, and the next action. On resume, inspect current state before reusing that evidence; do not restart the workflow from its first step.
