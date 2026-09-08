---
name: spec
description: Interactively challenge and clarify a user's idea through focused questions, optional prototype comparisons, and source inspection, then define an actionable specification.
---

Read [shared development instructions](../../instructions/development.md) when applying this skill; reuse them if already loaded in this conversation.


# Spec

Define what the user wants and how success will be recognized before prescribing implementation. Work in the current conversation; reuse existing decisions, requirements, and evidence. A specification is not a task breakdown or executable test suite. No separate specialist or mandatory interview script is required.

## Discover the intended behavior

Read the request, relevant project instructions, existing behavior, and supplied artifacts first. Distinguish what is already known from assumptions and consequential unknowns. Inspect enough source to expose real constraints; do not turn discovery into exhaustive codebase research.

Treat an explicit spec session as a collaborative interview. Be a demanding but constructive product partner: probe vague answers, challenge contradictory requirements, ask for concrete examples, and expose expensive assumptions. Ask one to three focused questions per round, then use the answers to choose the next round. Do not dump a questionnaire or write a finished spec before the consequential answers arrive.

Explore who uses this, what triggers it, expected results, boundaries, failure cases, compatibility, and material constraints. Ask which trade-offs the user would accept and what would make the result a failure. Offer a recommendation or example when it clarifies the choice. Do not repeat known decisions or make the user research technical facts you can inspect. An explicit request to be grilled calls for deeper challenges, not a fixed question count or needless confrontation.

Use answers to refine the same specification. Continue independent investigation while material questions are pending, but keep affected requirements provisional. Silence is not a product decision or approval. If the request is already clear, summarize the intent without manufacturing an interview.

## Optional prototypes and competing ideas

Early in discovery, offer a choice between discussion only and seeing concrete options when visuals or architecture alternatives would resolve uncertainty. Reuse an already stated preference. Keep this within spec; no separate prototype skill is required.

When the user selects prototypes, create two or three materially different options, proportional to the question: quick interactive UI mockups for interaction decisions, or architecture diagrams with data/control flows for technical choices. Use the same scenario and constraints for every option. Label differences, benefits, costs, failure modes, and unresolved assumptions; include a recommendation without pretending an option was selected. Do not manufacture cosmetic alternatives to fill a quota.

Put options together in one comparison artifact so the user can inspect them side by side or switch between them. Ask what they prefer, reject, or want combined, then revise and carry the decision into the specification. Keep prototypes lightweight, isolated from product source, and clearly labeled with mocked behavior and unsupported states. Do not connect live accounts, introduce dependencies, or implement a backend merely to illustrate an idea.

Use `docs/specs/spec<NN>-<YYYYMMDD>-<title-slug>-options.html` when an HTML prototype comparison was requested; keep the same spec identity and link it from the Markdown specification. A prototype request authorizes that visual artifact, not an automatic HTML copy of every report. Honor explicit read-only/output boundaries and separate serving authorization. Inspect interactions and narrow/desktop rendering, or disclose the gap. Architecture options can use Markdown diagrams when sufficient. Proposed designs are not accepted ADRs or implemented behavior.

## Specification process

1. Establish the problem, intended users, desired outcome, current behavior, and source evidence. For a bug, use the reported/reproduced symptom; for a refactor, state preserved contracts; for performance, define the workload and measurable objective without inventing targets.
2. Resolve meaningful ambiguities with the user. Capture observable behavior, examples, edge/failure cases, interfaces and compatibility constraints, scope/non-goals, and accepted trade-offs. Separate confirmed requirements, assumptions, open questions, and proposals.
3. Give acceptance criteria stable identifiers such as AC-01 so planning can map them to tests and tasks. Describe observable results, not a file existing or an internal function being called. Specify enough to distinguish a correct outcome without constraining valid implementations unnecessarily.
4. Check completeness against the original request and examples. Identify contradictory or unobservable criteria. State ready for planning, provisional, or blocked on a named decision. Do not claim a document proves runtime behavior or user approval.
5. Produce the specification following the output convention below. Keep product code, executable tests, and configuration unchanged during this stage; only specification artifacts and requested isolated prototypes are written. Record decisions from the interview, rejected alternatives and why when material, and unresolved questions with their implications.

Return the specification path, concise agreed outcome, scope, acceptance criteria, and unresolved decisions. A spec-only request ends here. For an already-authorized end-to-end task, continue to technical planning once material decisions are resolved, preserving the same specification and authorization. Do not insert approval gates at routine transitions. Small, clear tasks may keep the specification and plan in the conversation rather than requiring separate invocations or files; honor explicit artifact requests.


## Report and output format

Write Markdown by default. Generate HTML only when the user explicitly requests a visual or HTML report; do not ask a routine format question. Reuse a combined report where practical instead of generating one per consulted skill. Honor explicit artifact paths/formats and keep small in-conversation work proportional.

Default path: `docs/specs/spec<NN>-<YYYYMMDD>-<title-slug>.md` in the target repository. Allocate the lowest unused positive number for this type across formats, padded to at least two digits. Use the creation date and a lowercase ASCII title slug, replacing non-alphanumeric runs with hyphens and limiting it to 60 characters at a word boundary. Retain the same basename and creation date when revising a confirmed matching artifact; never overwrite an unrelated report.

Use a descriptive title as the Markdown H1. Include the task-specific outcomes above, source references/revisions, actual verification commands and results, remaining gaps, and delivery state. Do not fabricate evidence or label proposed work completed. Check headings, links, and factual claims. Return a concise outcome and the absolute artifact path.

For a requested visual report, read [assets/report.html](assets/report.html) relative to this skill, or an explicitly supplied template. Use the same basename with `.html`; reuse existing Markdown evidence, and keep any companion formats consistent. Preserve the Foundry Zero layout, numbered sections, sidebar, themes, and print styling. Replace placeholders, escape content, and keep CSS/diagrams inline with accessible labels. Verify desktop/mobile rendering in an available browser or disclose the visual-check gap. A missing HTML asset matters only when HTML is requested. Report creation does not authorize serving, publishing, or merging.

For substantial interrupted work, update the existing task checkpoint with decisions, source/workspace state, evidence, active workers, and the next action. On resume, inspect current state before reusing that evidence; do not restart the workflow from its first step.
