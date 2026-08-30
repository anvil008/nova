---
name: perf
description: Make something measurably faster — establish a baseline with the project's benchmark harness, optimize against it, and prove the gain is outside the noise. Refuses to proceed without a harness.
---

# Perf

Speed up code and prove it. Every other workflow's oracle is a boolean; this one's is a distribution, which changes how the whole thing is gated. One PR to `main`.

You are the orchestrator: you dispatch, hold the gates, and merge ([ADR 0007](../../docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)). You read the numbers, not the code.

## No harness, no run

**If the project has no benchmark harness, stop and say so.** Do not let an agent invent a timing script and call it a baseline — that measures the script. Offer to build a harness first, as its own [`new-feature`](../new-feature/SKILL.md) run, and come back.

This is the honest failure mode of this skill, and taking it is cheaper than the alternative: a run that produces confident numbers nobody can reproduce next week.

## What counts as an improvement

A change is faster when the difference is **outside the baseline's spread**, measured the same way on the same machine, with the run count stated. Anything inside the noise is *no measurable difference* — a real result, and one to report plainly rather than dress up. A codebase gets slower one unmeasurable "improvement" at a time, each of which looked positive in isolation.

Correctness is not negotiable for speed: a faster wrong answer is a regression. The suite stays green on every measured revision.

## Procedure

1. **Baseline.** Dispatch a `benchmarker` to find the project's harness, state the measurement environment, and report median and spread with the run count. If it returns `blocked` for a missing harness, stop here.
2. **Locate the cost.** Dispatch a `debugger` to profile and find where the time actually goes — it is the agent that runs experiments, and profiling is one. Optimizing what you assumed was slow, rather than what the profile says is slow, is the most common way this work wastes a week.
3. **Plan.** Dispatch the `planner` with the profile and the baseline. Each issue is one independently measurable optimization with a disjoint `ownershipHint`, and its `acceptanceTests` cover the **behaviour that must not change** — correctness is the seal here; speed is measured separately, because a test that asserts a timing threshold is a flaky test with extra steps.
4. **Optimize.** Run the waves as [`build`](../build/SKILL.md) does. Each `builder` implements one optimization against sealed correctness tests it cannot edit.
5. **Measure again, the same way.** Dispatch the `benchmarker` over the change, with the same harness, machine, and run count as the baseline. It reports the comparison with its uncertainty and never decides whether the change is worth shipping — that is yours.
6. **Keep only what paid.** An optimization inside the noise gets dropped, not merged: it bought nothing and cost readability. Say so in the PR — a documented negative result stops the next person from trying it again.
7. **Integrate and open one PR** to `main` with the before and after distributions, the run counts, the environment, and the correctness evidence. Merge on the numbers.

## Boundaries

Never accept a single run as evidence, never quote a mean without a spread, and never report an improvement you cannot distinguish from noise. Never let a benchmark be "fixed" to produce a better number — the `benchmarker` has no write tools for exactly this reason. Never trade correctness for speed without stating the trade explicitly and getting the human to take it. Never extrapolate a microbenchmark to end-to-end behaviour: say what was measured, and say what was not.
