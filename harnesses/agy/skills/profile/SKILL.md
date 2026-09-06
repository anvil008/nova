---
name: profile
description: "Measure a workload, establish performance baselines and bottlenecks, and report the evidence. Route authorized optimization through build, then repeat comparable benchmarks to establish the result. Compare speedups with the existing benchmark harness using baseline median, spread, and measurement noise."
---

# Profile

Invocation: `/workcell:profile`
Prompting Reference: [`docs/models/gemini-3.8-flash/prompting.md`](../../runtime/docs/models/gemini-3.8-flash/prompting.md)

Dispatch specialists with Antigravity's `invoke_subagent` and use `run_command` for VCS and validation commands. Reasoning effort is session-wide; respect the configured session settings. Use [anvil.agent-handoff/v1](../../runtime/handoff.md) and configured specialist roles. Resolve bundled helper paths from this skill installation; the `skills/...` command examples are relative to the Workcell package root, while the target repository and run directory are supplied by the brief.

Explain where the requested workload spends time or resources, with measurements that can be repeated. Standalone profiling ends with a Markdown report of the baseline, bottlenecks, and worthwhile next investigations. Produce HTML only when explicitly requested.

The orchestrator owns the question, scope, dispatch, and final evaluation. Delegate measurement to the [profiler](../../agents/profiler/agent.md), selecting assignments and concurrency to fit the workload and runtime capacity. Concurrent measurements must not compete for the resources being compared. There is no prescribed team size, iteration count, or optimization quota.


## Ordered Gates

1. **measurement scope**: Establish the workload, source, objective, and permitted environment.
2. **benchmark baseline**: Record reproducible baseline commands, conditions, and uncertainty.
3. **hotspot analysis**: Link measured bottlenecks to source evidence.
4. **report**: Deliver a Markdown measurement report and its limitations.
5. **build transition**: Use build for authorized optimizations and repeat comparable measurements on the candidate.

## Establish the baseline

Identify the workload, input or dataset, source commit, performance objective, and existing benchmark or profiling commands. The profiler records exact commands and command IDs, environment, warmup treatment, run count, median, spread, and raw artifact paths outside source workspaces. Use the project's harness and representative inputs. A supported profiler over a reproducible project command can locate costs even when the project has no benchmark suite; distinguish that observation from a repeatable performance baseline.

If no representative repeatable measurement is possible, report the specific harness or workload gap. Do not invent timing scripts and claim they are an established baseline. Harness creation or product instrumentation belongs to an authorized build; continue useful read-only investigation while that decision is pending.

Ask the profiler to identify measured hot paths, allocations, I/O waits, contention, or other relevant costs and link them to source evidence. Do not require a debugger merely because profiling reveals an expensive path. Record correctness-check results for the measured source, including pre-existing failures; incorrect output cannot support an optimization claim.

## Report and optional optimization

The report states what was measured, the baseline distribution and conditions, measured bottlenecks, proposed changes and their expected tradeoffs, and what remains unknown. Separate measurements from hypotheses. A microbenchmark result applies to its workload; do not extrapolate it into an end-to-end claim.

Offer [build](../build/SKILL.md) for selected changes. Profiling alone does not authorize optimization. If the user already asked to optimize, continue through build for that scope without reasking. Carry the baseline artifacts, chosen objective, comparison method, and existing decisions into planning. Build owns implementation, independent correctness evidence, review, and final PR delivery; the profiler never edits code to make its numbers improve.

For behavior-preserving optimizations, build uses its existing GREEN-baseline path and unchanged tests. A behavior or dependency change requires the appropriate approved scope and acceptance criteria; do not disguise it as a refactor.

Before accepting an optimization claim, dispatch the profiler on the built candidate using comparable harness, inputs, machine, load, and sampling conditions, preferably interleaving baseline and candidate when practical. Compare distributions and uncertainty, not isolated runs. Report regression or no measurable difference plainly. If conditions differ materially, obtain comparable evidence or leave the claim unresolved. The orchestrator evaluates whether the measured result meets the user's objective and asks build to revise the candidate when needed, without inventing a pass cap or discarding user work automatically.

Keep the before/after measurements, correctness evidence, source commits, and remaining limits with the build handoff and final report. Explicit user budgets and runtime limits govern further measurement; stalled work needs an explanation and a decision, not another unexamined repetition.
