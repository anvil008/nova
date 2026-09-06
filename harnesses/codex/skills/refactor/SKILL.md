---
name: refactor
description: "Refactor and simplify existing code without changing observable behavior, output, public contracts, or dependencies. Consolidate duplicated modules, remove dead wrappers and unreachable paths, and reduce unnecessary shallow indirection. Establish invariants and protected GREEN baseline tests, then use the shared build workflow for implementation and final verification."
---

# Refactor

Make the existing code simpler while preserving what it does. This is a discoverable entry into [/build](../build/SKILL.md) with behavior-preserving verification, not a second implementation pipeline.

Invocation: `/workcell:refactor`
Prompting Reference: [`docs/models/gpt-6-astra/prompting.md`](../../runtime/docs/models/gpt-6-astra/prompting.md)

Dispatch specialists with `spawn_agent` using native specialist routing and run VCS and gate commands through shell execution. Use the configured roles in `agents/models.json` and [`anvil.agent-handoff/v1`](../../runtime/handoff.md). Native runtime capacity affects scheduling; it does not prescribe a workflow team size.

The orchestrator identifies the requested scope and holds its invariant: no behavior change, no dependency upgrade or new feature, and no added, modified, or deleted baseline test files. Use the [design heuristics](references/design-heuristics.md) when deciding whether consolidation, deeper modules, fewer indirections, or deletion earns its cost. Evidence should identify demonstrated friction at `file:line`, the simplification, and the contracts it must preserve.

Reuse an existing executable plan or brief. When it lacks the needed design or task breakdown, dispatch planning through [/plan](../plan/SKILL.md) with the fixed behavior, existing tests, source revision, ownership, and user decisions. The planner can direct researchers to investigate useful independent areas and must name any ADR conflict. The orchestrator chooses delegation according to the actual work, with no required team count or fixed maximum.

Continue into shared `/build` with the preserved plan and authorization to refactor. Each applicable assignment uses an integrator with `mode: baseline`, the existing tests as `sealedTests`, and the exact `baselineCommand`. It proves GREEN and records a `kind: baseline` seal before a builder with `mode: refactor` begins. No specifier is needed. A failing baseline is reported before implementation; it is not repaired under a refactor label.

Build owns isolated writers, dependency scheduling, independent review, combined source verification, relevant documentation, and authorized delivery. Review checks behavior preservation and whether the structure became simpler; changed baseline tests or public behavior are failed refactor evidence. If a requested simplification requires different behavior or acceptance tests, surface the trade-off and scope it explicitly as a behavior change through build. Do not hide fixes inside cleanup or automatically fix unrelated bugs found along the way.

## Ordered Gates

1. **scope and invariants**: Record the requested simplification, unchanged behavior and contracts, and protected existing tests.
2. **shared build**: Carry the evidence, invariant, and existing repair authorization into the shared build workflow; an investigation-only request ends with its report.
3. **baseline comparison**: Shared build verifies final behavior against the unchanged GREEN baseline and resolves independent review findings.
