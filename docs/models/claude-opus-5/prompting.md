---
model: claude-opus-5
official_source_urls:
  - https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5
fetched_date: 2026-09-02
extractor_version: 1.0.0
normalized_source_digests:
  https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5: 55f1366cfd61051a63f2030a209521960ca6e161bce35cac451c0917d80189e0
---
# Claude Opus 5 prompting extract

This extract summarizes guidance specific to Claude Opus 5. It intentionally
does not import operational conclusions from the Claude Fable 5.1 guide.

## Effort and capability

Start at the default `high` effort and evaluate lower settings liberally for
cost and latency: code review remains strong at lower effort. Move to `xhigh`
for the hardest coding and long-horizon agentic work. For reviews, ask for every
finding and filter severity later; conservative wording may be followed so
literally that real lower-severity findings are omitted.

## Tool use and thinking

Keep thinking enabled when possible and control cost with effort. With thinking
disabled, a tool call may appear as visible text instead of a structured call,
or internal XML may leak into the response. If disabling thinking is required,
allow a brief sentence before tool use, permit the model to say when no tool
fits, and prohibit internal or system XML tags.

For vision work, iterative crop and visual verification tools are a more
cost-effective lever than thinking alone.

## Narration and written output

Opus 5 narrates agentic work readily and often at greater length than earlier
Opus models. Specify the desired progress cadence: one opening sentence, brief
updates only for important findings or changes of direction, and a final answer
that leads with the outcome. Calibrate written deliverables separately so files
cover the substance without filler sections or redundant summaries.

## Delegation and scope

The model coordinates multi-agent work well but delegates more readily than
prior models. Reserve delegation for sizeable, genuinely independent tracks;
cap spawn depth, concurrency, and spend, and do not create a subagent merely to
double-check the lead's work.

Give the complete task specification up front, constrain narrow tasks to the
requested scope, and let the model run. It is strong at completing end-to-end
work, but can otherwise add steps that were not requested.

## Verification and self-correction

Opus 5 already performs verification and self-correction. Remove legacy prompts
that demand a separate final check, re-check, or verifier subagent, because they
compound its native behavior without improving quality. Ask it to narrate only
corrections that would change the user's code, conclusions, or decisions.
