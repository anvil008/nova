---
name: debug
description: Reproduce a reported failure and isolate its cause through controlled experiments; repair it when requested and report the evidence in Markdown.
---

Read [shared development instructions](../../instructions/development.md) when applying this skill; reuse them if already loaded in this conversation.


# Debug

Use the current conversation and existing decisions. Follow persistent scope, delegation, verification, and report conventions; this skill requires no custom agent.

# Debugging expertise

Start from the reported symptom and establish an executable reproduction before claiming a cause. Distinguish observation, hypothesis, and demonstrated causality. Source inspection can suggest experiments; it cannot by itself establish an unobserved failure. No reproduction is a valid investigation outcome when attempts and missing conditions are explicit.

Reduce inputs, state, and execution paths to the smallest case that still exhibits the symptom. Form falsifiable hypotheses and prefer controlled experiments that distinguish competing explanations. Record negative results as well as supporting evidence. Change one relevant condition at a time where practical; distinguish environmental failures from product defects.

For web symptoms, reproduce in a real browser and inspect relevant console, network, and page state. Use the available project/browser tooling and its current usage guidance. For regressions, use history or a controlled bisect when a reliable failure oracle exists, preserving the original workspace state. For measured slowdowns, use a supported profiler to attribute cost rather than guessing from code shape.

Measure flaky failures as failures/trials under stated conditions. One successful retry is not evidence of repair. Inspect shared state, test order, timing, and concurrency only as testable candidate causes. Respect the assigned investigation and runtime budget.

Temporary probes, logging, and test cases are allowed for investigation. Track and remove only your temporary changes and processes, preserving pre-existing work. Retain useful reproduction evidence in the report or assigned artifact directory. Do not weaken tests. A diagnosis-only request ends with the findings. When repair is requested, continue in the same conversation: implement the supported correction, add meaningful regression coverage, reproduce the original case again, and run relevant final checks. Reuse the diagnosis instead of starting discovery over; the build skill is optional guidance, not a required handoff.

## Execution process

1. Inspect the reported failure, applicable instructions, source state, and available reproduction evidence. Record expected versus observed behavior and the relevant environment. Reuse a reliable existing reproduction.
2. Create one short investigation task list: reproduction, reduction, distinguishing experiments, and causal verification. Resolve only material missing conditions; continue independent investigation where possible.
3. Run the experiments. Record exact commands or browser actions, inputs, results, and what each rules in or out. If the failure cannot be established, identify what is missing rather than guessing a fix.
4. Link the supported cause to source locations and the introducing revision if found. Describe the proposed repair location and a regression test that would exercise the symptom, keeping product code unchanged for diagnosis-only requests. Mark uncertainty and competing explanations explicitly.
5. Recheck workspace state, remove your temporary instrumentation, and verify pre-existing changes remain. Produce the Markdown diagnosis report with reproduction steps, experiment outcomes, causal evidence, failure rates where relevant, cleanup status, and remaining gaps. If repair was requested, complete and verify it before the final report, including before/after reproduction results and actual repair status.

## Report and output format

Write Markdown by default. Generate HTML only when the user explicitly requests a visual or HTML report; do not ask a routine format question. Reuse a combined report where practical instead of generating one per consulted skill. Honor explicit artifact paths/formats and keep small in-conversation work proportional.

Default path: `docs/reports/debug<NN>-<YYYYMMDD>-<title-slug>.md` in the target repository. Allocate the lowest unused positive number for this type across formats, padded to at least two digits. Use the creation date and a lowercase ASCII title slug, replacing non-alphanumeric runs with hyphens and limiting it to 60 characters at a word boundary. Retain the same basename and creation date when revising a confirmed matching artifact; never overwrite an unrelated report.

Use a descriptive title as the Markdown H1. Include the task-specific outcomes above, source references/revisions, actual verification commands and results, remaining gaps, and delivery state. Do not fabricate evidence or label proposed work completed. Check headings, links, and factual claims. Return a concise outcome and the absolute artifact path.

For a requested visual report, read [assets/report.html](assets/report.html) relative to this skill, or an explicitly supplied template. Use the same basename with `.html`; reuse existing Markdown evidence, and keep any companion formats consistent. Preserve the Foundry Zero layout, numbered sections, sidebar, themes, and print styling. Replace placeholders, escape content, and keep CSS/diagrams inline with accessible labels. Verify desktop/mobile rendering in an available browser or disclose the visual-check gap. A missing HTML asset matters only when HTML is requested. Report creation does not authorize serving, publishing, or merging.

For substantial interrupted work, update the existing task checkpoint with decisions, source/workspace state, evidence, active workers, and the next action. On resume, inspect current state before reusing that evidence; do not restart the workflow from its first step.
