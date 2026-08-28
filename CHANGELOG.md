# Changelog

All notable changes to Swarm Coder will be documented in this file.

## [Hardening Release] - 2026-08-27

This release focuses on hardening the Go-based guard mechanical gates, improving the portability of shell hooks across GNU/Linux and BSD/macOS environments, enhancing Python skill orchestration, ensuring complete agent parity across Claude, Codex, and Antigravity, and introducing comprehensive CI/CD quality gates.

### Added
- **Centralized Skills Layout**: Centralized skill structure (`skills/`) at the repository root, projected dynamically into Claude, Codex, and Antigravity harnesses via `scripts/install-harness.sh` (documented in ADR-0002).
- **CI/CD Quality Gates**: Automated GitHub Actions workflow (`.github/workflows/ci.yml`) performing Go building, testing, vetting, hook testing (`test_hooks.sh`), Python skill unittest discoveries, and mechanical docs checks (`docs_check.py`) on push and PR.
- **Wave Ownership Overlap Detection**: Programmatic check (`waves.py`) to detect and reject overlapping `ownershipHint` globs for parallel issues within the same wave to prevent concurrent builder worktree collisions.
- **Bootstrapping Enhancements**: Auto-creation of `.git/info/exclude` in `project-bootstrap.sh` to local-ignore configuration files invisibly to `git diff`.

### Changed
- **Go Guard Mechanical Gates Hardening**:
  - Implemented streaming SHA-256 digests bounded by a strict 10MB limit (`maxBytes` limit reader) in the policy engine and untracked file check to eliminate unbounded memory consumption during diff digesting.
  - Added cross-platform path normalization for backslash-separated (Windows) paths in test-driven development checks.
  - Introduced in-memory directory caching in `arch-check` (`matchGlobCached` / `repositoryFilesWalk`) to avoid quadratic filesystem walking.
- **Cross-Platform Hook Portability**:
  - Updated hook scripts (`scripts/hooks/`) to use POSIX character-class regexes (e.g. `[[:alnum:]_]`, `[[:space:]]`) supported natively by both GNU grep and BSD grep (macOS).
  - Wired explicit `jq` dependency verification inside tool bootstrappers.
  - Expanded JSON parsing to use robust multi-field tool-call payload extraction to handle both Claude (`.tool_input.command`) and Antigravity (`.toolCall.args.CommandLine` or `.toolCall.args.command`) payloads.
- **Orchestration Skills Enhancements**:
  - Added default 30-second subprocess timeouts to GitHub reconciler API requests in `reconcile_github.py` and raise explicit `ReconcileError` on timeout.
  - Aligned all skill markdown files (`skills/**/SKILL.md`) to utilize explicit, unified repository-relative script execution paths.
- **Agent Parity**:
  - Ported missing developer instruction guidelines and skills sections across Claude, Codex, and Antigravity agent definitions.
  - Wired format (`build-format agy`), advisory lint (`build-lint agy`), `build-guard agy`, and `build-hooks agy PreToolUse` / `PostToolUse` hooks natively into the Antigravity builder's `hooks.json` file.
