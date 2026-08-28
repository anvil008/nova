# Swarm Coder

A small, native multi-agent coding system for **Claude Code, Codex, and Antigravity**.
You give a goal; a skill turns it into a plan and GitHub tasks; specialist agents do the
work — some in parallel — and two mechanical gates keep them honest.

## Agents (`agents/`)
- **research** — explore code / docs / runtime / prior-art; read-only. Owns `read-the-damn-docs`, `find-docs`.
- **builder** — implement one issue end-to-end (branch → change → PR); the only writer, never commits to `main`. Owns `jj`, `full-output-enforcement`, `builder-frontend`.
- **code-reviewer** — read-only assurance, one instance per review lens. Owns `frontend-review`.
- **docs** — the docs-scoped writer: update-don't-duplicate, lean `CLAUDE.md`/`AGENTS.md`, ADRs. Owns `grill-with-docs`.

## Skills (`skills/`)
Orchestration: **planner** (→ HTML plan + GitHub issues), **build** (parallel builder waves),
**research** (area fan-out), **code-review** (lens fan-out + adversarial verify).
Lifecycle: **docs** (standardize + ADRs + docs-check), **deploy** (human-gated ship).
Plus **use-other-harness** — an explicit headless run in another harness.

## Mechanical gates
- **tdd-guard** (`cmd/tdd-guard`) — test-first for code: seal a failing test → implement → verify green → diff-review. Enforced on the builder via `build-hooks`.
- **docs-check** (`skills/docs/scripts/docs_check.py`) — instruction-file budget + ADR format.

## Flagship workflow
planner → **you approve** → GitHub issues (milestone) → parallel builders → review →
integrate + retest → repeat. GitHub is the durable, resumable task board.

## tdd-guard

```sh
go build -o ~/.local/bin/tdd-guard ./cmd/tdd-guard
tdd-guard seal   --tests <globs> --red-command <argv...>
tdd-guard verify --green-command <argv...>
tdd-guard diff-review record --findings <file>
```

Decisions are recorded as ADRs under [`docs/adr/`](docs/adr/).
