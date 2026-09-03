# 26. Antigravity Roster Moves to Gemini 3.8 Flash

## Status

Accepted. Records the decision to move the Antigravity harness fleet to Gemini 3.8 Flash following upstream release and documentation updates.

## Context

Google released Gemini 3.8 Flash and updated its authoritative latest-model documentation (`https://ai.google.dev/gemini-api/docs/latest-model`) to describe Gemini 3.8 Flash. The versioned model page (`https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash`) and prompting strategies guide (`https://ai.google.dev/gemini-api/docs/prompting-strategies`) document the operational characteristics: 1M token context window, thinking levels at low, medium, and high (with minimal unsupported), and structured sequential generation.

Workcell previously operated its Antigravity roster on Gemini 3.7 Flash ([ADR 0025](0025-layered-architecture-and-harness-owned-instructions.md)). With upstream swapping `latest-model` to 3.8 Flash, our automated guide freshness checks require an authoritative guide for 3.8 Flash while preserving the versioned 3.7 Flash documentation for historical stability.

## Decision

1. **Move Antigravity Roster to Gemini 3.8 Flash**:
   - Update `agents/models.json` so every Antigravity role resolves to `gemini-3.8-flash` (session-wide reasoning effort `high`).
   - Sync all agent frontmatter under `agents/agy/**` and harness-owned agents under `harnesses/agy/agents/**` to `gemini-3.8-flash`.
   - Update harness-owned skills under `harnesses/agy/skills/**` to cite `docs/models/gemini-3.8-flash/prompting.md`.
   - Update headless command configuration in `harnesses/agy/runtime/capabilities.json`.

2. **Retain Pinned Gemini 3.7 Flash Guide**:
   - Keep `docs/models/gemini-3.7-flash/prompting.md` pinned to its versioned upstream URL (`https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash`) as historical documentation.

3. **Authoritative Guide for Gemini 3.8 Flash**:
   - Establish `docs/models/gemini-3.8-flash/prompting.md` sourcing upstream latest-model, model, and prompting-strategies documentation, validated by unit and live-fresh extract tests.

## Consequences

- Automated guide freshness (`docs/models/check/check_guides.py --check`) now validates seven model guides across all supported harness providers.
- All Antigravity agents, orchestrators, and runtime artifacts operate under Gemini 3.8 Flash prompting guidance.
- Contract parity, agent sync, skill sync, and cross-harness evaluation suites remain green across all four supported harnesses.
