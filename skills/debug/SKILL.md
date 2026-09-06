---
name: debug
description: Reproduce a reported failure, isolate its cause with experiments, and hand the diagnosis to shared build when repair is requested. Use for a known symptom, incident, failing job, or flaky test.
---

# Debug

Start from a reported symptom and produce an experimentally supported diagnosis. `/debug` is a standalone workflow alongside `/review` and `/profile`. When the user requested a fix, feed that evidence into [/build](../build/SKILL.md). Diagnosis and repair share the same task context; this skill has no separate implementation pipeline.

The orchestrator owns scope, user decisions, authorization, and the handoff. Dispatch debugger agents for useful independent hypotheses or areas, with a count chosen from the investigation rather than a prescribed team size. Each debugger reproduces the symptom, reduces the case, tests distinguishing hypotheses, and returns commands, environment, outputs, causal `file:line` evidence, and proposed fix location. Temporary probes must be removed without disturbing pre-existing user changes. They implement no product repair.

No reproduction, no guessed fix. If a debugger cannot establish the failure, return its attempts and the concrete missing condition. For a flaky symptom, preserve the measured failure rate and sampling conditions; one successful retry is not evidence of repair. Scope stays with the reported defect. Related findings can be recorded, but fixing them needs authorization for that additional work.

Return a Markdown diagnosis report with the symptom, reproduction, tested hypotheses, supported cause, and remaining gaps. Add an HTML companion only when requested. A diagnosis or a documented inability to reproduce is a complete investigation outcome; neither requires entering build. Continue only when the cause is supported and repair is authorized.

Carry a usable diagnosis, exact source revision, reproduction command, minimal case, and existing decisions into `/build` as a fix. The brief conforms to [`agents/handoff.md`](../../agents/handoff.md), with an existing issue number or `issue: null`. Its acceptance criteria reproduce the observed failure; do not invent a milestone or issue. Reuse a complete brief, and dispatch a planner only for missing executable detail. For a request limited to investigation, stop with the report; do not assume permission to repair. A request to debug and fix already authorizes the build transition.

Shared build owns the specifier's honest RED seal, implementation, independent review, documentation when relevant, final verification, and authorized delivery. It preserves the diagnosis and tests the actual repair against it. A no-issue final PR names the symptom and the reproduction instead of `Closes #<n>`. If the investigation reveals a required design or behavior change outside the requested repair, return that decision to the user before expanding scope.
