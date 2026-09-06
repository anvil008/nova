---
name: refactor
description: "Assess refactoring opportunities or simplify existing code without changing observable behavior, output, public contracts, or dependencies. Consolidate duplicated modules, remove dead wrappers and unreachable paths, and reduce unnecessary shallow indirection. Return a refactor proposal, then route authorized implementation through shared build with protected GREEN baseline tests."
---

# Refactor

Assess how existing code could become simpler while preserving what it does. `/refactor` is a standalone workflow alongside `/review`, `/debug`, and `/profile`; its assessment can finish with a proposal. Authorized implementation uses [/build](../build/SKILL.md) with behavior-preserving verification.

The orchestrator identifies the requested scope and holds its invariant: no behavior change, no dependency upgrade or new feature, and no added, modified, or deleted baseline test files. Assign assessment and proposal authorship to planners, who can direct researchers into useful independent areas. Team sizes follow the actual work, with no required count or fixed maximum. They inspect target code read-only and write only assigned report artifacts.

Use the [design heuristics](references/design-heuristics.md) when deciding whether consolidation, deeper modules, fewer indirections, or deletion earns its cost. Evidence should identify demonstrated friction at `file:line`, the simplification, contracts to preserve, existing tests, risks, and any ADR conflict. Distinguish supported opportunities from speculation; leaving an adequate structure unchanged is a valid recommendation. A refactor does not imply a performance gain. Such a claim needs measurements through [/profile](../profile/SKILL.md).

Return a Markdown refactor proposal with the inspected source revision, evidence, recommended scope, preserved behavior, validation commands, tradeoffs, and remaining gaps. Add an HTML companion only when requested. The orchestrator reviews the proposal and offers build for actionable work unless the user limited the request to a report. Assessment alone does not authorize code changes. An explicit request to refactor already authorizes that scoped implementation; continue without asking again.

Reuse an existing accepted assessment, executable plan, or brief instead of repeating the survey or producing a redundant report. When it lacks the needed design or task breakdown, dispatch planning through [/plan](../plan/SKILL.md) with the fixed behavior, existing tests, source revision, ownership, and user decisions. Carry the selected proposal into that planning; fill only missing detail.

Continue into shared `/build` with the preserved plan and authorization to refactor. Each applicable assignment uses an integrator with `mode: baseline`, the existing tests as `sealedTests`, and the exact `baselineCommand`. It proves GREEN and records a `kind: baseline` seal before a builder with `mode: refactor` begins. No specifier is needed. A failing baseline is reported before implementation; it is not repaired under a refactor label.

Build owns isolated writers, dependency scheduling, independent review, combined source verification, relevant documentation, and authorized delivery. Review checks behavior preservation and whether the structure became simpler; changed baseline tests or public behavior are failed refactor evidence. If a requested simplification requires different behavior or acceptance tests, surface the trade-off and scope it explicitly as a behavior change through build. Do not hide fixes inside cleanup or automatically fix unrelated bugs found along the way.
