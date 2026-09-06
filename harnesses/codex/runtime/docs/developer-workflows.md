# Developer workflows

Workcell's orchestrator frames your request, dispatches specialists, reviews evidence, and manages completion. Skills package workflows; agents perform their stages.

| Command | Outcome | Delegation |
| --- | --- | --- |
| `plan` | Executable Markdown plan; HTML when requested | Planners author approaches and direct researchers; orchestrator compares and reviews |
| `build` | Verified feature, fix, refactor, or optimization | Planner fills missing detail; specifier or integrator protects tests; builders, reviewers, documenter, and integrator complete the change |
| `review` | Verified findings for a diff or codebase audit | Reviewers investigate lenses and independently verify findings |
| `profile` | Reproducible measurements and hotspots | Profilers measure a baseline and explain uncertainty |
| `docs` | Independently validated documentation | Documenters edit assigned scopes and independent validation checks the final docs |
| `debug` | Diagnosis report; verified repair when requested | Debuggers reproduce and isolate the cause; authorized repairs use build |
| `refactor` | Refactor proposal; simpler structure when authorized | Planners assess structure with researchers as useful; build preserves invariants with a protected GREEN baseline |
| `deploy` | Authorized, verified release | Deployer performs preflight, release, verification, and rollback readiness |
| `repo-setup` | Repository ready for agent work | Delegated setup of instructions, runners, version control, and quality gates |
| `wiki` | Opted-in project knowledge | Consolidates immutable evidence and reusable patterns |

`jj` and `use-other-harness` are auxiliary skills. The latter runs only when explicitly requested. There are **12 public skills: 10 workflows and 2 auxiliaries**, and 10 specialist roles. Use `/workcell:<command>` in plugin slash-command surfaces or the host's native skill invocation.

## Planning

The orchestrator asks **one plan or multiple plan ideas** for a new plan unless the request or saved decision already supplies the choice. This chooses the deliverable, not a team size. It frames different approaches, assigns planners, compares the results, and has a planner author the selected or combined plan. Planners direct research into relevant unknowns; the orchestrator proxies dispatch if the host cannot nest agents.

Markdown is the default, with no format question. Ask for a visual or HTML plan to add an HTML companion. A small change can use a concise brief. Dependency runs use a strict JSON sidecar carrying task dependencies, acceptance tests, and ownership. GitHub issues are optional; local task IDs work without invented repository names or issue numbers.

The public research skill is removed. The researcher role and evidence-merging helpers remain inside planning. Standalone research can use the host's available research capabilities and ends with its result; Workcell does not automatically prompt it into planning or build. See the [planning choices](../../skills/plan/references/planning-modes.md) and [research contract](../../skills/plan/references/research.md).

## Moving into build

Standalone plan, review, profile, and refactor assessments deliver artifacts first. The orchestrator offers build for actionable follow-up, using the existing artifact as input, unless the user requested only a report. “Plan and implement,” “review and fix,” and explicit refactor or optimization requests already authorize that transition. Internal build reviews do not ask whether to start build again.

`debug` is a peer workflow to review and profile. It starts with a reported failure and returns a Markdown diagnosis with reproduction evidence, tested hypotheses, a supported cause, and any missing conditions. HTML is an optional requested companion. Investigation-only requests finish with that report. “Debug and fix” already authorizes build, but an unreproduced failure or unsupported cause never starts a guessed repair. Planning fills only missing design or executable detail.

`refactor` is also a peer workflow. Planners assess structural friction and direct researchers where useful, then return a Markdown proposal with source evidence, preserved contracts, existing tests, tradeoffs, and validation. Assessment-only requests finish there; authorized simplification continues into build. It does not need a new agent role or imply a performance improvement. Performance claims require profiling, while refactor verification protects the existing behavior and GREEN test baseline.

Build reuses plans, findings, source revisions, and decisions. It fills only missing executable detail, then chooses a single-change shape or schedules a dependency run by ownership and dependencies. There are no public simple-build or complex-build skills. A specifier proves and seals RED for behavior changes and fixes. An integrator seals a GREEN baseline for behavior-preserving work. Builders implement, reviewers check independently, and the integrator verifies the exact final source. Relevant documentation is combined before final verification; performance work includes comparison to the original baseline.

`docs` also runs independently, with its own validation and authorized delivery. A documenter assigned inside build returns scoped work to build instead of starting this standalone lifecycle. Deploy remains a separate authorized operation.

## Team sizing, evidence, and resume

The orchestrator decides team size from useful independent work, with no workflow-imposed count or retry ceiling. Explicit user budgets and host capacity still apply. Assign disjoint write ownership, preserve dependency order, and retain workspaces and agent IDs for recovery. Reuse completed evidence on resume.

Completion requires fresh evidence for the exact final source, independent review, and applicable checks. The orchestrator can accept, request revision, or surface a missing decision. No-progress, explicit budget exhaustion, cancellation, and blockers remain visible outcomes. See [build runs](build-runs.md), [single changes](../../skills/build/references/single-change.md), and [ADR 0029](adr/0029-composable-workflows-and-native-research.md).

Examples:

- `/workcell:plan Compare alternative approaches for organization accounts. Return a visual plan.`
- `/workcell:build Add a CSV download using the existing filtered table data.`
- `/workcell:review Audit authorization paths and report findings. Do not change code.`
- `/workcell:profile Measure the slow import path, then implement and remeasure the recommended optimization.`
- `/workcell:refactor Assess duplication in the billing modules and return a proposal. Do not change code.`
- `/workcell:docs Update the public API guide to match the shipped implementation.`
