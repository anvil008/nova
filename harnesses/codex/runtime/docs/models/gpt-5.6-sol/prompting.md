---
model: gpt-5.6-sol
official_source_urls:
  - https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6
fetched_date: 2026-09-03
extractor_version: 1.1.0
normalized_source_digests:
  https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6: 6005ec0311d2d8d23f2ae7ad93a910fb57cf4147b8e6f0fa0a50e6a8ae9aebda
---
# GPT-5.6 Sol prompting guidance

This is a deliberately small, attributed extract of the official GPT-5.6 model
guide, selected for the controls that Workcell can apply to Codex agents. The
quoted fragments are source text; the notes explain their Workcell application.

## Lean prompts

Source: https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6

> State each instruction once.

Remove repeated rules, examples, and tool descriptions one group at a time, and
rerun the same evaluations. Keep an example or style rule only when it encodes a
real requirement or closes a measured gap. Track prompt growth over long runs.

## Goals, constraints, and success criteria

Source: https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6

> success criteria

Prefer an outcome-focused brief: name the goal, relevant context, hard
constraints, evidence needed, success criteria, and required output shape. Do
not prescribe every step when the surrounding context already establishes the
intended level of work. Name ambiguities that should stop for a question.

## Intentional reasoning effort

Source: https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6

> Set reasoning.effort intentionally.

Start from the existing measured baseline, then compare the same effort and one
level lower on representative work. Use higher settings only when evaluation
shows a quality gain; reserve `max` for the hardest quality-first tasks and
compare it with `xhigh` for quality, latency, and cost.

Codex cannot express these API-only controls through prompting: the
`reasoning.effort` request field and `reasoning.mode: "pro"`. A Codex agent can
follow the outcome and verification instructions,
but a prompt cannot enable pro mode or change an unavailable effort setting.

## Relevant tools

Source: https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6

> relevant to the task

Expose only tools that the task needs, with concise descriptions of inputs,
outputs, and errors. Use direct calls when judgment, approval, citations, or
native artifacts matter. For a bounded data-processing stage, define its tools,
schema, evidence, concurrency, retries, stop condition, and direct-call handoff.

Programmatic Tool Calling, `allowed_callers`, and `program_output` are API-only
features that Codex cannot express merely through agent instructions. Codex can
still apply the routing principle with the tools its harness provides.

## Autonomy and approval boundaries

Source: https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6

> approval boundaries

Put one compact authorization policy in the prompt. Read-only analysis reports
results without implementing; build or fix requests authorize safe, in-scope
local edits and validation. Require confirmation before external writes,
destructive or costly actions, and material scope expansion. Explicitly name
safe local actions so routine work can continue without unnecessary pauses.

## Multi-agent use

Source: https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6

> multiple subagents in parallel

Delegate only when the task divides cleanly into independent workstreams and a
coordinator will synthesize the results. State ownership, interfaces, evidence,
and stopping conditions so parallel work does not overlap or repeat.

The guide's Responses API multi-agent beta is API-only and is not enabled by a
Codex prompt. Codex may use its own harness-provided agent controls when they are
available and authorized, but those controls are a separate capability.

## Evidence-grounded progress

Source: https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6

> required evidence

Define the evidence needed for both intermediate decisions and the final
answer. Progress updates should report observed results, unresolved risks, and
the next action; fewer calls or tokens count as improvements only when the
result still passes the task's evaluations.

## Final completeness

Source: https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6

> answer completeness

Evaluate the final assistant message separately from intermediate or structured
tool output. Before finishing, recheck the requested facts, decisions, caveats,
evidence, output format, and next steps. Optimize latency, tokens, calls, or
brevity only after the complete answer meets the required quality bar.
