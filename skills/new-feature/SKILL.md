---
name: new-feature
description: Build a new feature end-to-end, starting with a real interview — at least five clarifying questions before any planning — then plan, test-first build, review, and one PR to main.
---

# New feature

Take a feature from a sentence to a merged PR. The difference from running [`planner`](../planner/SKILL.md) directly is the front of it: you interview the human properly *before* anything is planned, because the cheapest place to fix a misunderstanding is before an agent has built on it.

You are the orchestrator ([ADR 0007](../../docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents, hold the human gates, run `git` / `jj` / `gh` for branch, merge, and issue-state operations, and read gate output and handoff records. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator runs the interview and carries the human's answers into every later dispatch.

## The interview

**Ask at least five clarifying questions before dispatching the planner**, and wait for the answers. Skip this only when the user explicitly says to skip questions or to use your best judgement; a terse request is not permission to skip, and neither is impatience.

Ask about what would change the build if answered differently. Ground every question in what you can see of the repository, so they are answerable rather than abstract:

- **Users and trigger** — who does this, from where, and what makes them start?
- **Definition of done** — what observable thing is true when it works? This becomes the `acceptanceTests` oracles, so vagueness here is expensive later.
- **Scope edges** — what is explicitly *not* in this? The excluded half prevents more rework than the included half.
- **Existing seams** — which current module, table, endpoint, or component should this extend rather than sit beside?
- **Failure behaviour** — what should happen on bad input, a timeout, or a downstream outage? Silence here becomes an agent's guess.
- **Constraints** — deadline, compatibility promises, data or privacy limits, anything that rules an approach out.

Do not ask what the repository can tell you. Before the interview, dispatch a `researcher` agent for a repository picture — manifests, architecture seams, and existing conventions — then state what its evidence suggests and ask the human to correct it. "The survey reports a Postgres schema and a REST layer, so I assume this is a new endpoint rather than a job — right?" is worth three abstract questions.

Batch the questions in one pass rather than interrogating one at a time, mark which are blocking, and offer your recommendation for each so a busy human can answer "yes to all".

## Procedure

1. **Interview** as above. Write the answers down; they are the planner's brief.
2. **Plan.** Dispatch the `planner` with the goal *and the answers*. It investigates read-only and returns the folio, sidecar, and per-issue `acceptanceTests`. If it returns `needs-decision`, that is a question the interview missed: put it to the human and re-dispatch rather than answering on their behalf.
3. **Approve.** Present the folio and stop for explicit human approval, then write the milestone and issues yourself.
4. **Execute** [`build`](../build/SKILL.md) in **single-PR mode**, both phases per issue: an `oracle` writes the acceptance tests, proves honest RED, and seals; the `builder` implements against tests it cannot edit; `reviewer` agents fan out by lens before any intermediate PR exists.
5. **Integrate.** Dispatch an `integrator` over each wave, merge the intermediate PRs to the integration branch on the evidence, and dispatch the `scribe` agent for whatever the feature changed about how the project is used.
6. **Open the final PR to `main`** from the integration branch. Its body describes the feature, the questions that shaped it, and the acceptance tests that define it as done, and repeats every per-issue `Closes #<n>` line.

## Boundaries

Never start planning on an unanswered blocking question, and never encode an unresolved decision into the plan — the sidecar has nowhere to put it by design. Never expand past what the interview agreed: a feature that grows during the build is a feature nobody approved. If the answers reveal the request is really a bug fix or a cleanup, say so and route it to [`code-analysis`](../code-analysis/SKILL.md) or [`code-refactor`](../code-refactor/SKILL.md) instead of building the wrong thing well.
