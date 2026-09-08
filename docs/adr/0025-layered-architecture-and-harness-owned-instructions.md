# 25. Layered Architecture and Harness-Owned Instructions

## Status

Accepted. This decision supersedes the shared-body generation model of [ADR 0005](0005-unified-cross-harness-plugin-architecture.md), while preserving its wrapper history and maintaining [ADR 0023](0023-installs-are-self-contained-copies.md) as the deployment and installation authority.

## Context

Nova previously attempted to maintain agent and skill instructions as shared source bodies with conditional tags (`<!-- only:... -->`) and macro token substitutions, projecting them down into each harness wrapper. As Nova expanded to four distinct harnesses—Claude Code, Codex, Antigravity, and Grok Build—this shared-body approach broke down under conflicting foundation-model prompt idioms, varying execution capabilities, and distinct native plugin systems.

Model guides under `docs/models/` document the upstream specifications and prompting constraints of each platform, validated continuously by our automated guide freshness check (`docs/models/check/check_guides.py --check`). Furthermore, empirical evaluation determined the final model roster across harnesses: Claude relies on Opus and Sonnet (with the measured Fable decision recorded in ADR 0024 de-prescribing Fable for standard roles), Codex runs on GPT-5.6 Sol, Antigravity operates on Gemini 3.8 Flash, and Grok Build is pinned to grok-4.6. Supporting these distinct platforms requires harness-native instruction bodies rather than lossy shared macros.

## Decision

We establish a layered architecture based on shared contracts and harness-owned instructions:

1. **Shared Contracts Registry**: All cross-harness specifications and interfaces are defined centrally in `contracts/harness-contracts.json`. Shared contracts establish the authoritative definition for all 10 agents and 16 skills, eliminating ambiguity across implementations.

2. **Four Harness-Owned Families**: Four distinct harness families—claude, codex, antigravity (agy), and grok—fully own their instructions, agent definitions, skill documents, and runtime adapters under `harnesses/<harness>/`. Each harness team authors native prompt bodies tailored to that environment's capabilities.

3. **Omission Rule**: We enforce an explicit omission rule for optional harness capabilities: any optional feature unsupported by a given harness must be omitted with explanatory notes in the registry, whereas any missing required contract value must fail immediately during validation.

4. **Cross-Harness Evals**: The unified evaluation suite (`evals/run_evals.py`) runs across each harness to enforce parity, contract compliance, and behavioral correctness for every supported platform.

5. **Standalone Dist Artifacts**: Each harness stager produces a completely self-contained, standalone dist tree under `dist/<harness>/` with real file copies and zero symlinks per ADR 0023.

## Consequences

- Each harness enjoys idiomatic prompt engineering tailored to its target model without compromising other harnesses.
- Central contracts in `contracts/harness-contracts.json` prevent functional divergence and ensure strict interface parity.
- Mechanical gates (`check_guides.py`, `check-contract-parity.py`, `sync-agents.py --check`, `sync-skills.py --check`) enforce synchronization and integrity automatically in CI.
- Distribution artifacts are isolated, self-contained directories free of symlink traps.
