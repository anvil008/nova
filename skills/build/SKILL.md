---
name: build
description: Implement a requested feature or fix with meaningful acceptance checks, runtime verification, and a Markdown implementation report.
---

Read [shared development instructions](../../instructions/development.md) when applying this skill; reuse them if already loaded in this conversation.


# Build

Use the current conversation and existing decisions. Follow persistent scope, delegation, verification, and report conventions; this skill requires no custom agent.

# Implementation expertise

Start from observable behavior and the user's accepted scope. Read the existing code and conventions before choosing a design. Prefer the smallest coherent change that satisfies the contract, with clear responsibility boundaries and established project idioms. Avoid speculative abstractions, unrelated cleanup, and new dependencies without a concrete need. Explain material compatibility or dependency trade-offs before depending on unresolved choices.

Use the existing specification, technical plan, diagnosis, and acceptance tests when supplied. Preserve criterion-to-task/test mappings and implement coherent planned tasks. Small clear requests may carry their spec and plan in the conversation; do not require separate invocations or artifacts. When planning has not supplied tests, write meaningful tests where the change warrants them and use a reproduced regression for a bug fix. Do not require ceremonial tests for trivial reversible edits. Do not require a separate test-writing agent, seal, issue, or helper command.

Independently authored acceptance tests express the agreed contract. Preserve their assertions, expected outputs, and selection: do not disable, skip, filter away, or weaken them to obtain a green run. If one is demonstrably incorrect, return specific evidence to its owner/caller for correction instead of redefining acceptance yourself. Add useful implementation-level and regression tests within scope; the initial acceptance tests are not assumed exhaustive. Preserve acceptance intent and any required independent test ownership. Honor any stronger user or project test protections. Assertions that pass while the requested behavior is absent are insufficient evidence.

For a defect, establish the failure before claiming a repair and exercise the same case afterward. Keep baseline environment failures distinct from product regressions. For an optimization, retain comparable performance and correctness evidence; do not claim a speedup from a single timing. For a refactor assignment, preserve behavior and contracts; do not disguise feature changes as cleanup.

Treat public interfaces, serialized data, failure behavior, and dependencies as compatibility surfaces. For a schema or data migration, establish existing-data behavior, upgrade sequencing, and recovery in an authorized local environment. Do not execute a production migration or deployment merely because implementation was requested. Build evidence must cover the relevant failure path as well as the happy path where it matters.

For frontend work, use the existing stack, design tokens, semantic elements, labeled controls, visible focus, keyboard operation, text error states, and responsive layout. Test user-visible loading, empty, error, and success states where affected. Avoid adding a framework solely for a small component. Browser checks must exercise the changed interaction, not only capture a screenshot.

When a change makes an actual architectural decision, record it in `docs/adr/NNNN-title.md` using the repository's numbering and Status, Context, Decision, and Consequences sections. Preserve accepted ADRs; supersede them with a new decision record when necessary. Routine implementation choices do not require an ADR. Keep affected README, API docs, changelog, and architecture notes aligned within scope, before final verification. Do not document a proposed spec or plan as an accepted decision.

## Execution process

1. Inspect scope, repository instructions, workspace state, and existing evidence. Reuse a supplied task workspace and acceptance tests. Otherwise prepare work under the global/repository jj and trunk conventions, isolating it only when necessary. Do not absorb unrelated changes or manufacture issues and intermediate branches.
2. Develop one proportional task breakdown if the work needs it. Connect each task to its acceptance behavior, affected components, dependencies, and verification. Reuse an accepted plan; a breakdown does not require renewed approval for already-authorized implementation. Surface consequential missing decisions while continuing independent work.
3. Establish the relevant baseline and implement coherent increments. Run supplied acceptance tests and useful regressions as behavior changes. Fix the underlying defect rather than suppressing symptoms. Keep related docs and examples accurate within the assignment. Follow existing build-cache locations and avoid copying large artifacts into temporary memory-backed storage.
4. Verify the final changed source with relevant tests and project-required checks. After interface/type changes, use the available type checker, compiler, or language-server diagnostics to catch cross-file errors. Format/lint as required. Reuse evidence only while its source and relevant environment remain valid; rebases or conflict resolution may require fresh checks.
5. Exercise the changed runnable surface in a local/test environment: drive UI interactions in a real browser at narrow and desktop sizes and inspect console/network errors; assert meaningful status and bodies for APIs; run CLIs on realistic inputs and check exit/output. A library without an independent runnable surface can use public-API tests, with that limitation stated. Attribute existing runtime errors separately and resolve regressions. Stop only processes and temporary state you created, unless the user asked to keep them running.
6. Inspect the complete diff, acceptance coverage, and delivery state. Arrange required or risk-warranted independent review when authorized and available, supplying the exact candidate, scope, and evidence; do not call self-review independent. Resolve assigned findings within scope, rerun affected checks, and return changed source for any required follow-up review. Outstanding required review or blocking findings mean the candidate is not ready to merge.
7. Have an assigned implementer write the Markdown implementation report with task outcomes, contract changes, representative examples, test and runtime evidence, review status, known failures, and actual local/published/integrated state. The parent reviews the report and follows the user's publication/merge authorization and project checks; a successful local build does not imply deployment or merge. Retain the task workspace and exact verified revision/state for continuation. Distinguish later report-only changes from the tested source.

## Native implementation

The parent owns decisions, observation, review, verification, and integration. An implementer authors every task-scoped file change, including code, tests, documentation, configuration, generated source, and file-backed reports; this includes small edits. The parent may inspect read-only, run checks or builds, and handle version control. Incidental caches and build output from those commands are not authored task changes.

Before a native call, give the implementer the source base, owned paths, behavior, acceptance checks, interfaces, and expected evidence. Make one assignment per coherent write task, not per file. Reuse the same implementer for scoped repairs and do not reassign active paths. The parent inspects each returned diff, combines results in dependency order, runs combined checks, and handles the final delivery. A requested file-backed report is an implementer assignment after the parent supplies the evidence it must contain.

The parent, never a hook, starts native implementers. Run concurrent writers only when the active harness supports it and tasks have no dependency or shared write ownership, including fixtures, generated files, lockfiles, and docs. Serialize coupled work. Use a separate workspace when isolation is needed. If no native implementer is available, report the limitation and obtain a user exception before directly authoring a task file; honor an explicit user override.

## Report and output format

Write Markdown by default. Generate HTML only when the user explicitly requests a visual or HTML report; do not ask a routine format question. Assign every file-backed report to an implementer; the parent may summarize verified results in conversation. Reuse a combined report where practical instead of generating one per consulted skill. Honor explicit artifact paths/formats and keep small in-conversation work proportional.

Default path: `docs/reports/build<NN>-<YYYYMMDD>-<title-slug>.md` in the target repository. Allocate the lowest unused positive number for this type across formats, padded to at least two digits. Use the creation date and a lowercase ASCII title slug, replacing non-alphanumeric runs with hyphens and limiting it to 60 characters at a word boundary. Retain the same basename and creation date when revising a confirmed matching artifact; never overwrite an unrelated report.

Use a descriptive title as the Markdown H1. Include the task-specific outcomes above, source references/revisions, actual verification commands and results, remaining gaps, and delivery state. Do not fabricate evidence or label proposed work completed. Check headings, links, and factual claims. Return a concise outcome and the absolute artifact path.

For a requested visual report, read [assets/report.html](assets/report.html) relative to this skill, or an explicitly supplied template. Use the same basename with `.html`; reuse existing Markdown evidence, and keep any companion formats consistent. Preserve the Foundry Zero layout, numbered sections, sidebar, themes, and print styling. Replace placeholders, escape content, and keep CSS/diagrams inline with accessible labels. Verify desktop/mobile rendering in an available browser or disclose the visual-check gap. A missing HTML asset matters only when HTML is requested. Report creation does not authorize serving, publishing, or merging.

For substantial interrupted work, update the existing task checkpoint with decisions, source/workspace state, evidence, active workers, and the next action. On resume, inspect current state before reusing that evidence; do not restart the workflow from its first step.
