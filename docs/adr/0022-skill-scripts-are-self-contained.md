# 22. Skill scripts are self-contained

## Status

Accepted

## Context

A design survey run with [`skills/code-refactor/references/design-heuristics.md`](../../skills/code-refactor/references/design-heuristics.md) found the same small helpers — envelope field validation, `nonempty_string`, the CLI error-driver shape, `substitute_tokens` — reimplemented near-identically across `skills/*/scripts/`, and `skills/build/scripts/waves.py` loading a sibling skill's file (`skills/plan/scripts/render_plan.py`) through `importlib` to borrow one validator. The three report-emitting skills also each carry a byte-identical `templates/report.css`, with the lockstep rule stated separately in all three `references/report-rendering.md` files.

Consolidating any of this into a shared module would create cross-skill runtime dependencies. But skills are packaged as standalone units: the Codex and Grok builders stage each skill directory as its own bundle, and an installed skill must run from whatever path its harness copied it to. A shared module would either be duplicated into every bundle by tooling that does not exist, or break the installed skill.

## Decision

Each `skills/<name>/scripts/` directory is self-contained: it imports nothing from outside its own skill directory, and nothing outside the repository's own tooling imports into it. Deliberate mirrored copies of small helpers are the accepted cost, and each carries a mirror-comment naming its source (the `label_names()` precedent in `skills/build/scripts/waves.py`). The `waves.py` `importlib` reach into the plan skill is removed in favour of such a mirrored copy.

Repository-level tooling under `scripts/` is not a skill and may depend on skill code — dependency points inward only. `scripts/render-diagrams.py` therefore reuses the plan skill's diagram layout engine rather than maintaining a second copy.

`templates/report.css` remains three byte-identical copies, one per report-emitting skill; a repository test asserts the identity so the lockstep rule is enforced once rather than stated three times.

## Consequences

Skill bundles keep working wherever a harness copies them, at the price of duplicated helpers that must be edited in every mirror. Future design surveys should not re-propose a shared `skills/` library while this ADR stands; a candidate that wants one must argue the packaging constraint itself has changed. Repo tooling gains a single diagram layout engine, and drift between the report stylesheets or a new cross-skill import fails tests instead of waiting for a reviewer to notice.
