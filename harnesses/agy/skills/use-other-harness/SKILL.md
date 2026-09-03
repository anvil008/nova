---
name: use-other-harness
description: ONLY when the user explicitly asks to run a subagent in a DIFFERENT coding harness (Claude Code, Codex, Antigravity, or Grok Build) via headless mode. The user must name the harness, the model, and the effort. Never invoke this for automatic cross-harness routing — it is an explicit, user-triggered escape hatch, not a router.
---

# Use Another Harness (Headless)

Spin up a one-shot subagent in another harness by calling its headless CLI directly.

Invocation: `/workcell:use-other-harness`
Prompting Reference: [`docs/models/gemini-3.7-flash/prompting.md`](../../runtime/docs/models/gemini-3.7-flash/prompting.md)

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you hold the human gates, run headless processes via `run_command`, and read handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never invoke this skill automatically as a router; it is solely an explicit user escape hatch. Per the Gemini 3.7 Flash guide, execute instructions literally, enforce strict parameter checks, and avoid speculative routing.

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

- **harness** — `claude` (Claude Code) · `codex` (Codex) · `antigravity` (`agy`) · `grok` (Grok Build)
- **model** — the exact model id for that harness
- **effort** — the reasoning effort (where the harness supports it)

If any of the three is missing, ask for it. Do not guess a model or effort, and do not pick a harness on the user's behalf.

## Procedure

1. **Validate explicit request.** Verify that the user provided an explicit prompt to execute via another coding harness. Never trigger this skill as an automatic router.
2. **Check required parameters.** Ensure harness, model, and effort are all specified. If any parameter is absent, halt and request clarification from the user.
3. **Execute headless leaf CLI.** Run the command via `run_command` in an isolated workspace:
   - For Claude Code: `claude -p "<task prompt>" --model <model> --effort <effort> --dangerously-skip-permissions`
   - For Codex: `codex exec --cd <dir> -m <model> -c model_reasoning_effort="<effort>" --approve-for-me -o <out.txt> "<task prompt>"`
   - For Antigravity (`agy`): `agy -p "<task prompt>" --model <model> --effort <effort> --dangerously-skip-permissions`
   - For Grok Build: `grok -p "<task prompt>" -m <model> --effort <effort> --always-approve`
4. **Capture and integrate result.** Ingest the leaf command output conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md) and report findings.

## Boundaries

This is a leaf capability. The spawned agent does one bounded job and returns its output; it does not orchestrate, and you own integrating whatever it produced. Never attempt multi-hop routing between harnesses.

Based on the requirements and constraints above, execute the use-other-harness workflow systematically.
