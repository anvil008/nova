---
model: claude-sonnet-5
official_source_urls:
  - https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5
fetched_date: 2026-09-02
extractor_version: 1.1.0
normalized_source_digests:
  https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5: c57abd8001825503cd98f0996fdf5743ca29ed8ca6bb6d7597245a9738521b1d
---
# Claude Sonnet 5 prompting extract

This extract summarizes guidance specific to Claude Sonnet 5. It intentionally
keeps that model's defaults and migration advice separate from the Claude Fable
5.1 guide.

## Effort and adaptive thinking

Effort defaults to `high`; use `xhigh` for the hardest coding and agentic tasks,
`medium` for cost-sensitive work, and `low` only for short, scoped,
latency-sensitive tasks. At lower levels, the model adheres closely to the
requested scope and may under-think complex work, so raising effort is the first
remedy.

Adaptive thinking is on by default. Manual budgeted extended thinking is not
supported. Leave headroom in `max_tokens` at high effort and above because
thinking and tool calls share the output limit, and revisit limits set for the
older tokenizer.

## Tool use and verification

Sonnet 5 reaches for tools and runs self-verification loops more readily than
Sonnet 4.6, especially at `high` and `xhigh`. Thinking-disabled requests use
tools less often, so integrations that rely on search should state when and why
tools are required. In code-review prompts, request comprehensive reporting and
defer severity or confidence filtering; a conservative instruction can reduce
reported recall even when investigation remains thorough.

## Progress updates

The model provides regular progress updates during long agentic traces. Remove
fixed-cadence scaffolding such as status after every few calls. If update length
or content needs tuning, describe the desired messages directly and supply
positive examples.

## Literal instruction following

Sonnet 5 is more literal, particularly at lower effort: it applies instructions
to the named item rather than silently generalizing them. State scope explicitly
when a rule must apply to every section, file, or result. This precision is
useful for structured extraction and predictable pipelines.

## Response and product behavior

Response length follows task complexity; prompt explicitly when a product
requires a stable degree of concision. Specify voice in the system prompt rather
than relying on sampling parameters, which are not accepted at non-default
values.

For autonomous coding products, provide the task, intent, and constraints in the
first user turn and use `high` or `xhigh` effort. For open-ended frontend work,
give a concrete visual direction or ask the model to propose distinct options
before implementation instead of relying on generic style prohibitions.
