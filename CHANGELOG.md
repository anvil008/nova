# Changelog

All notable changes to Workcell will be documented in this file.

## [One workspace helper across harnesses] - 2026-08-30

### Added

- **`scripts/workcell-ws`:** One shell helper owning agent isolation on all three harnesses —
  `add` / `forget` / `list` / `sweep`. A jj repository gets a jj workspace, a git-only repository a
  git worktree, both at the sibling path `../<repo>-<key>` with the bookmark or branch `<key>`.
  `sweep` names every stranded workspace and every merged local ref and is read-only until
  `--apply` (ADR-0014). `bootstrap-tools.sh --install` links it onto `PATH` beside the `build-*`
  hooks; `scripts/tests/test_workcell_ws.sh` covers both version-control systems.
- **`docs/workspaces.md`:** The isolation standard — naming, base, teardown after the PR exists,
  and the sweep as the leak check.

### Changed

- **`test-author` / `builder` bodies, `build`, `code-refactor`, `repo-setup`.** They now name
  `workcell-ws` where they used to spell out `jj workspace add` / `forget`, keeping the raw jj
  commands as the shown equivalent. Git-only repositories gain isolation parity, so jj adoption is
  an optimisation for parallel waves rather than a prerequisite.

## [README diagrams are generated SVG] - 2026-08-30

### Added

- **`scripts/render-diagrams.py`:** A stdlib-only layered renderer that turns
  `docs/diagrams/src/*.json` into a light and a dark SVG per diagram, deterministically.
  `--check` fails and names any file that differs from a fresh render; CI runs it as
  `Diagrams in sync` (ADR-0010).

### Changed

- **README "How it works".** Both Mermaid fences are now theme-aware `<picture>` elements over
  generated SVG — one for how work moves from a goal to a merge, one for the mechanical gates —
  each still paired with its "In words" text equivalent (ADR-0004).
- **Docs README contract.** The `docs` agent body now prefers a generated theme-aware SVG for the
  README, GitHub-rendered Mermaid elsewhere, and a durable text diagram when either adds
  complexity. `docs/gates.md` keeps its Mermaid.

## [Skill instruction review — contracts, disclosure, evals] - 2026-08-30

### Added

- **Dispatch contracts (#85):** Made orchestration skills explicit dispatch-and-gate contracts,
  including single-PR integration and green baseline seals for behavior-preserving work.
- **Agent contracts (#86):** Added the canonical dispatch/handoff schema, specialist modes, and
  command-linked evidence requirements across every agent body.
- **Instruction evals (#87):** Added structural, TF-IDF routing, collision, and on-demand
  executor/grader behavioral tiers for all 17 skills and 10 agents, with free tiers wired into CI.

### Changed

- **Repository guidance:** Synchronized the workflow, agent ownership table, mechanical gates,
  verification commands, and milestone history with the reviewed contracts.

## [Plugins install through local marketplaces] - 2026-08-29

### Fixed

- **Claude Code and Codex now actually load the plugin.** Both discover plugins through a
  registry, never by scanning their plugin directory, so the symlink the installer wrote
  into `~/.claude/plugins/workcell` was inert: `claude plugin list` did not show it and
  none of its agents, skills, or hooks reached a session. Both harnesses now install
  through a local marketplace using their own CLI (ADR-0006).
- **Claude plugin hooks.** `plugins/claude/hooks.json` was a copy of the Codex file: Codex
  tool names (`run_command`, `write_to_file`) inside a `workcell-guard` module wrapper, which
  Claude Code parsed as zero hooks. Rewritten in Claude's schema at
  `plugins/claude/hooks/hooks.json`, matching `Bash` and `Edit|Write|NotebookEdit`.
- **Restored files deleted from the working copy.** `agents/agy/builder/agent.md`,
  `agents/agy/builder/hooks.json`, `plugins/agy/plugin.json`, and
  `skills/builder-frontend/SKILL.md` were missing, leaving the Antigravity plugin without
  a manifest or a builder agent.

### Changed

- **Flatter layout.** Wrappers moved from `plugins/<harness>/workcell` to
  `plugins/<harness>`, and `plugins/codex-marketplace/` is gone — both marketplace
  manifests now live at the repository root (`.claude-plugin/marketplace.json` and
  `.agents/plugins/marketplace.json`), which is also what keeps each wrapper's `agents/`
  and `skills/` symlinks inside the marketplace root.
- **Two bootstrap commands, symmetrically named.** `install-harness.sh` is now
  `bootstrap-plugins.sh` and `project-bootstrap.sh` is now `bootstrap-project.sh`, joining
  `bootstrap-tools.sh`: one command for the external tools, one for the plugin, one for a
  single project.
- **Antigravity skill links are derived.** `bootstrap-plugins.sh` regenerates
  `plugins/agy/skills/` from `skills/` minus the skills owned by an agent, so adding a
  skill no longer means editing the installer.
- **Ownership refusal now covers Antigravity only**, the one harness this repository still
  writes a symlink for. Claude and Codex targets belong to their own CLIs.

## [Human-friendly visual skill outputs] - 2026-08-29

### Added

- **Accessible visual contract**: Recorded ADR-0004, requiring meaningful visuals to
  have concise nearby text equivalents and generated views to share authoritative data.
- **Planner change story**: Planner folios now compare current and proposed states and
  explain the architectural delta in text.
- **Review topology**: Code-review reports now show how review lenses and raw candidates
  become verified findings and affected files, including zero-finding outcomes.

### Changed

- **Newcomer documentation**: The docs skill and all docs-agent definitions now require
  a concise what/why/quickstart README shape with an accessible workflow or architecture
  visual when relationships matter.
- **Repository README**: Reorganized the root guide around a short installation path,
  a visual-plus-text workflow explanation, core guarantees, and executable verification.

## [Harness Gate Integrity and Cross-Harness Parity] - 2026-08-28

### Added

- **Gate-integrity milestone**: Added argv-bound RED-to-GREEN evidence, tamper-resistant sealed-test checks, physical-path target resolution, authenticated guard records, full-stream untracked-file digests, concurrent touch-log protection, and control-plane contract validation.
- **Build boundary corpus**: Added fail-closed hook parsing and adversarial command tests covering protected Git/jj/GitHub operations, shell wrappers, quoting, and tmpfs targets.
- **Research assurance**: Added stance-driven conflict detection that separates corroboration from genuine contradictions in merged research.

### Changed

- **Cross-harness parity**: Removed dangling skill references, aligned agent capabilities and model tiers, wired the Antigravity Stop gate, and documented Codex's explicit manual gates.
- **Install and CI hardening**: Made installs symlink-only, ownership-checked, Bash-3.2-portable, and fail-fast; CI now discovers every skill test suite and enforces Ruff, ShellCheck, Go race tests, installer tests, and docs checks.
- **Build and review orchestration**: Corrected recursive ownership-glob overlap detection, normalized planner/review finding identities, and made the review-fix loop severity threshold part of convergence.

## [Report System and Harness Reset] - 2026-08-28

- Commit `a1f4584`: introduced shared HTML report styling, planner folios under `docs/plans/`, code-review reports and finding reconciliation, isolated jj builder workspaces, the frontend review lens, and the repository-as-single-source harness installer.
- Commit `ee46c1a`: introduced the bounded `review-fix-loop` with durable converged, stalled, and exhausted states on a dedicated loop branch.

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
