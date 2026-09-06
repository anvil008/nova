# 27. Developer workflows and orchestrator-owned planning

Current workflow menu and planning policy: [ADR 0029](0029-composable-workflows-and-native-research.md). This document records the earlier decision.
## Status

Superseded for planning authorship and planning modes by [ADR 0028](0028-planner-owned-research-and-three-harnesses.md). The developer entry-point decisions remain in effect. Historical decision follows.

## Context

Developers choose work by intent and scope. The previous entry points mixed those choices with internal phases and required a separate planner even when the lead agent already understood a bounded change. Each planning handoff could lose user context. Large investigations still benefit from a separate context, and implementation must still be checked independently.

## Decision

Expose `build`, `refactor`, and `debug` as the primary development entry points. `build` selects `simple-build` or `complex-build` from scope and uncertainty; both paths remain explicitly invocable. Keep existing commands working. `plan`, `build`, and `code-review` remain reusable stages; `new-feature` and `code-refactor` remain compatibility entry points.

The orchestrator owns requirements, planning, scope decisions, dispatch, and completion. It may read project code and tests to ground or challenge a plan, and write planning artifacts and run records. It delegates deep investigation or a draft plan when uncertainty, coupling, or context volume justifies a specialist. A planner's proposal is input to the orchestrator's final plan; a human still approves GitHub reconciliation against the exact sidecar digest. A changed approved sidecar requires renewed approval.

Planning has two modes, offered once when starting a new plan: standard orchestrator-owned planning, or five independent proposals with explicit user opt-in because of the extra token cost. Five proposal agents use fresh contexts and the same evidence, with different design priorities. The orchestrator compares the alternatives, recommends a coherent plan, and lets the human choose or combine approaches. Complexity alone never authorizes the extra round; saved choices and completed proposals survive nested workflows and resume. Additional rounds or paid retries require another user choice. This planning choice is separate from approval of the final artifacts or any external writes.

The orchestrator does not implement product changes, author runnable acceptance tests, or produce the independent verification evidence it uses to accept work. Specifiers, builders, reviewers, and integrators retain those responsibilities. Passing command evidence remains bound to the tested source and base, regardless of who wrote the plan.

`simple-build` handles one bounded behavior change with a recorded brief and one final PR. It needs no synthetic GitHub issue, milestone, or multi-issue ledger. `complex-build` composes planning and the existing resumable candidate/acceptance build protocol. Classification depends on uncertainty, dependencies, and ownership, not line count. A simple request escalates before implementation when its assumptions no longer hold; escalation preserves completed investigation and authorization but never grants broader scope.

`refactor` preserves behavior and existing tests through a GREEN baseline seal. `debug` establishes a reproduction before a RED seal and fix. Neither becomes a feature workflow merely because it spans several files.

## Consequences

The developer chooses a task; the orchestrator chooses the necessary specialists. Planning remains attributable through saved briefs or sidecars, decisions, and evidence references. Small work avoids milestone ceremony while retaining independent checks. Large work keeps dependency scheduling and durable acceptance. The run protocol lives in shared references, and each harness owns its native dispatch instructions.

Routing and contract checks establish packaging and instruction consistency. Compare real small fixes and large milestones on completion time, tokens, rework, and regressions before claiming this arrangement outperforms the previous one.
