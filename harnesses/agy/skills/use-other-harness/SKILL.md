---
name: use-other-harness
description: ONLY when the user explicitly asks to run a subagent in a DIFFERENT coding harness (Claude Code, Codex, or Antigravity) via headless mode. The user must name the harness, the model, and the effort. Never invoke this for automatic cross-harness routing — it is an explicit, user-triggered escape hatch, not a router.
---

# Use Another Harness (Headless)

Spin up a one-shot subagent in another harness by calling its headless CLI directly.

Invocation: `/workcell:use-other-harness`
Prompting Reference: [`docs/models/gemini-3.8-flash/prompting.md`](../../runtime/docs/models/gemini-3.8-flash/prompting.md)

You are the orchestrator ([ADR 0028](../../runtime/docs/adr/0028-planner-owned-research-and-three-harnesses.md)): you own requirements, user decisions, budgets, dispatch, and final evaluation. Read source to frame goals and review evidence. Delegate new plans and bounded development briefs to one planner, which may manage an authorized researcher team. Delegate implementation, runnable test authorship, and independent verification to specialists. Accept implementation from mechanical gate output and handoff records, preserving source-bound evidence. Dispatch specialists with Antigravity's `invoke_subagent` and run VCS and gate commands with `run_command`. Use `agents/models.json` and [`anvil.agent-handoff/v1`](../../runtime/handoff.md).

## Critical Constraints

- **Goal:** Execute a bounded leaf task inside a distinct foreign coding harness via headless CLI execution upon explicit user instruction.
- **Constraints:** Never invoke automatically as a router. The user must explicitly request the run and specify the harness, model, and effort. This is strictly a leaf execution capability.
- **Success Criteria:** Bounded leaf execution completes in isolation, output captured into structured handoff, and results integrated.

## Ordered Gates

Execution proceeds through four strict, ordered gates:

1. **explicit user request**: Verify user explicitly requested running a task in a different coding harness.
2. **named harness model and effort**: Confirm user named the target harness, model ID, and reasoning effort.
3. **headless leaf execution**: Launch foreign CLI in headless mode via `run_command` within a scoped workspace.
4. **result handoff**: Capture structured output conforming to `anvil.agent-handoff/v1` and integrate findings.

## When to Use

Only when the **user explicitly asks** to run work in another harness, and only after they have specified:

- **harness** — `claude` (Claude Code) · `codex` (Codex) · `antigravity` (`agy`)
- **model** — the exact model id for that harness
- **effort** — the reasoning effort (where the harness supports it)

If any of the three is missing, ask for it. Do not guess a model or effort, and do not pick a harness on the user's behalf.

## Headless Invocation Per Harness

Run in the target repo/dir; pass the task as the prompt (long briefs via stdin/a file); capture the result; launch in the background for long jobs and report back when it exits.

**Claude Code**

```bash
claude -p "<task prompt>" --model <model> --effort <low|medium|high> \
  [--agent <name>] --dangerously-skip-permissions
```

**Codex**

```bash
codex exec --cd <dir> -m <model> \
  -c model_reasoning_effort="<low|medium|high>" \
  --approve-for-me -o <out.txt> "<task prompt>"   # long brief: append  < brief.md
```

**Antigravity (`agy`)**

```bash
agy -p "<task prompt>" --model <model> --effort <low|medium|high> \
  --dangerously-skip-permissions
```

## Procedure

1. **Validate explicit request.** Verify that the user provided an explicit prompt to execute via another coding harness. Never trigger this skill as an automatic router.
2. **Check required parameters.** Ensure harness, model, and effort are all specified. If any parameter is absent, halt and request clarification from the user. Never guess model or effort.
3. **Execute headless leaf CLI.** Run the command via `run_command` in an isolated workspace using the appropriate CLI invocation above.
4. **Capture and integrate result.** Ingest the leaf command output conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md) and report findings.

## Notes

- Each command auto-approves tools inside a workspace sandbox (`--approve-for-me` / `--dangerously-skip-permissions`), so scope it to one repo/dir and review the diff after.
- For long runs, launch in the background and wait for the process to exit rather than polling; then read the captured output (`-o` file or stdout) and summarize it.
- Structured result: Codex `-o <file>`; `agy --json-schema <schema>`; Claude `--output-format json`.
- This is a leaf capability. The spawned agent does one bounded job and returns its output; it does not orchestrate, and you own integrating whatever it produced.

## Boundaries

This is a leaf capability. The spawned agent does one bounded job and returns its output; it does not orchestrate, and you own integrating whatever it produced. Never attempt multi-hop routing between harnesses. Never guess model or effort parameters.

Based on the requirements and constraints above, execute the use-other-harness workflow systematically.
