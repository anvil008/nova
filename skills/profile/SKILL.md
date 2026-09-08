---
name: profile
description: Measure representative workloads, identify bottlenecks, and verify authorized optimizations with comparable measurements and a Markdown report.
---

Read [shared development instructions](../../instructions/development.md) when applying this skill; reuse them if already loaded in this conversation.


# Profile

Use the current conversation and existing decisions. Follow persistent scope, delegation, verification, and report conventions; this skill requires no custom agent.

# Profiling expertise

Use the project's benchmark harness or supported profiler over a representative reproducible project command. Pin the measured source revisions and identify inputs or dataset, runtime settings, machine, background load, warmup treatment, and exact commands. Keep raw samples and profiles in an assigned artifact directory outside source where practical.

Separate three questions: a baseline measures starting behavior; bottleneck analysis attributes measured costs to source; comparison evaluates supplied baseline and candidate under comparable conditions. A baseline does not require a candidate, and an observed hot path is not itself proof that a proposed optimization will help.

Repeat measurements within the user's runtime budget to characterize variability. Report sample count, median, and spread or uncertainty with units and excluded warmups. Retain raw samples and explain exclusions. Compare equivalent inputs, commands, machines, load, and runtime conditions; interleave baseline and candidate when it reduces drift. Avoid concurrent measurements that compete for the same resources.

Never describe one timing as a reliable distribution or a difference within measurement noise as a proven improvement. If conditions differ materially, qualify the comparison or obtain comparable evidence. State whether higher or lower is better and make any percentage calculation traceable. Do not extrapolate microbenchmarks to end-to-end performance.

Check correctness for measured source. Existing failures remain visible; faster incorrect output cannot support a successful optimization claim. Identify time, allocations, I/O, or contention with profiles and source locations. Separate measured attribution from hypotheses and expected trade-offs.

When a representative repeatable workload is unavailable, explain the measurement gap and retain any defensible profiling observations. Do not invent an ad-hoc timing script and call it an established baseline. For measurement-only requests, keep product code, tests, and configuration unchanged. Harness creation and permanent instrumentation need implementation scope. When optimization is requested, use the measured bottleneck to implement a scoped candidate, verify correctness, and repeat comparable measurements in the same conversation. Preserve baseline evidence; no separate implementation agent is required.

## Execution process

1. Identify the performance question, source revision(s), workload, correctness criteria, commands, and measurement budget. Inspect the existing harness and related code.
2. Make one short measurement task list with configurations, warmups, sampling approach, artifact paths, and relevant environment controls. Keep unrelated workloads out of scope.
3. Run correctness checks and collect repeated measurements and profiles. Record conditions and raw results; do not hide outliers or failed runs. Avoid altering user work or competing with other benchmarks.
4. Attribute bottlenecks to source evidence. For a comparison, calculate the observed difference with variability and limitations; report improvement, regression, or no measurable difference equally plainly. Leave unsupported comparisons unresolved.
5. Produce a Markdown report with workload and environment, task outcomes, raw artifact references, distributions, bottlenecks, correctness results, proposed next investigations, and uncertainty. Use labeled tables or inline charts with units; do not invent samples to fill a chart. For an optimization request, complete the authorized candidate and comparison before the final report; for measurement-only work, report evidence without product edits.

## Report and output format

Write Markdown by default. Generate HTML only when the user explicitly requests a visual or HTML report; do not ask a routine format question. Reuse a combined report where practical instead of generating one per consulted skill. Honor explicit artifact paths/formats and keep small in-conversation work proportional.

Default path: `docs/reports/profile<NN>-<YYYYMMDD>-<title-slug>.md` in the target repository. Allocate the lowest unused positive number for this type across formats, padded to at least two digits. Use the creation date and a lowercase ASCII title slug, replacing non-alphanumeric runs with hyphens and limiting it to 60 characters at a word boundary. Retain the same basename and creation date when revising a confirmed matching artifact; never overwrite an unrelated report.

Use a descriptive title as the Markdown H1. Include the task-specific outcomes above, source references/revisions, actual verification commands and results, remaining gaps, and delivery state. Do not fabricate evidence or label proposed work completed. Check headings, links, and factual claims. Return a concise outcome and the absolute artifact path.

For a requested visual report, read [assets/report.html](assets/report.html) relative to this skill, or an explicitly supplied template. Use the same basename with `.html`; reuse existing Markdown evidence, and keep any companion formats consistent. Preserve the Foundry Zero layout, numbered sections, sidebar, themes, and print styling. Replace placeholders, escape content, and keep CSS/diagrams inline with accessible labels. Verify desktop/mobile rendering in an available browser or disclose the visual-check gap. A missing HTML asset matters only when HTML is requested. Report creation does not authorize serving, publishing, or merging.

For substantial interrupted work, update the existing task checkpoint with decisions, source/workspace state, evidence, active workers, and the next action. On resume, inspect current state before reusing that evidence; do not restart the workflow from its first step.
