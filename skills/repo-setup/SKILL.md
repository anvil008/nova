---
name: repo-setup
description: Prepare a new or existing repository with concise project instructions, working verification commands, and appropriate development tooling.
---

Read [shared development instructions](../../instructions/development.md) when applying this skill; reuse them if already loaded in this conversation.


# Repository setup

Inspect purpose, manifests, source layout, instructions, CI, version control, and existing build/test/lint commands before asking questions. Infer routine choices from the repository; ask only for consequential missing decisions. Preserve the chosen stack and runner. Tool availability is not a reason to adopt a new build system.

Read [plugin installation and setup](../../instructions/install.md). Reconcile the shared Workcell conventions into persistent project instructions when requested. Optional helper setup must resolve native support and existing names before copying definitions; optional hooks require explicit trusted config and installed paths.

Create or update concise project instructions covering purpose, entry points, layout, exact verification commands, and non-obvious conventions. Prefer one canonical instruction source with supported native links/imports. Preserve and reconcile divergent existing instructions rather than blindly overwriting files or replacing them with symlinks.

Follow the user's jj/trunk preference unless the repository explicitly requires plain Git. Inspect existing state before authorized colocated initialization. Reuse a suitable workspace. Global installation and unrelated CI replacement are separate scope; a setup request does not authorize unrelated feature implementation.

Reuse existing formatters, linters, and test runners. Add missing executable checks when setup scope permits. Optional post-edit hooks may run explicitly configured format/lint commands; they do not prove test correctness or independent review. Do not install sealed-test guards as a hidden prerequisite.

Run the documented commands from the documented directory. Repair setup defects within scope; distinguish missing dependencies, existing failures, and checks not run. Report changed files, working commands, hook activation state, remaining decisions, and actual readiness. Apply one proportional plan in this conversation; no survey or implementation agent is required.
## Report and output format

Write Markdown by default. Generate HTML only when the user explicitly requests a visual or HTML report; do not ask a routine format question. Reuse a combined report where practical instead of generating one per consulted skill. Honor explicit artifact paths/formats and keep small in-conversation work proportional.

Default path: `docs/reports/repo-setup<NN>-<YYYYMMDD>-<title-slug>.md` in the target repository. Allocate the lowest unused positive number for this type across formats, padded to at least two digits. Use the creation date and a lowercase ASCII title slug, replacing non-alphanumeric runs with hyphens and limiting it to 60 characters at a word boundary. Retain the same basename and creation date when revising a confirmed matching artifact; never overwrite an unrelated report.

Use a descriptive title as the Markdown H1. Include the task-specific outcomes above, source references/revisions, actual verification commands and results, remaining gaps, and delivery state. Do not fabricate evidence or label proposed work completed. Check headings, links, and factual claims. Return a concise outcome and the absolute artifact path.

For a requested visual report, read [assets/report.html](assets/report.html) relative to this skill, or an explicitly supplied template. Use the same basename with `.html`; reuse existing Markdown evidence, and keep any companion formats consistent. Preserve the Foundry Zero layout, numbered sections, sidebar, themes, and print styling. Replace placeholders, escape content, and keep CSS/diagrams inline with accessible labels. Verify desktop/mobile rendering in an available browser or disclose the visual-check gap. A missing HTML asset matters only when HTML is requested. Report creation does not authorize serving, publishing, or merging.

For substantial interrupted work, update the existing task checkpoint with decisions, source/workspace state, evidence, active workers, and the next action. On resume, inspect current state before reusing that evidence; do not restart the workflow from its first step.
