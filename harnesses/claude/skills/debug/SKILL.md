---
name: debug
description: Reproduce a reported failure, isolate its cause with experiments, and hand the diagnosis to shared build when repair is requested. Use for a known symptom, incident, failing job, or flaky test.
---

# Debug

Start from a reported symptom and produce an experimentally supported diagnosis. When the user requested a fix, feed that evidence into [/build](../build/SKILL.md). Diagnosis and repair share the same task context; this skill has no separate implementation pipeline.

Invocation: `/workcell:debug`
Prompting Reference: [`docs/models/claude-fable-5-1/prompting.md`](../../runtime/docs/models/claude-fable-5-1/prompting.md)

Dispatch specialists with Claude Code's `Agent` tool and use `Bash` for VCS and gate commands. Use the configured roles in `agents/models.json` and [`anvil.agent-handoff/v1`](../../runtime/handoff.md). Native runtime capacity affects scheduling; it does not prescribe a workflow team size.

The orchestrator owns scope, user decisions, authorization, and the handoff. Dispatch debugger agents for useful independent hypotheses or areas, with a count chosen from the investigation rather than a prescribed team size. Each debugger reproduces the symptom, reduces the case, tests distinguishing hypotheses, and returns commands, environment, outputs, causal `file:line` evidence, and proposed fix location. Temporary probes must be removed without disturbing pre-existing user changes. They implement no product repair.

No reproduction, no guessed fix. If a debugger cannot establish the failure, return its attempts and the concrete missing condition. For a flaky symptom, preserve the measured failure rate and sampling conditions; one successful retry is not evidence of repair. Scope stays with the reported defect. Related findings can be recorded, but fixing them needs authorization for that additional work.

Carry a usable diagnosis, exact source revision, reproduction command, minimal case, and existing decisions into `/build` as a fix. The brief conforms to [`agents/handoff.md`](../../runtime/handoff.md), with an existing issue number or `issue: null`. Its acceptance criteria reproduce the observed failure; do not invent a milestone or issue. Reuse a complete brief, and dispatch a planner only for missing executable detail. For a request limited to investigation, stop with the report; do not assume permission to repair. A request to debug and fix already authorizes the build transition.

Shared build owns the specifier's honest RED seal, implementation, independent review, documentation when relevant, final verification, and authorized delivery. It preserves the diagnosis and tests the actual repair against it. A no-issue final PR names the symptom and the reproduction instead of `Closes #<n>`. If the investigation reveals a required design or behavior change outside the requested repair, return that decision to the user before expanding scope.

## Ordered Gates

1. **reproduce symptom**: Debuggers establish the reported symptom or return the missing reproduction condition.
2. **isolate cause**: Use experiments and minimal cases to demonstrate the causal defect.
3. **shared build**: Carry the evidence, invariant, and existing repair authorization into the shared build workflow; an investigation-only request ends with its report.
4. **reproduction verification**: Shared build proves the original symptom resolved against its sealed acceptance test and final source.
