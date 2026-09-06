---
name: build
description: "Build and deliver a new feature or requested change from scope interview through planning, delegated tests, implementation, review, and final PR. Add a small bounded feature using a concise brief, or execute and resume an approved multi-issue milestone in dependency waves with isolated tasks and combined verification. Reuse selected plans or findings. Coordinate migrations and local tasks without mandatory GitHub issues; preserve acceptance tests and include documentation before final checks. Schedule separate test-writing and implementation agents for each accepted ticket, followed by combined verification. Build user-visible UI components and accessible responsive forms as well as backend changes."
---

# Build

Deliver the requested software change through one shared execution workflow. `/plan`, `/review`, `/profile`, `/debug`, and `/refactor` can supply inputs; they do not create separate implementation pipelines. Simple and complex describe the work inside `/build`, not additional skills.

Invocation: `/workcell:build`
Prompting Reference: [`docs/models/gpt-6-astra/prompting.md`](../../runtime/docs/models/gpt-6-astra/prompting.md)

Dispatch specialists with `spawn_agent` using native specialist routing and run VCS and gate commands through shell execution. Use the configured roles in `agents/models.json` and [`anvil.agent-handoff/v1`](../../runtime/handoff.md). Native runtime capacity affects scheduling; it does not prescribe a workflow team size.

You are the orchestrator ([ADR 0029](../../runtime/docs/adr/0029-composable-workflows-and-native-research.md)): own user decisions, scope, authorization, scheduling, and final acceptance. Planners author plans and task breakdowns; specifiers author runnable tests; builders implement; reviewers judge independently; integrators verify combined source. Research remains a capability managed within planning. Evaluate evidence against the request, rather than accepting an agent's summary as proof.

## Start from what is already known

Preserve the source revision, goal, constraints, existing plan or findings, acceptance criteria, ownership, user decisions, authorization, and completed evidence in a durable run directory outside all source workspaces. Reuse a valid plan or executable brief. Dispatch a planner only for missing design or executable detail; do not rerun planning merely because another workflow handed work to build.

For a new plan, follow [/plan](../plan/SKILL.md)'s one-plan or multiple-ideas choice unless the user already specified it. The planner turns the selected direction into tasks with observable acceptance criteria, dependencies, and ownership. Markdown is the default; add HTML only when requested. Resolve material questions about users, compatibility, failure behavior, and scope, without an obligatory interview length or asking questions already answered.

The orchestrator reviews the plan against those decisions and carries authorization forward. A standalone assessment or plan must obtain the user's build decision before entering this workflow; a request to implement, fix, refactor, or optimize already authorizes the corresponding build work. Do not ask again at every internal stage. Reconcile GitHub issues only when tracking in GitHub is part of the request or project workflow; specifiers do not author issue breakdowns or create issues.

## Scheduling and verification are separate decisions

Choose the amount of delegation from the work's dependencies, ownership, uncertainty, and expected benefit. The orchestrator may use any useful number of planners, researchers, specifiers, builders, reviewers, documenters, or integrators. There is no prescribed team size, minimum fan-out, or workflow maximum. Respect actual runtime capacity and explicit user limits; queue ready assignments when capacity is occupied. Do not pad the work to fill an illustrated team or run overlapping writers concurrently.

- **A single change:** Use the [single change protocol](references/single-change.md). A concise brief and existing issue or `issue: null` are enough; no synthetic milestone or issue is needed.
- **Dependent work:** Use the [dependency run protocol](references/dependency-runs.md) and its durable `build_run.py` ledger. Task keys, dependency-ready selection, disjoint ownership, and accepted receipts make resume reliable. GitHub tracking is optional; local tasks have `issue: null`.

Changing team size does not change the evidence needed for a task:

| Change intent | Before implementation | Builder work | Acceptance evidence |
| --- | --- | --- | --- |
| Feature or bug fix | Specifier proves honest RED and seals runnable acceptance tests | Implement against protected tests | Fresh GREEN, independent review, runtime evidence, combined verification |
| Behavior-preserving refactor or optimization | Integrator proves GREEN against existing tests and records a baseline seal | `mode: refactor`; preserve behavior and tests | Fresh GREEN against the baseline, independent review, combined verification; remeasurement for performance work |

No builder starts without the applicable seal. A specifier's unobservable oracle or broken test returns to the planner or specifier; a failing baseline is reported before implementation. If an optimization requires a behavior or contract change, explicitly separate that scope and its RED verification from the behavior-preserving work. Existing tests that do not measure performance still require the profiler's independent benchmark evidence.

## Shared execution

1. **Isolate and dispatch ready tasks.** Pin the integration base; assign disjoint implementation and test ownership and an isolated workspace to each writer. Dependencies must be accepted before dependent implementation begins. Run the specifier or baseline integrator first, then the builder in the same workspace. Use native agent tools, the configured role models, and [`agents/handoff.md`](../../runtime/handoff.md).
2. **Implement and review.** Builders run sealed acceptance tests, targeted regressions, and the changed runnable surface. Independent reviewers inspect the complete task diff. Keep their findings, fixes, and verification inside this build; do not invoke a standalone `/review` that offers to re-enter `/build`. The orchestrator chooses further assignments and review passes from unresolved findings and progress, without a fixed retry quota. Reuse current findings on unchanged source. Stop claiming progress when the same unresolved failure recurs without new evidence; return the concrete blocker for a changed approach or a missing user decision. Critical or high findings remain blockers regardless of how many passes have run.
3. **Combine accepted work.** An integrator tests the combined candidate; the orchestrator accepts the receipt only after inspecting fresh per-source gates, ownership, runtime proof, and independent review. A failed candidate preserves the accepted base and source workspaces. The [dependency protocol](references/dependency-runs.md) retains the exact `prepare` / `accept` and recovery mechanics.
4. **Include relevant documentation.** Dispatch documenters when usage, contracts, or architecture changed. They may author alongside other ready work in disjoint docs workspaces, but their source must be combined before final verification. Use [finalization](references/finalization.md) to keep documentation commits separate from the accepted task ledger and verify the complete result. Do not launch a separate `/docs` workflow or create a second PR solely for required build documentation.
5. **Verify the final source.** The integrator runs the required project checks on the exact combined source, including relevant docs checks. For an optimization, the profiler then remeasures that same source against the recorded baseline using the same harness and conditions; inspect correctness, variability, and achieved performance together. A changed source or target base invalidates affected evidence and requires renewed verification. Source-bound mechanical gates and independent findings determine readiness.
6. **Deliver within authorization.** Record exact source commits and evidence; return the verified change or open the single final PR when requested or implied by the project workflow. Include only real issue-closing references. Require remote checks for the exact PR head before an authorized merge. Keep the source workspaces and run artifacts through acceptance and any outstanding finalization.

A Markdown plan, a review report, and a profiling report remain useful input artifacts; build does not reinterpret them as permission for unrelated changes. For diagnosis-only requests, [/debug](../debug/SKILL.md) can stop with evidence. [/refactor](../refactor/SKILL.md) preserves the behavior and tests that define its scope. Standalone documentation uses [/docs](../docs/SKILL.md).

## Ordered Gates

1. **scope and reuse**: Carry forward the request, source revision, decisions, existing plan or findings, and valid completed evidence.
2. **execution contract**: A planner fills only missing executable detail; choose scheduling and verification independently, with optional GitHub tracking.
3. **protected tests**: A specifier RED seal precedes behavior changes; an integrator GREEN baseline seal precedes behavior-preserving work.
4. **implementation and review**: Builders implement and independent reviewers inspect the current diff; the orchestrator chooses further assignments from evidence and progress.
5. **documentation**: Include relevant documentation in the combined source before final verification.
6. **final verification**: Verify the exact final source with project checks; remeasure optimization work against the same profiler baseline afterward.
7. **delivery**: Record source-bound readiness and deliver within existing authorization; inspect remote checks before an authorized PR merge.
