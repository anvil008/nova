---
name: multiplan
description: When explicitly requested, obtain three independent plans using Antigravity, Claude Code, and Codex, then synthesize one coherent plan and acceptance-test approach in the main conversation.
---

Read [shared development instructions](../../instructions/development.md) when applying this skill; reuse them if already loaded in this conversation.


# Multiplan

Use for an explicit multiplan request, not as the automatic default for planning. Invoking this skill requests all three harnesses: Agy, Claude Code, and Codex. Do not require the user to repeat their names. Keep the user’s chosen models and efforts; otherwise use each harness's configured defaults and report effective settings when discoverable. Do not substitute a different harness/model to fill a missing result.

## Prepare a common brief

Establish the desired behavior from the accepted specification or clear request. If consequential intent is missing, resolve it with the user before commissioning dependent designs. Pin one source revision and provide the same scope, constraints, acceptance criteria, evidence pointers, and output expectations to all three planners. Reuse previous decisions and evidence without embedding a preferred implementation in the brief.

Inspect installed CLI help, native delegation support, authentication readiness, and permissions. Use a native worker for the current harness when its identity and task isolation are clear; use the requested harness's headless CLI for the others. Record the actual harness/model/effort. Prefer file/stdin briefs with proper quoting and captured output. No permission-bypass flags, automatic installs, or publishing are part of planning. The use-other-harness skill may supply execution guidance when available; this skill defines the assignment and synthesis itself.

## Fan out three independent drafts

Launch one planning pass per harness concurrently when available. Give each a read-only source snapshot or an isolated workspace pinned to the same base, with its own output destination. If stable snapshots cannot be obtained without disturbing existing work, resolve that limitation first. Do not let three planners edit the main workspace or share artifact filenames.

Each pass produces a Markdown draft containing: source-backed technical approach, interfaces/data/error behavior, task breakdown and real dependencies, criterion-to-test mapping with proposed fixtures/commands, compatibility and operational risks, alternatives considered, assumptions, and open questions. Ask each to form its own recommendation; do not show it the other plans or assign a predetermined conclusion. Agreements and differences should emerge from evidence rather than manufactured novelty.

These three passes are document-only planning: they do not implement product code or write/run acceptance tests. Mark commands not run and distinguish source inspection from runtime observations. Acceptance-test authoring occurs once after synthesis, preventing incompatible speculative test suites. Workers return their own plan and limitations; they do not launch further planners or mark the overall task complete.

Capture exit status and artifacts, keep the user informed, and retain successful results if another pass fails. Diagnose a failed invocation before a bounded retry. If a harness is missing or blocked, disclose which and why; continue useful comparison of available evidence but label it partial. Do not silently call two plans a three-harness result. Ask for a material substitution only if needed to satisfy the request.

## Synthesize in the main conversation

Read all completed drafts and verify consequential claims against source. Compare requirements coverage, correctness, simplicity, compatibility, task dependencies, testability, operational cost, and uncertainty. Attribute useful ideas to their originating drafts. Three agreeing models are not independent proof of a fact; challenge shared unsupported assumptions.

Choose one coherent approach. Combine compatible strengths, not every suggested feature. Reconcile conflicting interfaces, data models, and test expectations; explain significant rejected ideas and trade-offs. Resolve consequential product choices with the user rather than treating a majority vote as authorization. End with one implementation task sequence and acceptance-to-test mapping.

Apply the plan method to the synthesized design: author appropriate acceptance tests once in the retained implementation workspace and establish honest baseline passes/failures, unless the request is document-only/read-only. A missing interface may need an explicitly permitted signature-only stub; setup/import failures are not behavioral RED. Preserve criterion intent and existing passing behavior. Do not implement product logic during planning. When available, consult the plan skill for detailed test craft without spawning a fourth planning pass or generating a competing plan.

## Output and continuation

Write `docs/plans/plan<NN>-<YYYYMMDD>-<title-slug>.md` for the synthesis, using the existing plan numbering across formats and retaining identity on revision. Keep the three drafts under the matching `docs/plans/plan<NN>-<YYYYMMDD>-<title-slug>-alternatives/` directory as `agy.md`, `claude.md`, and `codex.md`. Summarize their differences in the final plan; link rather than duplicate raw logs. An explicit visual/HTML request adds the same-basename HTML plan using [assets/report.html](assets/report.html), with inline assets, escaped content, verified rendering, and honest partial status.

Return the synthesized recommendation, provenance of selected ideas, participation/settings, test evidence, remaining decisions, and artifact paths. A planning-only request ends there. Continue already-authorized implementation from the synthesized plan and retained tests without restarting discovery or requesting redundant approval. Preserve scope and external-action permissions. Use the shared checkpoint convention for substantial interrupted work, including which harness passes are still running and where their output lives.
