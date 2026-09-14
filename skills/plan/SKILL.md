---
name: plan
description: Turn a specification or clear request into one technical approach, ordered tasks, and executable acceptance tests with honest baseline results before product implementation.
---

Read [shared development instructions](../../instructions/development.md) when applying this skill; reuse them if already loaded in this conversation.


# Plan

Use the current conversation and existing decisions. Follow persistent scope, delegation, verification, and report conventions; this skill requires no custom agent.

# Planning expertise

Use plan when desired behavior is sufficiently clear to design and test. Resolve missing product intent with the user or spec before dependent planning; do not invent requirements. Use multiplan only when explicitly requested for independent Agy, Claude, and Codex alternatives. Ordinary plan remains one approach.

Start from the specification or a clear request; a separate spec file is not a prerequisite. Develop one actionable approach by default. Reuse accepted scope, user decisions, existing plans, diagnoses, and current evidence. Compare alternatives only when requested or when a material trade-off needs resolution; do not ask the user to choose a number of plans. Planning includes acceptance-test authoring by default, but does not authorize product implementation. Honor explicit read-only, no-test-edit, or document-only requests; map tests and disclose the deferred baseline in those modes.

Ground proposals in the actual repository: entry points, callers, tests, data flows, dependencies, architecture decisions, and relevant runtime constraints. Distinguish observed behavior from desired behavior. Use official primary sources for external technical claims and verify version applicability. Mark inference and assumptions rather than presenting them as facts.

Identify what must be learned before a design is credible. Investigate tightly coupled questions yourself. For useful independent questions, delegate only when authorized and available, supplying the question, scope/source revision, source pointers, read-only boundary, and decision it should inform. The optional scout helper is suitable but not required; investigate directly when delegation adds no value. No mandatory research phase is needed. Reuse completed evidence and ask follow-ups only when they can change a decision.

Synthesize evidence rather than concatenate reports. Preserve contradictions, gaps, and uncertainties; evaluate whether sources describe the same version or context before treating them as disagreement. Resolve routine implementation choices using source and constraints. Surface only consequential product, compatibility, scope, or resource decisions to the user while continuing independent work.

Choose a small coherent design that fits existing responsibility boundaries. Specify public contracts, error behavior, data changes, compatibility, and any rollout/recovery needs proportionally. Avoid speculative abstractions, unnecessary migrations, and optimizing an unmeasured workload. For a refactor, state preserved behavior; for a repair, anchor acceptance in the reproduced symptom; for optimization, require comparable performance and correctness evidence.

Break the approach into verifiable tasks, with outcome, affected areas, observable acceptance criteria, and real dependencies. Do not invent parallelism by splitting coupled work. If tasks will run concurrently, identify overlapping writes and shared interfaces. A task list is not a requirement for separate agents, branches, issues, or PRs. Map specification criteria to tasks and acceptance tests. Author those tests during planning while keeping product behavior unchanged.

## Acceptance-test expertise

Translate the assigned requirement into an observable pass condition. Assert the promised behavior at a useful public boundary, not a proxy such as a function being called or an implementation-specific string appearing. Cover the accepted examples, meaningful boundaries, and failure behavior without inventing new requirements. Existing issues, user instructions, and accepted plans are sufficient input; no special brief schema is required.

Inspect actual interfaces and the project's test conventions. Reuse fixtures and test infrastructure, isolate state, avoid live external services where a faithful local boundary suffices, and keep tests deterministic. Avoid excessive mocking of the behavior under test. Tests should fail when the promised behavior is absent and pass for any valid implementation of the contract.

For missing behavior, demonstrate a failure that reaches the behavioral assertion. Import failures, syntax errors, missing fixtures, and environment setup failures are test-infrastructure problems, not proof of an acceptance failure. When the public interface does not yet exist, prefer a test at an existing executable boundary. If a signature-only stub is necessary, add it only when the assignment permits that implementation-path edit; give it no product logic and report it explicitly. Otherwise identify the blocked oracle without pretending the test is ready.

Do not require every assertion to fail: already-supported cases should remain green. Report newly failing expectations, existing passing coverage, and genuinely blocked cases separately. Do not alter working behavior to manufacture RED. If the requested feature already works, document the passing evidence rather than force a failure.

During test specification, keep production code read-only except an explicitly permitted signature-only stub. Establish the acceptance baseline before any authorized implementation begins. Do not weaken criteria or decide ambiguous product behavior yourself. Surface an unobservable criterion or material design gap with the concrete question and continue independent test work. An acceptance report can identify coverage gaps; it cannot substitute for runnable evidence.

## Execution process

1. Read the specification, acceptance criteria, existing source/tests, project instructions, and workspace state. Reuse a supplied workspace and preserve existing work. Ask only about consequential unresolved requirements; keep affected tasks provisional rather than choosing product behavior yourself.
2. Develop one technical approach with rationale, relevant interfaces, compatibility/data/error behavior, ordered tasks, ownership where useful, real dependencies, risks, and verification. Each task maps to specification criteria and a concrete outcome. No required sidecar, issue, branch, or agent per task is needed.
3. Create an acceptance-to-test mapping: criterion ID, observable oracle, test location, fixtures, command, and implementation task. Reuse adequate existing coverage. Author meaningful missing acceptance tests and authorized scaffolding; avoid ceremonial tests for trivial reversible edits. For document-only/read-only planning, describe tests without writing or running mutating steps.
4. Run focused tests against the unchanged product implementation. Record source state, commands, exit status, and actual assertion failures or passes. Fix test setup before claiming RED; identify blocked oracles honestly. Keep existing passing behavior visible. Inspect the diff for unintended product implementation and honor project test protections; this skill installs no seals.
5. Check that every required behavior has an implementation task and verification path, interfaces agree, and dependencies are real. Report coverage gaps, test ownership, signature-only stubs if explicitly allowed, passing/failing cases, and unresolved criteria. Retain the workspace and tests for implementation. Revise the same plan after feedback.
6. Produce the plan following the output convention below. Include spec references, approach, task outcomes, acceptance-to-test mapping, baseline results, exact commands, risks, and readiness.

Return the plan path, retained workspace/tests, source state, key decisions, observed baseline, and remaining gaps. Plan-only work ends with the plan and authorized test changes; it does not implement product behavior. When implementation is already authorized and required decisions are resolved, continue with build using the same spec, plan, and tests without renewed approval. Small tasks can keep a concise spec/plan in the conversation; separate invocations and documents are not mandatory unless requested.


## Report and output format

Write Markdown by default. Generate HTML only when the user explicitly requests a visual or HTML report; do not ask a routine format question. Reuse a combined report where practical instead of generating one per consulted skill. Honor explicit artifact paths/formats and keep small in-conversation work proportional.

Default path: `docs/plans/plan<NN>-<YYYYMMDD>-<title-slug>.md` in the target repository. Allocate the lowest unused positive number for this type across formats, padded to at least two digits. Use the creation date and a lowercase ASCII title slug, replacing non-alphanumeric runs with hyphens and limiting it to 60 characters at a word boundary. Retain the same basename and creation date when revising a confirmed matching artifact; never overwrite an unrelated report.

Use a descriptive title as the Markdown H1. Include the task-specific outcomes above, source references/revisions, actual verification commands and results, remaining gaps, and delivery state. Do not fabricate evidence or label proposed work completed. Check headings, links, and factual claims. Return a concise outcome and the absolute artifact path.

For a requested visual report, read [assets/report.html](assets/report.html) relative to this skill, or an explicitly supplied template. Use the same basename with `.html`; reuse existing Markdown evidence, and keep any companion formats consistent. Preserve the Foundry Zero layout, numbered sections, sidebar, themes, and print styling. Replace placeholders, escape content, and keep CSS/diagrams inline with accessible labels. Verify desktop/mobile rendering in an available browser or disclose the visual-check gap. A missing HTML asset matters only when HTML is requested. Report creation does not authorize serving, publishing, or merging.

For substantial interrupted work, update the existing task checkpoint with decisions, source/workspace state, evidence, active workers, and the next action. On resume, inspect current state before reusing that evidence; do not restart the workflow from its first step.
