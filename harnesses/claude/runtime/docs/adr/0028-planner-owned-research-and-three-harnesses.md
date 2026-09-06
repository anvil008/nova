# 28. Planner-owned research and three supported harnesses

Current workflow menu and planning policy: [ADR 0029](0029-composable-workflows-and-native-research.md). This document records the earlier decision.
## Status

Accepted. Supersedes ADR 0027's planning authorship and five-proposal mode, and the Grok support described in earlier deployment decisions.

## Context

Planning benefits from focused investigation and a coherent author. Relaying every research question through the root adds coordination work and puts intermediate evidence into the context used to review the plan. Grok's integration adds a separate compatibility surface that the project no longer intends to maintain.

## Decision

Support Claude Code, Codex, and Antigravity. Remove Grok agent definitions, model guides, plugins, generated runtime, installation, staging, and evaluation support. Historical plans and ADRs remain records of their original decisions.

The orchestrator owns user intent, authorization, the overall budget, workflow scheduling, and final evaluation. One planner owns every new plan or bounded development brief. In standard mode the planner investigates itself. With user opt-in, the planner spawns scoped read-only researchers, receives evidence directly, resolves research conflicts, and authors a coherent plan. Researchers cannot delegate further. Use native harness tools, their capacity limits, and the configured role models.

Choose the research team from distinct unknowns; five is an available size, not a mandatory count. Preserve the approved total attempt budget, saved researcher IDs, evidence, and completion state across resume. Extra attempts beyond that budget require a new user choice. No automatic five-planner debate remains.

Produce Markdown by default without asking a format question. An explicit visual/HTML request adds an HTML companion. Both full-plan formats come from one validated sidecar and reuse the same plan identity and filename number. A bounded brief need not manufacture milestone tracking.

The orchestrator returns accept, revise with specific findings, or needs-decision. The planner makes revisions. Reports retain references to evidence, conflicting findings, alternatives, and gaps. Internal acceptance does not replace mechanical implementation gates or the user's authorization for external writes.

## Consequences

Planning research stays with its author while the root retains review context. Nested scheduling, cancellation, and budgets must remain visible across the team. Native depth/capacity limits are mechanical; total research authorization and revision limits are recorded workflow contracts and must be checked before dispatch. This change does not introduce a custom SDK executor or claim measured quality gains.

Markdown plans remain usable in repositories and code review. HTML is generated only when requested. SDK-based automation can consume the same role and artifact contracts in a later execution layer without duplicating workflow policy.
