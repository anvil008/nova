---
model: gemini-3.7-flash
official_source_urls:
  - https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash
  - https://ai.google.dev/gemini-api/docs/prompting-strategies
fetched_date: 2026-09-02
extractor_version: 1.1.0
normalized_source_digests:
  https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash: 73fded168648a58631322b845b307afdd2eec8acec8649881094085bfec9e207
  https://ai.google.dev/gemini-api/docs/prompting-strategies: 02a91196f2be4df7c133e739fd2d8c60395b303f56330821e1f00864ff691124
---
# Gemini 3.7 Flash prompting guide

This extract applies Google's Gemini 3 guidance to `gemini-3.7-flash`.
Antigravity Teamwork is an orchestration surface, not a Gemini model capability,
so it is outside this model guide.

## Direct and structured prompts

Source: https://ai.google.dev/gemini-api/docs/prompting-strategies

> They respond best to prompts that are direct, well-structured, and clearly define the task and any constraints.

State the goal directly. Structure the task, context, constraints, and expected
output with consistent Markdown headings or XML-style delimiters.

## Critical instruction placement

Source: https://ai.google.dev/gemini-api/docs/prompting-strategies

> Prioritize critical instructions: Place essential behavioral constraints, role definitions (persona), and output format requirements in the System Instruction or at the very beginning of the user prompt.

Put critical behavior, role, and output requirements first rather than burying
them in supporting context.

## Explicit parameters

Source: https://ai.google.dev/gemini-api/docs/prompting-strategies

> Define parameters: Explicitly explain any ambiguous terms or parameters.

Name thresholds, formats, units, bounds, and decision rules explicitly wherever
the task could otherwise be interpreted more than one way.

## Long-context anchoring

Source: https://ai.google.dev/gemini-api/docs/prompting-strategies

> Structure for long contexts: When providing large amounts of context (e.g., documents, code), supply all the context first. Place your specific instructions or questions at the very end of the prompt. Anchor context: After a large block of data, use a clear transition phrase to bridge the context and your query, such as "Based on the information above..."

For long context, place the source material before the task, then anchor the
question to that context with a clear transition at the end.

## Verbosity

Source: https://ai.google.dev/gemini-api/docs/prompting-strategies

> Control output verbosity: By default, Gemini 3 models provide direct and efficient answers. If you need a more conversational or detailed response, you must explicitly request it in your instructions.

Request the desired verbosity instead of assuming the model will infer it.

## Thinking levels

Source: https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash

Quoted as spec-table fragments, verbatim and in the order they appear in the
versioned model page's property table:

> Input token limit 1,048,576 Output token limit 65,536

> Thinking Supported (low, medium, high)

> Note: minimal is not supported and returns an error.

Use low for latency-sensitive tasks, medium as the default balance, and high
for difficult reasoning, coding, or tool-heavy work where additional cost and
latency are acceptable. Unlike some other Gemini 3 models, `minimal` is not a
valid level here.

## Grounding and tools

Source: https://ai.google.dev/gemini-api/docs/prompting-strategies

> Gemini is able to use tools to avoid hallucinations in scenarios where it might otherwise produce incorrect responses. Grounding with Google Search connects the Gemini model to real-time web content, and should be enabled whenever the model may need to know obscure or recent facts. Gemini's code execution tool enables the model to generate and run Python code, and should be enabled whenever the model needs to perform any kind of arithmetic, counting, or calculation.

Enable grounding for obscure or time-sensitive facts. Enable code execution for
arithmetic, counting, or calculation rather than relying on unaided generation.
