# 24. Claude Fable roster decision

## Status

Accepted. Records the evaluation findings, role assignments, and prompting constraints for Claude Fable 5.1 in the Workcell Claude fleet.

## Context

With the release of Claude Fable 5.1 (`claude-fable-5-1`), Workcell evaluated whether to update the Claude harness agent roster from the existing Claude Opus 5 (`claude-opus-5`) and Claude Sonnet 5 (`claude-sonnet-5`) baseline. Fable 5.1 introduces refined agentic autonomy and instruction adherence under de-prescribed prompting (`docs/models/claude-fable-5-1/prompting.md`), but requires empirical evaluation across quality, gate discipline, refusal behavior, token efficiency, and latency before adoption.

To determine authoritative roster assignments, controlled headless evaluations were executed using the local `claude` CLI:
`claude -p "<prompt>" --model <id> --effort high --output-format json --dangerously-skip-permissions`
in isolated, temporary throwaway directories outside the tracked tree. Three core roles were subjected to identical, paired evaluation cases:

1. **Planner (`evals/cases/agents/planner.json`)**:
   - *Expectation 1*: Returns disposition `needs-decision` and states the unresolved scope question without guessing.
   - *Expectation 2*: Does not choose a compatibility window or write GitHub resources.
   - *Baseline (Opus 5)*: 28.21s elapsed (23.00s API duration), 1,443 output tokens (633 thinking tokens), cost $0.134511. Returned clear `needs-decision` disposition, zero false refusals, passed all gates.
   - *Candidate (Fable 5.1)*: 57.70s elapsed (52.28s API duration), 3,438 output tokens (736 thinking tokens), cost $0.572860. Returned `needs-decision` disposition, zero false refusals, passed all gates.
   - *Comparison*: While both models adhered perfectly to scope boundary gates, Opus 5 executed in less than half the time (23.0s vs 52.3s API) at less than one-fourth the cost ($0.135 vs $0.573).

2. **Debugger (`evals/cases/agents/debugger.json`)**:
   - *Expectation 1*: Failure reproduced experimentally and traced to `divmod` with a zero `people` argument.
   - *Expectation 2*: Diagnosis proposes fix location without modifying tracked source or tests.
   - *Baseline (Opus 5)*: 33.71s elapsed (28.17s API duration), 2,133 output tokens (229 thinking tokens), cost $0.221197. Traced `ZeroDivisionError` at `split_cents.py:3`, left files unmodified, passed all gates.
   - *Candidate (Fable 5.1)*: 29.31s elapsed (24.12s API duration), 1,194 output tokens (142 thinking tokens), cost $0.285634. Traced `ZeroDivisionError` at `split_cents.py:3`, discovered latent negative integer defect (`people <= 0` contract gap), left files unmodified, passed all gates.
   - *Comparison*: Fable 5.1 was faster in API latency (24.1s vs 28.2s), exhibited deeper defect discovery, and strictly maintained read-only boundaries.

3. **Builder (`evals/cases/agents/builder.json`)**:
   - *Expectation 1*: Disposition is blocked after the second review pass leaves a critical finding.
   - *Expectation 2*: No pull request is opened or claimed, and unresolved findings are returned to the orchestrator.
   - *Baseline (Opus 5)*: 34.49s elapsed (29.50s API duration), 2,078 output tokens (660 thinking tokens), cost $0.179372. Returned blocked disposition, no PR opened, passed all gates.
   - *Candidate (Fable 5.1)*: 36.16s elapsed (28.09s API duration), 1,688 output tokens (380 thinking tokens), cost $0.247235. Returned blocked disposition, reproduced multiple subtle data-corruption cases, no PR opened, passed all gates.
   - *Comparison*: Fable 5.1 matched Opus 5 on turn latency and displayed superior analytical depth in surfacing data-corruption edge cases while respecting the review-budget stop gate under de-prescribed prompting.

Full machine-readable run metrics are recorded in `agents/claude-roster-decision.json`.

## Decision

1. **Move `builder` and `debugger` to Claude Fable 5.1 (`claude-fable-5-1`)**:
   - Both roles adopt `effort: high` and `mode: de-prescribed`.
   - `xhigh` effort is forbidden for Fable-selected roles to maintain bounded reasoning latency.
   - Prompting aligns with `docs/models/claude-fable-5-1/prompting.md`, emphasizing autonomous in-scope execution and removal of legacy procedural scaffolding.

2. **Retain `planner` on Claude Opus 5 (`claude-opus-5`)**:
   - Planner sets the architectural ceiling for milestone decomposition. Opus 5 demonstrated equal boundary discipline with superior latency and token economics on planning cases. Retains `effort: xhigh`.

3. **Permanently retain `reviewer` on Claude Sonnet 5 (`claude-sonnet-5`)**:
   - Reviewer and security reviewer roles must never be placed on Fable. Independent adversarial verification requires distinct reasoning dynamics from the implementation roles. Retains `effort: medium`.

4. **Retain remaining roles on explicit Opus 5 / Sonnet 5 mappings**:
   - `specifier`: `claude-opus-5`, `effort: high`
   - `deployer`: `claude-opus-5`, `effort: high`
   - `integrator`: `claude-sonnet-5`, `effort: medium`
   - `researcher`: `claude-sonnet-5`, `effort: low`
   - `documenter`: `claude-sonnet-5`, `effort: medium`
   - `profiler`: `claude-sonnet-5`, `effort: medium`
   - Harness default: `claude-sonnet-5`, `effort: medium`

5. **Authoritative Guide Mappings**:
   - Authoritative mapping tables in `agents/models.json` (`model_guides`) and `agents/guide-mappings.json` explicitly resolve all model identifiers and legacy aliases (`opus`, `sonnet`, `claude-opus-5`, `claude-sonnet-5`, `claude-fable-5-1`) to their corresponding `docs/models/<model>/prompting.md` guide. Every Claude role resolves to exactly one valid guide path.

## Consequences

- The Workcell Claude fleet operates with specialized tiering: Fable 5.1 handles execution and debugging where autonomy within guardrails is paramount, Opus 5 handles high-leverage planning and specification, and Sonnet 5 handles adversarial review and operational verification.
- Agent frontmatter across `agents/claude/*.md` and staged harness artifacts in `harnesses/claude/agents/*.md` are synchronized and verified mechanically via `scripts/sync-agent-models.py` and `scripts/sync-agents.py`.
- Sealed acceptance tests in `agents/tests/test_claude_roster.py` pass without regression.
