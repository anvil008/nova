---
name: use-other-harness
description: ONLY when the user explicitly asks to run a subagent in a DIFFERENT coding harness (Claude, Codex, Antigravity, or Grok Build) via headless mode. The user must name the harness, the model, and the effort. Never invoke this for automatic cross-harness routing — it is an explicit, user-triggered escape hatch, not a router.
---

# Use Another Harness (Headless)

Spin up a one-shot subagent in another harness by calling its headless CLI directly. This replaces foreign-dispatch protocols with direct headless execution: you launch a process, wait on it, and capture the output.

Invocation: `/workcell:use-other-harness`
Prompting Reference: [`docs/models/gpt-5.6-sol/prompting.md`](../../runtime/docs/models/gpt-5.6-sol/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you hold human gates, run headless processes via shell execution, and read handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never invoke this skill automatically as a router; it is solely an explicit user escape hatch for leaf execution.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Execute a bounded leaf task inside a distinct foreign coding harness via headless CLI execution upon explicit user instruction.
- **Constraints and Boundaries:** Never invoke automatically as a router. The user must explicitly request the run and specify the harness, model, and effort. Execution is restricted to a leaf task.
- **Success Criteria:** Bounded leaf execution completes in isolation, output captured into structured handoff, and results integrated.

## Ordered Gates

Execution proceeds through four strict, ordered gates:

1. **explicit user request**: Verify user explicitly requested running a task in a different coding harness.
2. **named harness model and effort**: Confirm user named the target harness, model ID, and reasoning effort.
3. **headless leaf execution**: Launch foreign CLI in headless mode within a scoped workspace.
4. **result handoff**: Capture structured output conforming to `anvil.agent-handoff/v1` and integrate findings.

## Headless Invocation Per Harness

Only execute when the user explicitly names the harness, model, and reasoning effort:

- **Claude**
  ```bash
  claude -p "<task prompt>" --model <model> --effort <low|medium|high> --dangerously-skip-permissions
  ```

- **Codex**
  ```bash
  codex exec --cd <dir> -m <model> -c model_reasoning_effort="<low|medium|high>" --approve-for-me -o <out.txt> "<task prompt>"
  ```

- **Antigravity (`agy`)**
  ```bash
  agy -p "<task prompt>" --model <model> --effort <low|medium|high> --dangerously-skip-permissions
  ```

- **Grok Build (`grok`)**
  ```bash
  grok -p "<task prompt>" -m <model> --effort <low|medium|high> --always-approve
  ```

## Harness Limitations

API-only model controls (such as dynamic request-level reasoning effort or pro mode toggles) and API-only orchestration features are unsupported in Codex skill prompts; execution relies on native harness tooling and specialist dispatch.
