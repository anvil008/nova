---
name: use-other-harness
description: Run a bounded task in another coding harness only when the user explicitly requests that harness.
---

Read [shared development instructions](../../instructions/development.md) when applying this skill; reuse them if already loaded in this conversation.


# Use another harness

Use only for an explicit request to run Claude Code, Codex, or Agy as another harness. An explicit multiplan invocation also authorizes its three named planning passes; creating or discussing that skill does not execute them. Preserve requested model and effort. If unspecified, use configured defaults unless the task requires a user choice, and disclose the effective setting or that it could not be determined. Never route across harnesses automatically.

Inspect installed CLI help and version before constructing its headless invocation. Use supported prompt, model, effort, output, and working-directory options; avoid stale flags and invented model identifiers. Honor authentication and permissions. Do not add approval-bypass flags merely to avoid setup problems.

Prepare a bounded assignment containing goal, workspace, allowed edits, existing work, relevant skill path/instructions, verification, and expected output. Supply long prompts through a file or stdin when supported, with proper shell quoting. Isolate overlapping edits; launch one process for the assignment and capture output and exit status.

Keep the user informed during long execution. Reuse supported native continuation for focused follow-ups. Exit zero is not proof of task correctness: inspect changes and evidence and verify material gaps. Stop only processes you created. External actions by the other harness require the same authorization as direct execution.

Return the actual harness/model/effort, workspace, source state, outcome, verification, and limitations. Reuse the owning workflow's report; no separate HTML report or persistent orchestration service is required.
