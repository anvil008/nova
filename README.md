# Swarm Coder

A small, native multi-agent coding system for **Claude Code, Codex, and Antigravity**.
You give a goal; a skill turns it into a plan and GitHub tasks; specialist agents do the
work — some in parallel — and mechanical gates keep them honest.

## Agents (`agents/`)
Organized by harness under `agents/claude/`, `agents/codex/`, and `agents/agy/` with platform-tailored frontmatter, tools, and hooks to ensure agent parity:
- **research** — explore code / docs / runtime / prior-art; read-only. Owns `read-the-damn-docs`, `find-docs`.
- **builder** — implement one issue end-to-end (branch → change → PR); the only writer, never commits to `main`. Owns `jj`, `full-output-enforcement`, `builder-frontend`.
- **code-reviewer** — read-only assurance, one instance per review lens. Owns `code-reviewer-frontend-review`.
- **docs** — the docs-scoped writer: update-don't-duplicate, lean `CLAUDE.md`/`AGENTS.md`, ADRs. Owns `grill-with-docs`.

Deploy agents and skills into all present harnesses with:
```sh
scripts/install-harness.sh --install
```
Or target a specific harness with `--harness <claude|codex|agy>`.

## Centralized Skills (`skills/`)
Skills are defined in a centralized, harness-agnostic structure under the `skills/` directory at the project root. The installation script projects these skills into the target harness:
- **planner** — investigate a goal and produce an offline HTML implementation plan and strict JSON sidecar, then reconcile into GitHub milestones/issues.
- **build** — execute approved plan waves in parallel across isolated worktrees. Features programmatic glob overlap detection to prevent concurrent builder collisions.
- **research** — area fan-out and informational merging.
- **code-review** — adversarial code verification and multi-lens review aggregation.
- **docs** — standardize documentation in place, record ADRs, and run mechanical gate checks.
- **deploy** — human-gated production releases.
- **use-other-harness** — explicit headless run of a command or task in an alternative harness.
- **builder-frontend** & **code-reviewer-frontend-review** — specialize frontend-focused task flows and visual assets reviews.

## Mechanical Gates & Hooks
The system enforces safety, correctness, and compliance via blocking and advisory mechanical gates:

### Go Guard Gates (`cmd/tdd-guard`, `guard/`)
The Go-based guard framework implements hardened runtime checks:
- **tdd-guard** — enforces test-driven development: seals a failing test (`tdd-guard seal`), requires the builder to write the implementation, and validates successful completion (`tdd-guard verify` / `tdd-guard diff-review`).
- **Hardened Security & Performance**:
  - *Streaming SHA-256 digests*: Processes files in a streaming manner bounded by a strict 10MB limit (`maxBytes`) to prevent unbounded memory consumption during diff digesting.
  - *Cross-platform path normalization*: Normalizes backslash/forward-slash paths to prevent platform-specific bypasses of test/conformance rules.
  - *In-memory directory caching*: Caches repository directory walking during architecture compliance checks (`arch-check`) to avoid quadratic filesystem traversals.

### Shell Hooks (`scripts/hooks/`)
Harness-aware pre-tool-use and post-tool-use scripts execute in response to agent actions:
- **build-format** — automatically runs formatting tools on modified source files.
- **build-lint** — triggers single-file linters and feeds advisory, non-blocking feedback directly into the agent's context.
- **build-guard** — blocks critical violations, such as direct commits/pushes to `main`, or RAM tmpfs directories like `/tmp` for Rust cargo targets.
- **build-hooks** — wires test-first `tdd-guard` execution into writing or executing operations.
- **Cross-Platform Portability**:
  - Verified `jq` command availability at bootstrap.
  - Uses highly portable POSIX character-class regular expressions (e.g. `[[:alnum:]_]`, `[[:space:]]`) ensuring seamless execution across GNU (Linux) and BSD (macOS) grep implementations.
  - Integrates a robust multi-field tool-call payload extraction to parse JSON commands for both Claude (`.tool_input.command`) and Antigravity (`.toolCall.args.CommandLine` or `.toolCall.args.command`).
  - Automatically creates `.git/info/exclude` in `project-bootstrap.sh` to local-ignore configuration files invisibly to git diff.

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

## CI/CD Quality Gates
Our `.github/workflows/ci.yml` pipeline enforces 100% compliance across all commits and PRs:
1. **Go Verification**: Runs `go mod tidy` verification (verifying `go.mod` and `go.sum` match), builds all modules (`go build ./...`), and runs analysis (`go vet ./...`).
2. **Go Unit Testing**: Executes all tests under `./...` (including tdd-guard and repository state/lookups checks).
3. **Shell Hook Testing**: Runs `scripts/hooks/tests/test_hooks.sh` to verify hook script correctness and cross-platform compatibility.
4. **Python Skill Testing**: Runs automated unit tests for centralized skills (`planner`, `build`, `code-review`, `docs`, `research`).
5. **Docs Enforcement**: Executes `docs_check.py` to prevent any documentation or ADR regression.

---
Decisions are recorded as ADRs under [`docs/adr/`](docs/adr/).
