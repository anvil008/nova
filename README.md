# Swarm Coder

A small, native multi-agent coding system for **Claude Code, Codex, and Antigravity**.
You give a goal; a skill turns it into a plan and GitHub tasks; specialist agents do the
work — some in parallel — and mechanical gates keep them honest.

## Agents (`agents/`)
Organized by harness under `agents/claude/`, `agents/codex/`, and `agents/agy/` with platform-tailored frontmatter, tools, and gate instructions:
- **research** — explore code / docs / runtime / prior-art; read-only.
- **builder** — implement one issue end-to-end (branch → change → PR); the only code writer, never commits to `main`. Owns `jj` and `builder-frontend`.
- **code-reviewer** — read-only assurance, one instance per review lens (correctness / security / performance / tests / api-contract / frontend). The `frontend` lens runs `code-reviewer-frontend-review` over a Playwright viewport matrix.
- **docs** — the docs-scoped writer: update-don't-duplicate, lean `CLAUDE.md`/`AGENTS.md`, and ADRs.

Deploy agents and skills into all present harnesses with:
```sh
scripts/install-harness.sh --install
```
Or target a specific harness with `--harness <claude|codex|agy>`. `--uninstall`
removes only symlinks owned by this repository: harness agents, skills, generated Codex
TOMLs, and the `~/.local/bin/build-*` and `tdd-guard` links. Foreign files, directories,
and symlinks are refused or left in place and reported. The installers avoid GNU-only
shell features and are tested with the Bash 3.2 shipped on stock macOS.

**This repository is the single source.** Everything a harness sees is a symlink back into
it — agents, skills, and the `~/.local/bin/build-*` hooks — so editing a file here takes
effect immediately with no re-install. Codex is the one exception: its harness requires a
generated TOML with the agent body embedded as an escaped string, so it cannot read the
markdown directly. That file is generated into `dist/` (gitignored) and symlinked from
`~/.codex`, which means a change to `agents/codex/*.md` does need a re-run.

## Centralized Skills (`skills/`)
Skills live in a harness-agnostic structure under `skills/`, and the installer symlinks them
into each harness. The set is *discovered*, not listed — every directory under `skills/` is a
skill, so adding one needs no change to the install script.
- **planner** — investigate a goal and produce an offline HTML implementation plan (`docs/plans/plan<NN>-<YYYYMMDD>-<title>.html`) and strict JSON sidecar, then reconcile into GitHub milestones/issues.
- **build** — execute approved plan waves in parallel across isolated jj workspaces. Features programmatic glob overlap detection to prevent concurrent builder collisions. Each builder reviews its own change-set (two passes) before opening a PR, then tears its workspace down.
- **research** — area fan-out and informational merging.
- **code-review** — adversarial code verification and multi-lens review aggregation, rendered to a self-contained HTML report and reconciled into GitHub issues (idempotent, marker-based, approval-gated — resolved findings auto-close).
- **docs** — standardize documentation in place, record ADRs, and run mechanical gate checks.
- **deploy** — human-gated production releases.
- **use-other-harness** — explicit headless run of a command or task in an alternative harness.
- **builder-frontend** — the builder's focused UI skill: clean, accessible, responsive frontends.
- **code-reviewer-frontend-review** — the method behind code-review's `frontend` lens, not a standalone review: static pass over changed components and styles, then Playwright across 4K, half-tiled 4K, QHD, 1080p, MacBook 16"/15"/13", small laptop, tablet, and phone.
- **review-fix-loop** — review, fix, re-review on a dedicated `loop-branch`, bounded to ten passes. Driven by the harness `/loop`; the skill owns the stop conditions (`converged` / `stalled` / `exhausted`) in a state file, because `/loop` re-invokes with a fresh context each tick.
- **jj** — Jujutsu VCS reference, vendored (MIT, © 2025 Josh Thomas). The builder's version control, including the workspace isolation the build waves rely on.

## Mechanical Gates & Hooks
The system combines blocking boundaries with explicitly advisory signals:

### Go Guard Gates (`cmd/tdd-guard`, `guard/`)
The `tdd-guard` executable is the harness-neutral guard (its runtime messages use the
historical `anvil-guard` name). Its enforced TDD contract is:

1. `seal` runs a failing RED command and binds its exact argument vector and digest to
   the sealed test files.
2. `verify` accepts only the same argument vector, requires it to pass after the seal,
   and rejects sealed tests changed before or during the run.
3. A necessary test amendment must use `reseal --reason <text>`, which records the
   before/after digests and invalidates older GREEN and diff-review evidence.
4. `diff-review record` binds findings to the current diff. `status --json` exposes the
   seal, bound argv, GREEN evidence, amendments, review freshness, and readiness used by
   the Stop gate.

`arch-check` records structural assertions (or an unverified result when `ast-grep` is
missing), but architecture results and optional coverage thresholds are advisory: they
do not make the Stop gate fail.

- **Hardened Security & Performance**:
  - *Bounded streaming SHA-256 digests*: Streams untracked-file content used by the
    working-diff digest through a 10 MiB limit; tracked diffs come from Git, while sealed
    tests and small state records still read their inputs directly.
  - *Cross-platform path normalization*: Normalizes backslash/forward-slash paths to prevent platform-specific bypasses of test/conformance rules.
  - *In-memory directory caching*: Caches repository directory walking during architecture compliance checks (`arch-check`) to avoid quadratic filesystem traversals.

### Shell Hooks (`scripts/hooks/`)
Harness-aware pre-tool-use and post-tool-use scripts execute in response to agent actions:
- **build-format** — automatically runs formatting tools on modified source files.
- **build-lint** — triggers single-file linters and feeds advisory, non-blocking feedback directly into the agent's context.
- **build-guard** — a failing-closed command boundary: missing parsers, malformed or
  empty payloads, protected-branch mutations, and RAM-tmpfs build targets are denied.
  Its tokenizer corpus exercises quoting, wrappers, shell segments, Git, jj, and GitHub
  CLI bypass forms in `scripts/hooks/tests/test_hooks.sh`.
- **build-hooks** — wires test-first `tdd-guard` execution into writing or executing operations.
- **Cross-Platform Portability**:
  - Verified `jq` command availability at bootstrap.
  - Uses highly portable POSIX character-class regular expressions (e.g. `[[:alnum:]_]`, `[[:space:]]`) ensuring seamless execution across GNU (Linux) and BSD (macOS) grep implementations.
  - Integrates a robust multi-field tool-call payload extraction to parse JSON commands for both Claude (`.tool_input.command`) and Antigravity (`.toolCall.args.CommandLine` or `.toolCall.args.command`).
  - Automatically creates `.git/info/exclude` in `project-bootstrap.sh` to local-ignore configuration files invisibly to git diff.

Gate delivery differs by harness. Claude wires `build-guard` and the guard's
PreToolUse/PostToolUse/Stop/SubagentStop events, plus write-time format and advisory
lint hooks. Antigravity wires `build-guard`, guard PreToolUse/PostToolUse/Stop events,
and write-time format/lint hooks (it has no SubagentStop entry). Codex has no native
hook wiring in this repository: its builder instructions require explicit
`build-guard`, `tdd-guard seal/verify/diff-review`, and `status` calls.

### Docs Compliance (`skills/docs/scripts/docs_check.py`)
Enforces instruction file budgets (ensuring lean global files) and verifies proper formatting of ADRs.

## Bootstrap Setup
Ready a project folder (detect stack, install hook tools, and wire advisory gates) with:
```sh
scripts/project-bootstrap.sh [--install] [--with-hooks] [DIR]
```

## Flagship Workflow
```
planner ──> human approval ──> GitHub issues ──> parallel builders (with wave overlap check) ──> review ──> integrate + retest ──> deploy
```
GitHub serves as the durable, resumable task board.
The planner's reviewable HTML folios live in [`docs/plans/`](docs/plans/); the root
`plan.sidecar.json` is the machine-readable sidecar for the current approved plan.
Closed issues labelled `status:done` are durable completed work: planner reconciliation
does not reopen them unless explicitly asked, and build-wave derivation treats them as done.

## CI/CD Quality Gates
Our `.github/workflows/ci.yml` pipeline enforces 100% compliance across all commits and PRs:
1. **Go Verification**: Runs `go mod tidy` verification (verifying `go.mod` and `go.sum` match), builds all modules (`go build ./...`), and runs analysis (`go vet ./...`).
2. **Go Unit Testing**: Executes all tests under `./...` (including tdd-guard and repository state/lookups checks).
3. **Shell Hook Testing**: Runs `scripts/hooks/tests/test_hooks.sh` to verify hook script correctness and cross-platform compatibility.
4. **Python Skill Testing**: Runs automated unit tests for centralized skills (`planner`, `build`, `code-review`, `docs`, `research`).
5. **Docs Enforcement**: Executes `docs_check.py` to prevent any documentation or ADR regression.

---
Decisions are recorded as ADRs under [`docs/adr/`](docs/adr/).
