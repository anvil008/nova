---
name: new-feature
description: Build a new feature end-to-end, starting with a real interview — at least five clarifying questions before any planning — then plan, test-first build, review, and one PR to main.
---

# New Feature

Take a feature from a concept to a merged PR. Interview the human thoroughly before anything is planned so misunderstandings are caught before any code is built.

Invocation: `/workcell:new-feature`
Prompting Reference: [`docs/models/gpt-5.6-sol/prompting.md`](../../runtime/docs/models/gpt-5.6-sol/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_agent` with native specialist routing from `agents/models.json`, hold human gates, run VCS and workspace operations using shell execution, and read gate evidence and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

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

## The interview

**Ask at least five clarifying questions before dispatching the planner**, and wait for the answers. Skip this only when the user explicitly says to skip questions or to use your best judgement; a terse request is not permission to skip, and neither is impatience.

Ask about what would change the build if answered differently. Ground every question in what you can see of the repository, so they are answerable rather than abstract:

- **Users and trigger** — who does this, from where, and what makes them start?
- **Definition of done** — what observable thing is true when it works? This becomes the `acceptanceTests` oracles, so vagueness here is expensive later.
- **Scope edges** — what is explicitly _not_ in this? The excluded half prevents more rework than the included half.
- **Existing seams** — which current module, table, endpoint, or component should this extend rather than sit beside?
- **Failure behaviour** — what should happen on bad input, a timeout, or a downstream outage? Silence here becomes an agent's guess.
- **Constraints** — deadline, compatibility promises, data or privacy limits, anything that rules an approach out.

Do not ask what the repository can tell you. Before the interview, dispatch a `researcher` agent for a repository picture — manifests, architecture seams, and existing conventions — then state what its evidence suggests and ask the human to correct it. "The survey reports a Postgres schema and a REST layer, so I assume this is a new endpoint rather than a job — right?" is worth three abstract questions.

Batch the questions in one pass rather than interrogating one at a time, mark which are blocking, and offer your recommendation for each so a busy human can answer "yes to all".

## Procedure

1. **Clarifying interview.** Ask at least five clarifying questions before dispatching the planner (covering users, trigger, definition of done, scope boundaries, existing seams, failure behavior, and constraints). Ground questions in repository findings gathered via a `researcher` dispatched via `spawn_agent`. Wait for human answers.
2. **Plan.** Dispatch a `planner` via `spawn_agent` with the user's answers and feature goals. The planner produces the offline HTML folio, strict `plan.sidecar.json`, and per-issue `acceptanceTests` ([`plan`](../plan/SKILL.md)).
3. **Human approval checkpoint.** Stop and present the rendered HTML folio for explicit human approval. Never write GitHub milestones or issues without approval.
4. **Test-first execution.** Run [`build`](../build/SKILL.md) in single-PR mode. For each issue in a wave, dispatch a `specifier` via `spawn_agent` to author failing acceptance tests and establish a `tdd-guard seal`. Then dispatch a `builder` via `spawn_agent` in an isolated workspace ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)) to implement the feature against sealed tests.
5. **Parallel documentation.** For each wave, dispatch an `integrator` via `spawn_agent` over it and a `documenter` via `spawn_agent` on branch `doc/<slug>` with docs-only ownership. Documentation merges only inside a combined GREEN that includes it; the `documenter` reports `skills/docs/scripts/docs_check.py` — plus `render-diagrams.py --check` ([`ADR 0010`](../../runtime/docs/adr/0010-readme-diagrams-are-generated-svg.md)) where README visuals are generated — and the integrator reports the combined suite.
6. **Review and integrate.** Dispatch multi-lens `reviewer` agents via `spawn_agent`. Dispatch an `integrator` via `spawn_agent` over the combined wave. Open the single final PR from the integration branch to `main`.

## Boundaries

Never start planning on an unanswered blocking question, and never encode an unresolved decision into the plan — the sidecar has nowhere to put it by design. Never expand past what the interview agreed: a feature that grows during the build is a feature nobody approved. If the answers reveal the request is really a bug fix or a cleanup, say so and route it to [`code-analysis`](../code-analysis/SKILL.md) or [`code-refactor`](../code-refactor/SKILL.md) instead of building the wrong thing well.

## Harness Limitations

API-only model controls (such as dynamic request-level reasoning effort or pro mode toggles) and API-only orchestration features are unsupported in Codex skill prompts; execution relies on native harness tooling and specialist dispatch.
