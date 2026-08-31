---
name: perf
description: Make something measurably faster — establish a baseline with the project's benchmark harness, optimize against it, and prove the gain is outside the noise. Refuses to proceed without a harness.
---

# Perf

Speed up code and prove it. Every other workflow's oracle is a boolean; this one's is a distribution, which changes how the whole thing is gated. One PR to `main`.

You are the orchestrator ([ADR 0007](../../docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents, hold the human gates, run `git` / `jj` / `gh` for branch, merge, and issue-state operations, and read gate output and handoff records. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator holds the benchmark gate and decides whether a measured gain is outside the noise.

## No harness, no run

**If the project has no benchmark harness, stop and say so.** Do not let an agent invent a timing script and call it a baseline — that measures the script. Offer to build a harness first, as its own [`new-feature`](../new-feature/SKILL.md) run, and come back.

This is the honest failure mode of this skill, and taking it is cheaper than the alternative: a run that produces confident numbers nobody can reproduce next week.

## What counts as an improvement

A change is faster when the difference is **outside the baseline's spread**, measured the same way on the same machine, with the run count stated. Anything inside the noise is *no measurable difference* — a real result, and one to report plainly rather than dress up. A codebase gets slower one unmeasurable "improvement" at a time, each of which looked positive in isolation.

Correctness is not negotiable for speed: a faster wrong answer is a regression. The suite stays green on every measured revision.

## Procedure

1. **Baseline.** Dispatch a `profiler` to find the project's harness, state the measurement environment, and report median and spread with the run count. If it returns `blocked` for a missing harness, stop here.
2. **Correctness baseline.** Dispatch an `integrator` with a brief conforming to [`agents/handoff.md`](../../agents/handoff.md) and carrying `mode: baseline`: run the documented verification on the untouched tree at `base`, return command-linked evidence, and perform no merge. Stop unless that baseline is green.
3. **Locate and plan the cost.** Dispatch a `debugger` to profile and find where the time actually goes, then dispatch the `planner` with the profile and both baselines. Each issue is one independently measurable, behaviour-preserving optimization with a disjoint `ownershipHint`; its `acceptanceTests` name the existing tests whose outcomes must remain unchanged.
4. **Optimize against a green baseline seal.** Run [`build`](../build/SKILL.md) in **single-PR mode** with no `specifier`. For each optimization, the orchestrator creates the workspace and branch on the integration base, then dispatches an `integrator` with a brief conforming to [`agents/handoff.md`](../../agents/handoff.md) carrying `mode: baseline`, that `workspace`, the existing correctness tests as `sealedTests`, and their exact suite argv as `baselineCommand`. It returns green evidence plus a `kind: baseline` seal and hands the seal to the builder with `tdd-guard handoff --to builder`. Only then dispatch the `builder` in that workspace with `mode: refactor`.

   This is the same `tdd-guard` state machine with the RED requirement replaced by a GREEN one: sealed tests stay byte-identical, `verify --green-command` records a post-seal run, diff review binds the implementation diff, and the Stop hook and `status --json` work unchanged. The full gate is the profiler baseline plus that correctness state. Any optimization that changes observable behaviour is an ordinary planner issue and uses the normal `specifier` phase; it is not part of this behaviour-preserving path.
5. **Measure again, the same way.** Dispatch the `profiler` over the change, with the same harness, machine, and run count as the baseline. It reports the comparison with its uncertainty and never decides whether the change is worth shipping — that is yours.
6. **Keep only what paid.** An optimization inside the noise gets dropped, not merged: it bought nothing and cost readability. Say so in the PR — a documented negative result stops the next person from trying it again.
7. **Integrate and open the final PR.** Dispatch an `integrator` over each wave and merge intermediate PRs to the integration branch only when the correctness gate and benchmark evidence are green. The final PR from that branch to `main` carries the before and after distributions, run counts, environment, correctness evidence, and every per-issue `Closes #<n>` line.

## Boundaries

Never accept a single run as evidence, never quote a mean without a spread, and never report an improvement you cannot distinguish from noise. Never let a benchmark be "fixed" to produce a better number — the `profiler` has no write tools for exactly this reason. Never trade correctness for speed without stating the trade explicitly and getting the human to take it. Never extrapolate a microbenchmark to end-to-end behaviour: say what was measured, and say what was not.
