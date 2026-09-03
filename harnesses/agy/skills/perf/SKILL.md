---
name: perf
description: Make something measurably faster — establish a baseline with the project's benchmark harness, optimize against it, and prove the gain is outside the noise. Refuses to proceed without a harness.
---

# Perf

Speed up code and prove it. Every other workflow's oracle is a boolean; this one's is a distribution, which changes how the whole thing is gated. One PR to `main`.

Invocation: `/workcell:perf`
Prompting Reference: [`docs/models/gemini-3.7-flash/prompting.md`](../../runtime/docs/models/gemini-3.7-flash/prompting.md)

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents via Antigravity's `invoke_subagent`, hold the human gates, run `git` / `jj` / `gh` and scripts via `run_command` for branch, merge, and issue-state operations, and read gate output and handoff records using the [`anvil.agent-handoff/v1`](../../runtime/handoff.md) schema. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator holds the benchmark gate and decides whether a measured gain is outside the noise. Per the Gemini 3.7 Flash guide, place critical constraints first, demand objective distributions with reported sample sizes, and refuse unmeasured claims.

## Critical Constraints

- **Goal:** Achieve measurable performance improvements demonstrated against established benchmarks with statistical confidence outside the noise.
- **Constraints:** No harness, no run: refuse to invent ad-hoc timing scripts. Never sacrifice correctness: all existing tests must remain identically green under a baseline seal. The profiler has no write tools to prevent benchmark tampering.
- **Success Criteria:** Baseline and comparison distributions recorded with spread and run counts, green correctness baseline intact, and clean PR to `main` with distribution proofs.

## Ordered Gates

Execution proceeds through four strict, ordered gates:

1. **benchmark baseline**: Establish baseline median and spread over repeated runs on the project benchmark harness.
2. **optimization**: Implement targeted performance optimizations under a green baseline seal.
3. **benchmark comparison**: Measure optimized code on identical hardware; comparison report proves gain is outside noise.
4. **review**: Multi-lens review verifies performance improvements and correctness preservation.

## No Harness, No Run

**If the project has no benchmark harness, stop and say so.** Do not let an agent invent a timing script and call it a baseline — that measures the script. Offer to build a harness first, as its own [`new-feature`](../new-feature/SKILL.md) run, and come back.

This is the honest failure mode of this skill, and taking it is cheaper than the alternative: a run that produces confident numbers nobody can reproduce next week.

## What counts as an improvement

A change is faster when the difference is **outside the baseline's spread**, measured the same way on the same machine, with the run count stated. Anything inside the noise is _no measurable difference_ — a real result, and one to report plainly rather than dress up. A codebase gets slower one unmeasurable "improvement" at a time, each of which looked positive in isolation.

Correctness is not negotiable for speed: a faster wrong answer is a regression. The suite stays green on every measured revision.

## Procedure

1. **Benchmark baseline.** Dispatch the `profiler` agent via `invoke_subagent` with the area to measure and the run count. It finds the harness, checks it is clean, runs it, and returns the baseline distribution: median, spread, and the runs. It has no write tools. If it reports no harness, stop.
2. **Correctness baseline.** Dispatch an `integrator` via `invoke_subagent` with a brief conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md) and carrying `mode: baseline`: run the documented verification on the untouched tree at `base`, return command-linked evidence, and perform no merge.
3. **Plan.** Dispatch a `debugger` agent via `invoke_subagent` to profile the hot path and find the bottleneck with evidence; then dispatch the `planner` with the bottleneck and the target. Each issue is one independently measurable change with a disjoint `ownershipHint`. Its `acceptanceTests` are the existing tests that must keep passing plus the profiler's baseline command. Approval as usual before writing GitHub tracking.
4. **Optimize.** Run [`build`](../build/SKILL.md) in **single-PR mode** with the specifier phase omitted, identically to a refactor. For each issue, the orchestrator creates its jj workspace and branch on the integration base:

   ```bash
   workcell-ws add perf/<issue-key> --base <integration-base>
   # = jj workspace add --name perf-<issue-key> ../<repo>-perf-<issue-key> -r <integration-base>
   #   + jj bookmark create perf/<issue-key> -r @   (git worktree add -b <branch> in a git-only repo)
   ```

   Optimization branches take the `perf/` type ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). Dispatch an `integrator` with a brief conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md) carrying `mode: baseline`, that `workspace`, the existing correctness tests as `sealedTests`, and their exact suite argv as `baselineCommand`. It returns green evidence plus a `kind: baseline` seal and hands the seal to the builder with `tdd-guard handoff --to builder`. Only then dispatch the `builder` in that workspace with `mode: refactor`. This is the same `tdd-guard` state machine with the RED requirement replaced by a GREEN one: the builder never touches a test file, retains post-seal GREEN evidence, and records real diff review passes.

5. **Measure again.** Dispatch the `profiler` over the builder's branch with the same command, parameters, and run count. It returns the comparison distribution.
6. **Compare.** Check the distributions. If the new median is outside the baseline spread, the optimization is real. Keep only what paid. An optimization inside the noise gets dropped, not merged: it bought nothing and cost readability. Say so in the PR — a documented negative result stops the next person from trying it again.
7. **Integrate and open final PR.** Dispatch an `integrator` over each wave to verify combined correctness, and the `profiler` once more on the integrated result. The final PR from that branch to `main` carries the before-and-after distributions (median, spread, run count, machine specs if relevant), the flamegraph or profile diff, and repeats every per-issue `Closes #<n>` line.

## Boundaries

Never accept a single run as evidence, never quote a mean without a spread, and never report an improvement you cannot distinguish from noise. Never let a benchmark be "fixed" to produce a better number — the `profiler` has no write tools for exactly this reason. Never trade correctness for speed without stating the trade explicitly and getting the human to take it. Never extrapolate a microbenchmark to end-to-end behaviour: say what was measured, and say what was not.

Based on the requirements and constraints above, execute the perf workflow systematically.
