---
name: perf
description: Make something measurably faster — establish a baseline with the project's benchmark harness, optimize against it, and prove the gain is outside the noise. Refuses to proceed without a harness.
---

# Perf

Speed up code and prove it. While boolean suites test correctness, performance is evaluated against empirical distributions. One PR to `main` at the end.

Invocation: `/workcell:perf`
Prompting Reference: [`docs/models/gpt-5.6-sol/prompting.md`](../../runtime/docs/models/gpt-5.6-sol/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_agent` with native specialist routing from `agents/models.json`, hold human gates, run VCS and workspace operations using shell execution, and read gate evidence and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Achieve measurable performance improvements demonstrated against established benchmarks with statistical confidence outside the noise.
- **Constraints and Boundaries:** No harness, no run: refuse to invent ad-hoc timing scripts. Never sacrifice correctness: all existing tests must remain identically green under a baseline seal.
- **Success Criteria:** Baseline and comparison distributions recorded with spread and run counts, green correctness baseline intact, and clean PR to `main` with distribution proofs.

## Ordered Gates

Execution proceeds through four strict, ordered gates:

1. **benchmark baseline**: Establish baseline median and spread over repeated runs on the project benchmark harness.
2. **optimization**: Implement targeted performance optimizations under a green baseline seal.
3. **benchmark comparison**: Measure optimized code on identical hardware; comparison report proves gain is outside noise.
4. **review**: Multi-lens review verifies performance improvements and correctness preservation.

## No harness, no run

**If the project has no benchmark harness, stop and say so.** Do not let an agent invent a timing script and call it a baseline — that measures the script. Offer to build a harness first, as its own [`new-feature`](../new-feature/SKILL.md) run, and come back.

This is the honest failure mode of this skill, and taking it is cheaper than the alternative: a run that produces confident numbers nobody can reproduce next week.

## What counts as an improvement

A change is faster when the difference is **outside the baseline's spread**, measured the same way on the same machine, with the run count stated. Anything inside the noise is _no measurable difference_ — a real result, and one to report plainly rather than dress up. A codebase gets slower one unmeasurable "improvement" at a time, each of which looked positive in isolation.

Correctness is not negotiable for speed: a faster wrong answer is a regression. The suite stays green on every measured revision.

## Procedure

1. **Benchmark baseline.** Dispatch a `profiler` via `spawn_agent` to locate the project's benchmark harness, describe the test environment, and measure baseline median and spread across repeated runs. If the project lacks a benchmark harness, stop immediately and offer to create one first.
2. **Correctness baseline.** Dispatch an `integrator` via `spawn_agent` with a brief conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md) carrying `mode: baseline` on the untouched tree at `base`. Verification must be completely green before proceeding.
3. **Profile and plan.** Dispatch a `debugger` via `spawn_agent` to profile hotspots, then dispatch a `planner` via `spawn_agent` with the profile and baselines. Each planned optimization has disjoint `ownershipHint` globs and specifies existing tests that must remain green. Stop for human approval.
4. **Optimize under baseline seal.** Run [`build`](../build/SKILL.md) in single-PR mode omitting the specifier. Create a workspace with `workcell-ws add perf/<issue-key> --base <integration-base>` ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). Dispatch an `integrator` via `spawn_agent` with `mode: baseline` to establish a `kind: baseline` seal and hand the seal to the builder with `tdd-guard handoff --to builder`. Dispatch the `builder` via `spawn_agent` with `mode: refactor` to implement optimizations without altering test files.
5. **Benchmark comparison.** Dispatch the `profiler` via `spawn_agent` over the optimized code on identical hardware. Confirm that improvements exceed baseline spread and variance. Drop changes whose performance differences fall within noise.
6. **Integrate and PR.** Dispatch multi-lens `reviewer` agents via `spawn_agent`. Dispatch an `integrator` via `spawn_agent` over the wave. Open the single final PR to `main` including before/after distributions, environment specifications, and test proofs.

## Boundaries

Never accept a single run as evidence, never quote a mean without a spread, and never report an improvement you cannot distinguish from noise. Never let a benchmark be "fixed" to produce a better number — the `profiler` has no write tools for exactly this reason. Never trade correctness for speed without stating the trade explicitly and getting the human to take it. Never extrapolate a microbenchmark to end-to-end behaviour: say what was measured, and say what was not.

## Harness Limitations

API-only model controls (such as dynamic request-level reasoning effort or pro mode toggles) and API-only orchestration features are unsupported in Codex skill prompts; execution relies on native harness tooling and specialist dispatch.
