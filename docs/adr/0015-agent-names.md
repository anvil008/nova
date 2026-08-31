# 15. Agents are named for the worker, not the workflow

## Status

Accepted

## Context

Five agents carried the name of the workflow they serve rather than the job they do:
`test-author`, `code-reviewer`, `research`, `docs`, and `deploy`. Three of them —
`research`, `docs`, `deploy` — collided outright with the skills of the same name, so
"dispatch `docs`" was ambiguous between the orchestration skill and the agent it
dispatches, and `scripts/build-codex-plugin.py` had to namespace every agent as
`agent-<name>` to keep the two apart in one flat skill directory. The remaining two were
merely long: `test-author` described a task, and `code-reviewer` repeated the `code-review`
skill it works inside.

Skills are workflows; agents are the workers a workflow dispatches. The names should say
which is which without a prefix or a sentence of context.

## Decision

Rename the five agents. Skills keep their names.

| old agent id    | new agent id   | the skill that keeps the old name |
| --------------- | -------------- | --------------------------------- |
| `test-author`   | `oracle`       | —                                 |
| `code-reviewer` | `reviewer`     | `code-review`                     |
| `research`      | `researcher`   | `research`                        |
| `docs`          | `scribe`       | `docs`                            |
| `deploy`        | `deployer`     | `deploy`                          |

`planner`, `builder`, `debugger`, `benchmarker`, and `integrator` are unchanged: each
already names a worker. The one remaining agent/skill name collision is `planner`, which
is deliberate — the skill orchestrates the agent of the same name.

The skill `code-reviewer-frontend-review` becomes `reviewer-frontend-review`, since it is
named after the agent that owns it rather than after a workflow.

The rename covers the current state of the repository only: `agents/bodies/`, `agents.json`,
`models.json`, the Codex gate snippets, the generated per-harness definitions, every skill
that dispatches one of them, the eval cases and their routing owners, the tests that pin
those names, the README, `docs/gates.md`, and the README diagram sources. Accepted ADRs
0001–0014 keep the old names: an ADR records what was decided when it was decided, and
rewriting one to match a later rename would falsify the record. Read them with this table.

## Consequences

A dispatch now reads unambiguously — "dispatch the `scribe`" cannot be confused with "run
the `docs` skill" — and the Codex `agent-` prefix is a readability aid rather than a
collision fix.

Every reference to an old id outside `docs/adr/`, `docs/plans/`, `docs/research/`, and
`plan.sidecar.json` is stale, and the completeness gate is a word-boundary grep over
`agents/`, `skills/`, `evals/`, `scripts/`, the README, and the current-state docs.

Routing is affected only where a description changed: the `build` and `research` skill
descriptions were reworded around the new agent names, and `evals/run_evals.py --min-rank1`
holds the rank-1 floor at 77%. Anyone reading history — old ADRs, plan folios, research
packets, or `CHANGELOG` entries before this one — must map the old names through the table
above.
