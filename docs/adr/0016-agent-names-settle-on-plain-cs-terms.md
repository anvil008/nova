# 16. Agent names settle on plain computer-science terms

## Status

Accepted

## Context

[ADR 0015](0015-agent-names.md) fixed the real problem — agents were named for the
workflow they serve rather than the job they do — but three of the names it left standing
are the wrong words for the jobs they name.

`oracle` collides with the thing the agent consumes. Every `acceptanceTests` entry carries
an `oracle` field, the observable pass condition the planner writes and the agent turns
into an assertion, and that field name is fixed in the sidecar contract, the GitHub issue
body, the handoff record, and the planner's own vocabulary. Naming the agent after the
field meant the repository had to say "the `oracle` agent" every time it meant the worker,
which is the same sentence of context ADR 0015 set out to remove.

`benchmarker` and `scribe` are not collisions, they are jargon. `benchmarker` names one
tool the job happens to use rather than the job — the agent measures a distribution, and
the standard word for that worker is `profiler`. `scribe` is archaic for something the
rest of the repository already calls documentation; `documenter` says it in the vocabulary
the `docs` skill and `docs_check.py` already use.

## Decision

Rename three more agents. Skills keep their names, and so does the acceptance-test
`oracle` field.

| old agent id  | new agent id | where the old name came from     |
| ------------- | ------------ | -------------------------------- |
| `oracle`      | `specifier`  | ADR 0015 (was `test-author`)     |
| `benchmarker` | `profiler`   | original; ADR 0015 left it alone |
| `scribe`      | `documenter` | ADR 0015 (was `docs`)            |

ADR 0015's names for these three — the two it renamed and the one it affirmed — are
superseded. `builder`, `debugger`, `deployer`, `integrator`, `planner`, `researcher`, and
`reviewer` are unchanged, and ADR 0015's `test-author` → `oracle` → `specifier` chain is
the only double rename.

The **`oracle` field keeps its name everywhere** — in `plan.sidecar.json`, the sidecar
contract, `agents/handoff.md`, the rendered issue checklist, and the planner and specifier
bodies. It was never the ambiguous half of the collision; the agent was.

The workflow skills are untouched: `docs` dispatches the `documenter`, `perf` dispatches
the `profiler`, and `build` Phase 1 dispatches the `specifier`.

The rename covers the current state of the repository only: `agents/bodies/`,
`agents.json`, `models.json`, the Codex gate snippet, the generated per-harness
definitions, the agent-owned skill symlinks under `agents/agy/`, every skill that
dispatches one of them, the eval cases and their routing owners, the tests that pin those
names, the guard's comments, the README, `docs/gates.md`, and the README diagram sources.
Accepted ADRs 0001–0015, `docs/plans/`, `docs/research/`, and `plan.sidecar.json` keep the
old names: an ADR records what was decided when it was decided, and rewriting one to match
a later rename would falsify the record.

## Consequences

Sentences that had to disambiguate an agent from a field no longer do: the planner body
now reads "an observable pass condition that the `specifier` can turn into a real failing
assertion", with no "agent" needed to say which `oracle` is meant.

Every reference to `oracle`-as-agent, `benchmarker`, or `scribe` outside `docs/adr/`,
`docs/plans/`, `docs/research/`, `plan.sidecar.json`, and prior `CHANGELOG` entries is
stale. The completeness gate is a word-boundary grep for `benchmarker` and `scribe` over
`agents/`, `skills/`, `evals/`, `scripts/`, the README, and the current-state docs, plus a
hand review of each surviving `oracle` — because a bare grep cannot tell the field from
the agent, and the field is the one that stays.

Routing is affected only where a description or a dispatch sentence changed;
`evals/run_evals.py --min-rank1` holds the rank-1 floor at 77%. Anyone reading history —
ADRs 0001–0015, plan folios, research packets, or `CHANGELOG` entries before this one —
must map the old names through this table and ADR 0015's.
