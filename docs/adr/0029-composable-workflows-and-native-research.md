# 29. Composable workflows and planner-owned research

## Status

Accepted. Supersedes the workflow menu and planning choices in ADRs 0027 and 0028; their three-harness and specialist-ownership decisions remain in force.

## Context

Overlapping public commands duplicated implementation and approval flows. Planning output choices were confused with research team counts, and standalone reports were too tightly tied to implementation. The reviewed design consolidates implementation while preserving independent workflows.

## Decision

Nova exposes ten workflows: `plan`, `build`, `review`, `profile`, `docs`, `debug`, `refactor`, `deploy`, `repo-setup`, and `wiki`. `jj` and `use-other-harness` are auxiliary skills. Skills package dispatch contracts; agents perform assigned stages without recursively starting another workflow's delivery lifecycle.

Remove the public `research` skill. Research remains a planner capability, backed by the researcher role and evidence helpers under `skills/plan/research`. Standalone investigation can use the host's available research tools without entering Nova planning or being prompted to build. Native capabilities differ by host; this decision does not assume identical deep-research products.

For a new plan, the orchestrator asks whether the user wants one plan or multiple plan ideas unless the request or saved decision already answers that question. This controls the output, not a worker count. The orchestrator frames distinct approaches; planners investigate and author them. Planners direct researchers as needed. Where nested dispatch is unavailable, the orchestrator proxies dispatch and returns findings to the owning planner. The orchestrator compares evidence and tradeoffs, selects or combines compatible ideas, and assigns a planner to produce the coherent final artifact.

Markdown is the default plan and report format. An explicit visual/HTML request adds a companion without a format question. Standalone plan, review, profile, and refactor assessments deliver artifacts and offer build for actionable follow-up unless the user requested only a report. Existing authorization to implement, fix, refactor, or optimize carries through; do not ask again at internal stages.

Build is the shared implementation workflow. It reuses existing plans and findings, fills missing executable details, and schedules independent owned tasks. Single changes and dependency runs are internal shapes, not public skills. GitHub issues are optional. Feature and bug-fix changes require specifier-owned RED tests; behavior-preserving refactors and optimizations use an integrator-owned GREEN baseline. Builders implement and obtain independent review. Relevant documentation is combined before final verification. Performance changes are remeasured against the original baseline.

`review` includes codebase audits and diff reviews. `profile` produces measurement evidence. `debug` returns a diagnosis with reproduction and cause isolation. `refactor` returns a proposal with structural evidence and invariants, authored by planners with researchers as useful. These are peer workflows with completed assessment outcomes; their authorized implementation uses build. A refactor does not imply a performance gain. `docs` is independent; an assigned documenter inside build does not recursively invoke it. The public review-fix-loop is retired; its progress helper is internal to review.

## Team sizing and completion

No workflow imposes a default, required, or maximum number of agents or review attempts. The orchestrator chooses useful ownership and concurrency from the task and can revise it. Runtime capacity and explicit user constraints still apply. Dependencies and conflicting writers remain ordered.

Record evidence, ownership, decisions, and progress. Finish when the goal is verified, or report an actual blocked, cancelled, budget-limited, or no-progress outcome. Preserve immutable source receipts, sealed tests, resumability, independent verification, and existing delivery authorization.

## Consequences

There are fewer commands to learn and one implementation path to maintain. Research evidence and plan decisions survive transitions. The orchestrator judges and schedules; specialists perform the substantive work. Claude Code, Codex, and Antigravity use native tools; Grok is retired. GPT-6 Astra remains the configured Codex model where selected by the role manifest.
