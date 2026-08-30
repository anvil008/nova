---
name: code-refactor
description: Simplify a codebase end-to-end without changing what it does — consolidate duplicated modules, deepen shallow ones, delete dead paths — then open one PR to main. Behaviour-preserving only; never fixes bugs or changes features.
---

# Code refactor

Make the code simpler while it keeps doing exactly what it did. Combine modules that were split for no reason, deepen ones whose interface is wider than their substance, collapse indirection that earns nothing, and delete what nothing reaches. One PR to `main` at the end.

You are the orchestrator ([ADR 0007](../../docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents, hold the human gates, run `git` / `jj` / `gh` for branch, merge, and issue-state operations, and read gate output and handoff records. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator holds the behaviour-preservation invariant and rejects any change-set that moves tests.

## The one invariant

**Behaviour does not change, and neither do the tests.** That is what separates a refactor from a rewrite, and it is checkable rather than promised:

- the full suite is green *before* the first change, and identical-green after;
- **no test file is modified, added, or deleted** — a refactor that edits its own tests has stopped being one, because the thing that was supposed to hold still moved;
- no new dependency, no new feature, no bug fix. A bug found on the way is written down and routed to [`code-analysis`](../code-analysis/SKILL.md), never fixed here — a fix inside a refactor is a behaviour change hiding in a diff nobody is reading for behaviour.

## Why this skill does not use the TDD gate

`tdd-guard seal` requires a **non-zero** red command: it exists to prove tests fail before an implementation makes them pass. A refactor has nothing to make pass — the suite is green at the start and must be green at the end. Sealing is impossible and would be dishonest if it were not.

So this skill swaps the gate rather than skipping it. The baseline green run is the oracle, the diff must not touch tests, and `tdd-guard diff-review record` still binds review findings to the real diff. Do not dispatch a `test-author`, and do not let a builder invent a failing test to satisfy a ceremony that does not apply here.

## Procedure

1. **Baseline.** Dispatch an `integrator` with a brief conforming to [`agents/handoff.md`](../../agents/handoff.md) and carrying `mode: baseline`: run the documented verification on the untouched tree at `base`, return command-linked evidence, and perform no merge. If it is not green before you start, stop: you cannot tell a refactor regression from a pre-existing failure, and you will spend the whole run guessing.
2. **Survey.** Dispatch `research` agents, one per area, to map the simplification candidates: duplicated logic, modules that only forward, abstractions with a single caller, dead exports, cyclic dependencies, and interfaces wider than their use. They return evidence with `file:line`, never edits.
3. **Plan.** Dispatch the `planner` with the survey and this skill's invariant. Each issue is one independently landable simplification with a disjoint `ownershipHint`. `acceptanceTests` for a refactor issue name the **existing** tests that must keep passing — the observable behaviour being preserved — not new ones to write. Human approval as usual before any GitHub write.
4. **Execute.** Run [`build`](../build/SKILL.md) in **single-PR mode**, with the test-author phase omitted — which means **you create each issue's jj workspace and branch yourself** before dispatching its builder, since no test-author exists to do it:

   ```bash
   jj workspace add --name <issue-key> ../<repo>-<issue-key> -r <integration-base>
   jj bookmark create <branch> -r @
   ```

   Creating a workspace is a branch operation, so it stays inside the orchestrator's boundary. Each `builder` gets a brief conforming to [`agents/handoff.md`](../../agents/handoff.md) and carrying `mode: refactor`: the workspace was pre-created by the orchestrator, there is no seal, tests stay untouched, and diff-review is still recorded. Give it the workspace name and baseline evidence. Reject any change-set whose diff touches a test file, and send it back.
5. **Review.** The usual lens fan-out, weighted to this work: `correctness` (behaviour preserved), `api-contract` (no public surface moved without cause), plus `backend`, `frontend`, or `integrations` where the change lands. A reviewer that finds a *behaviour* difference is reporting a failed refactor, not a nit.
6. **Integrate and open the final PR.** Dispatch an `integrator` over each wave, compare its run against the step-1 baseline — same tests, same outcomes — and merge intermediate PRs to the integration branch only on the evidence. The final PR from that branch to `main` summarizes what got simpler and what stayed identical, and repeats every per-issue `Closes #<n>` line.

## Boundaries

Never fix a bug, add a feature, change a public contract without saying so plainly in the PR, or upgrade a dependency. Never accept "the tests needed updating" as part of a refactor: that sentence means the behaviour changed, and it belongs in a different skill with a different gate. If simplification is impossible without changing behaviour, stop and return the trade-off to the human rather than quietly taking it.
