# 8. Agent dispatch and handoff use one explicit contract

## Status
Accepted

## Context
Every Workcell agent was instructed to return an `anvil.agent-handoff/v1` record, but no canonical schema defined that record. Skills also dispatched mode-specific work and no-issue work without a shared definition of the fields the agent would receive. That left orchestrators to infer whether evidence was complete and agents to infer which parts of their normal issue workflow still applied.

## Decision
[`agents/handoff.md`](../../agents/handoff.md) is the canonical contract for agent dispatch briefs and returned handoff records. A dispatch explicitly carries its issue or no-issue brief, workspace provenance, ownership, mode, test state, reviewer runtime input, and deploy approval. Every agent returns the same top-level record shape, while its domain-specific test map, findings, distribution, root cause, or other evidence stays inside `evidence`.

The disposition enum is closed: `done`, `blocked`, and `needs-decision`. Every recorded command has a `commandId` so domain evidence can cite the command that produced it. An invalid disposition or command without an identifier makes the record malformed and therefore blocked at orchestration.

## Consequences
Orchestrators can validate all agent results uniformly without discarding domain-specific evidence. Agent bodies must link the canonical contract and document any mode that changes their standard procedure. No-issue work can use acceptance tests in the brief without inventing a GitHub marker or issue-state transition. The contract adds a small amount of required output, but makes missing provenance and ambiguous terminal state mechanically visible.
