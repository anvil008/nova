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

A change is faster when the difference is **outside the baseline's spread**, measured the same way on the same machine, with the run count stated. Anything inside the noise is no measurable difference.

## Procedure

1. **Baseline.** Dispatch a `profiler` via `invoke_subagent` to locate the benchmark harness, execute repeated measurement runs, and report median and spread with the run count. The profiler has no write tools. If it reports no harness exists, stop here.
2. **Correctness baseline.** Dispatch an `integrator` via `invoke_subagent` with `mode: baseline` to verify existing tests on `base` and seal them.
3. **Plan optimization.** Dispatch a `debugger` to profile hot paths, then dispatch `planner` to organize optimizations into issues with disjoint `ownershipHint` globs.
4. **Optimize against baseline seal.** In isolated workspaces (`workcell-ws add perf/<issue-key> --base <integration-base>`), dispatch `builder` agents with `mode: refactor` against the green baseline seal.
5. **Measure again.** Dispatch the `profiler` over the optimized code using the identical harness and parameters.
6. **Compare.** Retain only optimizations whose gain is outside the baseline's spread.
7. **Integrate and PR.** Open a single PR to `main` with before/after distributions.

## Boundaries

Never accept a single run as evidence or quote a mean without a spread. Never trade correctness for speed without explicit human authorization.

Based on the requirements and constraints above, execute the perf workflow systematically.
