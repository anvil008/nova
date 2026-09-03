---
name: new-feature
description: Build a new feature end-to-end, starting with a real interview — at least five clarifying questions before any planning — then plan, test-first build, review, and one PR to main.
---

# New Feature

Take a feature from a concept to a merged PR. Interview the human thoroughly before anything is planned so misunderstandings are caught before any code is built.

Invocation: `/workcell:new-feature`
Prompting Reference: [`docs/models/grok-4.6/prompting.md`](../../runtime/docs/models/grok-4.6/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_subagent` (running in foreground or with `background: true` tracked via `get_command_or_subagent_output`, or coordinated via `/workflow`), hold human gates, run VCS and workspace operations using shell execution, and read gate evidence and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Deliver a well-scoped new feature end-to-end through clarifying interview, approved plan, test-first execution, and a single PR to `main`.
- **Constraints and Boundaries:** Ask at least five clarifying questions before planning unless the user explicitly skips. Never dispatch a builder without a specifier RED seal. Never touch sealed tests.
- **Success Criteria:** Clarified requirements, approved plan and sidecar, sealed acceptance tests, verified green implementation, passing multi-lens reviews, and clean single PR to `main`.

## Ordered Gates

Execution proceeds through six strict, ordered gates:

1. **interview**: Conduct clarifying interview (at least 5 questions) before planning.
2. **approved plan**: Planner returns folio, sidecar, and acceptance tests; human approves before issue creation.
3. **sealed tests**: Specifier authors failing acceptance tests and establishes a `tdd-guard seal`.
4. **implementation**: Builder implements feature against sealed tests in an isolated workspace without editing tests.
5. **review**: Multi-lens review verifies code quality and behavioral correctness.
6. **pull request**: Single clean PR to `main` incorporates feature implementation, documentation, and closed issues.

## Input and Output Contracts

Subagent dispatch uses native Grok `spawn_subagent` (with `background: true` for parallel tasks, polled via `get_command_or_subagent_output`) or multi-step `/workflow` routines. Each dispatch exchanges structured handoff payloads conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md).

- **Researcher Exploration Inputs and Outputs:**
  - **Inputs:** Feature idea, relevant codebase areas, and architectural constraints.
  - **Outputs:** Architectural map, existing extension seams, and grounded context for interview questions.
- **Planner Inputs and Outputs:**
  - **Inputs:** Human interview responses, requirements, and codebase facts.
  - **Outputs:** HTML plan folio, `plan.sidecar.json`, and per-issue `acceptanceTests`.
- **Specifier Inputs and Outputs:**
  - **Inputs:** Planned issue key, acceptance test criteria, workspace path, and base bookmark.
  - **Outputs:** Sealed honest failing test manifest with `tdd-guard seal` evidence.
- **Builder Inputs and Outputs:**
  - **Inputs:** Assigned issue, sealed tests, and isolated workspace.
  - **Outputs:** Verified passing feature code, `tdd-guard verify` GREEN evidence, and two diff-review passes.
- **Integrator Inputs and Outputs:**
  - **Inputs:** Combined wave pull requests and integration branch.
  - **Outputs:** Integrated verification logs and merge readiness report.

## Procedure

1. **Clarifying interview.** Ask at least five clarifying questions before dispatching the planner (covering users, trigger, definition of done, scope boundaries, existing seams, failure behavior, and constraints). Ground questions in repository findings gathered via a `researcher` dispatched via `spawn_subagent`. Wait for human answers.
2. **Plan.** Dispatch a `planner` via `spawn_subagent` with the user's answers and feature goals. The planner produces the offline HTML folio, strict `plan.sidecar.json`, and per-issue `acceptanceTests` ([`plan`](../plan/SKILL.md)).
3. **Human approval checkpoint.** Stop and present the rendered HTML folio for explicit human approval. Never write GitHub milestones or issues without approval.
4. **Test-first execution.** Run [`build`](../build/SKILL.md) in single-PR mode. For each issue in a wave, dispatch a `specifier` via `spawn_subagent` to author failing acceptance tests and establish a `tdd-guard seal`. Then dispatch a `builder` via `spawn_subagent` in an isolated workspace ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)) to implement the feature against sealed tests.
5. **Parallel documentation.** For each wave, dispatch a `documenter` via `spawn_subagent` on branch `doc/<slug>` with docs-only ownership to update guides and reference docs in parallel.
6. **Review and integrate.** Dispatch multi-lens `reviewer` agents via `spawn_subagent`. Dispatch an `integrator` via `spawn_subagent` over the combined wave. Open the single final PR from the integration branch to `main`.

## Harness Limitations

Skill frontmatter fields `allowed-tools`, `model`, `effort`, `license`, and `compatibility` are unsupported for capability enforcement or routing under Grok Build; execution relies on native CLI flags (`--tools`, `--disallowed-tools`), agent definitions, capability modes, and specialist dispatch. API-only model controls and programmatic tool calling are unsupported in skill prompts.
