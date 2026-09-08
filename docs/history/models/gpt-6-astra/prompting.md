---
model: gpt-6-astra
official_source_urls:
  - https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra
fetched_date: 2026-09-06
extractor_version: 1.1.0
normalized_source_digests:
  https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra: 0e91b3ddd9d74a0bfdd24475287d2dc9ac812448f3af46d4caecc7044ba94eed
---
# GPT-6 Astra prompting guidance

Source: https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra

> preserve your current effective reasoning effort

The official migration guide recommends retaining effort when moving from Sol,
except unsupported `none` or `minimal` settings. It also identifies sensitivity
to conflicting instructions, unnecessary clarification pauses, delegation
frequency, verbose responses, and excessive verification as behaviors to tune.

## Nova application

Nova's Codex routes use `gpt-6-astra` with the existing role efforts in
`agents/models.json`: high for planning, specifying,
building, debugging, and deployment; medium for review, integration, documentation,
and profiling; low for research. Keep model and effort explicit on dispatch.
The launcher owns these settings; prose cannot change an unavailable runtime knob.

Give each agent the assignment, ownership, base, acceptance criteria, evidence
requirements, and completion condition. Continue authorized work through handoff;
ask only about unresolved decisions that materially affect the result. Prepare a
reviewable result before requesting any still-required approval.

Keep Nova's authorship separation: the specifier seals acceptance tests, the
builder implements, an independent reviewer reviews, and the integrator tests the
combined candidate. Dispatch independent issue pairs only with disjoint ownership
and a shared accepted base. Preserve the existing ban on recursive builder fan-out.

Builders run the bound acceptance command and relevant targeted regression checks;
integrators run the project's full required check set once per unchanged combined
candidate. Additional tests need a concrete failure or unresolved concern.

Readiness requires current guard evidence. A summary or final-answer claim cannot
replace a command record. Keep review findings, logs, and handoffs outside the
source tree so recording evidence cannot invalidate the tree being verified.

Use concise progress updates that identify a finding, uncertainty, or next action.
Audit contradictory skill and agent rules when behavior diverges before increasing
prompt length or effort. Evaluate Astra on the same execution traces used for Sol;
retain historical model guides and evaluation fixtures for comparison.

## API boundary

Nova launches Codex; this change adds no direct API integration. For a future
API executor, consult the official guide's Responses tool-calling and unsupported
parameter requirements rather than copying CLI settings into an API request.
