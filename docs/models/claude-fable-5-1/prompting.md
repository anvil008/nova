---
model: claude-fable-5-1
official_source_urls:
  - https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1
fetched_date: 2026-09-02
extractor_version: 1.0.0
normalized_source_digests:
  https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1: 08fb81ba73f9c158f8d81aa59b974082ea8f8d162291a1f3f45e298bc9f6044c
---
# Claude Fable 5.1 prompting extract

This is a concise, model-specific synthesis of the official Claude Fable 5.1
prompting guide. The labels below express Workcell's operational conclusions;
they are not headings copied from Anthropic's page.

## Workcell findings attributed to Claude Fable 5.1

- **De-scaffolding:** Remove legacy prompt scaffolding that suppresses narration,
  forces a fixed update cadence, or otherwise compensates for behavior from an
  earlier model. Add a short, positive instruction only when evaluation shows a
  remaining gap.
- **Goals and boundaries:** Treat the user's request or approved plan as the
  deliverable. Make routine judgment calls, finish every in-scope part, avoid
  nearby cleanup, and stop only for destructive actions or a genuine scope
  decision.
- **Evidence-backed progress:** Before a state-changing action, verify that the
  observed evidence supports that specific action. During long tool chains,
  expose brief updates that say what was found and what happens next.
- **Autonomy:** For reversible steps already authorized by the request, proceed
  without asking permission and do not end on an unexecuted plan. A request for
  analysis alone remains analysis; it does not authorize a fix.
- **Asynchronous delegation:** When subagents handle independent work, let the
  lead continue useful work instead of forcing it to wait. Return completed
  subagent results later and retain an explicit wait mechanism.
- **Wiki-only memory:** Persist reusable project knowledge in the designated
  project wiki rather than inventing hidden cross-run memory. Conversation
  compaction should preserve constraints and current state, while durable
  lessons belong in that explicit store.
- **Final re-grounding:** Close with a self-contained recap of the outcome,
  evidence, changes, and remaining work so the last message makes sense even
  when intermediate tool output is hidden.
- **Fresh-context verification:** A compacted session should restart from one
  complete summary and reason afresh. Search or retrieve fast-moving facts at
  the point of use instead of trusting partial or stale familiarity.
- **Refusal sensitivity:** Benign coding requests can still trip safeguards.
  Prefer bug-finding language over compile-check phrasing, explain unfamiliar
  languages, and keep base64 tool output out of model context when possible.

## Additional model-specific notes

Start effort at `high`, then sweep all supported levels against task-specific
evaluations because effort names do not represent the same thinking budget as
in Fable 5. At low effort, explicitly trigger search for unfamiliar or
fast-moving names. At `xhigh` and `max`, leave enough output budget for both
reasoning and a long deliverable.

Keep conversation history append-only, including returned thinking blocks.
Use turn-scoped or mid-conversation system messages for changing reminders and
instructions. If client-side compaction is necessary, replace the prior history
with one complete summary instead of replaying thinking blocks against a changed
prefix.

Prefer targeted file edits over whole-file rewrites. For dense visual inputs,
provide crop, zoom, and visual-verification tools so the model can inspect
details iteratively.
