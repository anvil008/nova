# Changelog

All notable changes to Workcell will be documented in this file.

## [v0.6.0 — The wiki opts in with one question in-session] - 2026-09-01

Backward-compatible feature, so the bump is a minor.

### Added

- **`/workcell:wiki init` puts the opt-in question in-session.** Invoked directly as
  `/workcell:wiki init`, or whenever `status` answers `present: false` and a human is present to
  ask, the orchestrator asks one yes/no question naming the resolved `projectKey` and the
  namespace path `status` printed, then runs `wiki.py init --repo .` itself only on an explicit
  yes. A non-interactive run, and a "no," still end at `present: false` — no run creates a
  namespace unasked, so ADR 0019's deliberate-opt-in principle is unchanged. `wiki.py` itself is
  untouched.

## [v0.5.0 — Skills consolidate to 16, MCP servers retire, planner becomes `/workcell:plan`] - 2026-09-01

User-facing renames and consolidations, no compatibility kept — this is pre-1.0, so the bump is a
minor, not a patch.

### Changed

- **`planner` the skill is now `plan`** — invocation is `/workcell:plan`. The `planner` agent keeps
  its name; only the skill's invocation changed. Every reference, test, and eval case moved with
  it (`evals/cases/skills/plan.json` replaces `planner.json`).
- **Skills consolidate 18 → 16.** `builder-frontend` becomes `skills/build/references/frontend.md`;
  `reviewer-frontend-review` becomes `skills/code-review/references/frontend-review.md`. Both are
  reference files now, read by the owning skill's agent body, not separately invocable skills.
  `code-review`'s own description now names its frontend lens directly. On Antigravity, only `jj`
  remains a builder-owned skill link; the agy shared-skill sweep was hardened against strays left
  by a renamed skill.
- **MCP servers are fully removed.** The `chrome-devtools` MCP server is retired from every
  harness; the `debugger` now reaches the same diagnostics — network requests/HAR, traces, console,
  script evaluation — through the `agent-browser` CLI, the same tool the `builder` and `reviewer`
  already used. No agent carries an `mcp__` tool on any harness (a new generator test asserts it).
  `register_mcp` in `bootstrap-plugins.sh` is retirement-only now: it removes any `playwright` or
  `chrome-devtools` MCP entry this repository previously wrote, by exact command match, and
  registers nothing new. ADR 0012 was amended accordingly.
- **The plugin marketplace is renamed `workcell-local` → `workcell`.** The plugin reference is now
  `workcell@workcell`. `bootstrap-plugins.sh` retires the old `workcell-local` registration on both
  install and uninstall, so a machine that installed under the old name converges automatically.
- **The planner folio renderer was reworked.** The 3.4MB bundled Mermaid JS is replaced by
  build-time inline SVG (`skills/plan/scripts/diagrams.py`); folios carry the Workcell mark;
  summaries and issue bodies render as real paragraphs instead of raw text blocks; SVGs scale
  responsively; the hints-toggle behavior is documented. `docs/plans/plan07-*` (the wiki-layer
  folio) is archived; `docs/plans/plan08-*` (the APM-migration folio) and its sidecar/issue-state
  are dropped as superseded.
- **The `tdd-guard` rename is complete in Go source.** The 64 remaining `anvil-guard` strings
  (comments and user-facing error text) across `controlplane/` and `guard/` now read `tdd-guard`;
  the wire schema ids (`anvil.guard/v1` and friends) are deliberately unchanged, since those are a
  data contract, not a display string.
- **`skills/wiki/SKILL.md` frontmatter fix** — a stray colon in the YAML description became an
  em dash, so the frontmatter parses.
- **`use-other-harness` gains Grok** as a selectable target harness.
- **README "Start here" is now "Workflows."**
- **The deploy skill's release-title rule**: a GitHub release title is exactly `<project> vX.Y.Z`;
  the descriptive strapline stays in the changelog entry heading, and release notes never repeat
  the title as their own first heading.

### Removed

- **Root `apm.yml` deleted**, per ADR 0020: Workcell's own plugin does not ship through apm, and a
  root manifest is what would incorrectly classify this repository for `apm install`.

## [v0.4.0 — Grok Build joins as a fourth harness; browsers move off Playwright] - 2026-08-31

### Added

- **Grok Build is a fourth harness** alongside Claude Code, Codex, and Antigravity: generated
  `agents/grok/*.md`, `plugins/grok/`, `.grok-plugin/marketplace.json`, and
  `scripts/build-grok-plugin.py`, which stages a real tree into `dist/grok/` because Grok — like
  Codex — drops any symlink pointing outside the plugin root. `bootstrap-plugins.sh` gained a
  `grok_plugin` install path and `--harness grok`. Grok ships no hooks — its hook payload is a
  different dialect the gate scripts would misparse — so the TDD seal/verify/review ceremony
  applies there only as agent-body procedure, never as a mechanically enforced gate; read-only
  Grok agents are scoped with `permission_mode: plan` instead of a narrowed tool list.
  `agents/models.json` gained a `grok` column (`model: inherit`, no verified per-agent effort or
  tool surface).
- **`scripts/bootstrap.sh`: one command for the whole install.** It installs the
  [`apm`](https://github.com/microsoft/apm) CLI when absent, ensures the
  `vercel-labs/agent-browser` package in apm's single global scope, then runs
  `bootstrap-tools.sh --install` and `bootstrap-plugins.sh`. `bootstrap-tools.sh` now also
  checks/installs `apm` and the `agent-browser` CLI. `bootstrap-plugins.sh` gained `register_mcp`,
  which registers the `chrome-devtools` MCP server (`npx -y chrome-devtools-mcp@latest`) at user
  scope in whichever of Claude, Codex, Antigravity, and Grok are installed, through each harness's
  own CLI — apm's MCP entries are project-scoped only. It retires any `playwright` MCP entry it
  previously registered under that exact command and never touches an entry it did not write.
- **ADR 0020** records why APM stays a peer tool rather than Workcell's distribution layer: it
  projects format, not the per-harness content differences Workcell actually has, and its
  marketplace-first format detection would silently decompose this repository if given an
  `apm.yml` at the root.

### Changed

- **Browsers move off Playwright, split by role.** The `builder` and `reviewer` now drive browsers
  through the `agent-browser` CLI via Bash on every harness — zero per-session MCP tool cost. The
  `debugger` alone carries the 11-tool `mcp__chrome-devtools__*` set on Claude (network waterfall,
  `evaluate_script`, console), for the deep diagnostic surface neither of the other roles needs.
  ADR 0012 was amended accordingly, and `skills/reviewer-frontend-review/SKILL.md` was rewritten
  from `browser_*` Playwright tool calls to `agent-browser` commands. Remaining Playwright mentions
  in `agents/bodies/reviewer.md`, `skills/code-review/SKILL.md`, and one missed heading in
  `skills/reviewer-frontend-review/SKILL.md` are corrected in this pass; the four generated
  `reviewer` copies were regenerated with `scripts/sync-agents.py`.

### Deploy notes (post-release, 2026-08-31)

The v0.4.0 deploy to Claude, Codex, and Grok (Antigravity deferred) surfaced operational findings
recorded as ADR 0021 and here, so they don't repeat on the next release:

- **Marketplace paths are load-bearing** (ADR 0021). Claude and Codex resolve the installed plugin
  through the registered marketplace _path_, not a content snapshot; deploying from a temporary
  worktree and then deleting it broke both harnesses (`Status: ✘ failed to load — cache-miss`).
  v0.4.0 currently serves from `/home/anvil/repos/workcell-v0.4.0-plugins`, which must persist
  until the next bootstrap run from the primary repository re-registers the marketplace there.
- **The next bootstrap from the primary repository will hit stale-registration conflicts** —
  Codex refuses a second `workcell` registration from a different source, and Grok ends up with a
  duplicate marketplace entry — so that run must remove the worktree-path registration first
  (`docs/install.md`'s upgrade section carries the one-line note).
- **Grok has no v0.3.0 to roll back to.** It is net-new in v0.4.0; its rollback is
  registration-level (`grok plugin uninstall workcell` plus removing the marketplace entry), not a
  version downgrade.
- **Codex's manifest version (`0.1.0+codex.<buildstamp>`) cannot confirm which release is
  installed** — it tracks Codex build metadata, not this repository's semver. The v0.4.0 deploy
  verified Codex's staged content byte-for-byte instead; a GitHub issue is open to give the
  manifest a version that tracks the release.

## [The wiki layer — persistent per-project knowledge] - 2026-08-31

### Added

- **A persistent knowledge store outside every repository**, at `$WORKCELL_WIKI_HOME`
  (default `~/.workcell/wiki/`), with one namespace per project key. The key is the normalized
  `origin` remote — `git@github.com:anvil008/workcell.git` and `https://github.com/anvil008/workcell`
  collapse to `github-com-anvil008-workcell` — or, with no remote, the toplevel basename plus a hash
  of its absolute path. It resolves through the primary toplevel exactly as `workcell-ws` does, so
  every per-issue workspace of one repository answers with one key, and it obeys the same
  `[a-z0-9][a-z0-9-]*` spelling rule.
- **`skills/wiki/scripts/wiki.py`, the store's only writer** — `key`, `init`, `status`, `record`,
  `pattern`, `check`. Raw bundles are write-once with hashed manifests, pattern pages are
  append-only prose with dated evidence citations, `index.md` is derived from the pages, and
  `logs.md` gains one line per write. Nothing deletes: there is no reset and no rollback. A
  namespace refuses a repository it was not created for, naming both sources, and a repository in
  eval mode is refused outright.
- **The `wiki` skill** — the opt-in rule (no namespace means no dispatch), the single `documenter`
  dispatch whose `ownership` is the namespace path and which writes only through `wiki.py`,
  `wiki.py check` as the completion gate, an offline demonstration over a shipped sample namespace,
  and the two standing boundaries: runtime agents are never given the wiki, and a project pattern
  never amends Workcell's shared `skills/`. The artifact contract is
  `skills/wiki/references/wiki-layout.md`.
- **The `review-fix-loop` consolidates on its way out.** Every ending — `converged`, `stalled`,
  and `exhausted` alike — records each pass's merged review and the loop state as one write-once
  bundle, then dispatches a single `documenter` to consolidate what the passes learned into the
  namespace, gated on `wiki.py check`. The exit step neither changes nor stands in for the loop's
  report, and a project with no namespace ends the loop exactly as it ends today.
- **A `build` hook records each accepted wave as a raw trace.** Once a wave is accepted on its
  evidence, `build` writes the integrator's handoff record and the gate output it accepted on into
  a scratch directory outside the repository and records them as a `build-wave` bundle under
  `raw/`. It records that raw evidence only and never consolidates it. A record that fails or is
  skipped never blocks, gates, or delays the merge, which stays gated on exactly what it was
  before.
- **[ADR-0019](docs/adr/0019-the-wiki-lives-outside-every-repository.md)** records the decision:
  the store outside every repository, the project-key rules, the three durability layers, opt-in
  by a namespace's existence, and why keeping the store outside the repository makes the eval
  ablation structural instead of a guard rule. `README.md` gains the layer, and
  `docs/eval-runs.md` states the eval-mode boundary.

## [Branch and workspace names carry a type prefix] - 2026-08-31

### Added

- **A type-prefixed naming standard for every branch, worktree, and jj workspace** (ADR-0018). A
  key is `<type>/<slug>` — `feature`, `bug`, `doc`, `refactor`, `perf`, `test`, `release`, `chore`,
  `review`, or `integration` — and the key is the bookmark or branch verbatim. Each skill mints one
  type at the point it names a branch, and the planner assigns each issue `type:feature` or
  `type:bug` so `build` can branch it. `docs/workspaces.md` carries the table.

### Changed

- **`workcell-ws` accepts one slash in a key.** The bookmark and git branch keep it; the sibling
  directory and the jj workspace name write it as a dash, so `feature/xyz` is bookmark
  `feature/xyz`, jj workspace `feature-xyz`, and directory `../<repo>-feature-xyz`. `list`,
  `forget`, and `sweep` recover the key from the local refs, so a slashed key round-trips and is
  classified — `merged`, `stale-dir`, `stale-reg` — under the key it was created with. A key with
  no slash behaves exactly as it did before, spelling included.

## [v0.3.0 — Deploy publishes GitHub releases and packages] - 2026-08-31

### Added

- **The deploy skill's orchestrator publishes the GitHub release for the tag it creates**, running
  `gh release create` from the notes the `documenter` prepares, instead of leaving the tag
  unaccompanied by a release.
- **The `deployer` publishes release packages** (GitHub Packages, npm, container registries) under
  the approved version as part of the human-gated deploy step, and records every artifact —
  name, version, digest or URL — in its handoff record. The boundary is explicit: tag and GitHub
  release belong to the orchestrator; package artifacts belong to the `deployer`.
- **Release notes have a pinned shape**: a short summary of what the release delivers, the
  changelog entries for that version, and any breaking-change or upgrade callouts.

## [The build wave loop overlaps where the seal allows] - 2026-08-30

### Changed

- **Dispatch is dependency-gated, not wave-gated** (ADR-0017). A not-done issue whose `dependsOn`
  are all done is dispatchable the moment they land, whatever wave it was planned into, so a long
  wave no longer holds back work that is already unblocked. `wave` demotes from a scheduling
  barrier to a planning hint and the anchor wave reports are grouped under.
- **Ownership overlap defers instead of failing.** A candidate whose `ownershipHint` overlaps
  anything in the in-flight set waits for that work to land rather than being dispatched beside it.
  An overlap _declared_ inside one wave is still a plan defect and is still rejected — deferral
  covers the pull-forward the scheduler does, not a plan that asked two builders to write the same
  files.
- **The `documenter` runs alongside the `integrator`.** It is dispatched at the same time, from the
  wave's pull requests, instead of after the merge, and its output is retested inside the same
  combined GREEN; documentation now merges with the code it describes rather than trailing it.
  This landed in `skills/new-feature/SKILL.md`; `skills/build/SKILL.md` dispatches no `documenter`
  and has no documentation step of its own yet, so a milestone driven straight from `build` still
  takes its documentation from a separately invoked `docs` pass.
- **Speculative `specifier` dispatches are permitted.** While a wave is in flight the orchestrator
  may seal tests for issues whose dependencies have not landed yet, so the seal is ready when they
  do. Speculative _builders_ are not permitted: a builder still starts only against a seal taken on
  a base its dependencies have merged into.
- **`ownershipHint` is exactly one narrow glob.** An issue that would need two disjoint areas is
  split into two issues instead of taking a wider hint, because a coarse hint serializes everything
  it touches under the deferral rule.
- **`README.md` and the how-work-moves diagram** were regenerated to match: the pull request fans
  out to the `integrator` and the `documenter`, and the single gate covering both is what the
  orchestrator merges on.

## [Agent names settle on plain CS terms] - 2026-08-30

### Changed

- **Three more agents renamed** (ADR-0016, superseding ADR-0015 for these three):
  `oracle` → `specifier`, `benchmarker` → `profiler`, `scribe` → `documenter`. `builder`,
  `debugger`, `deployer`, `integrator`, `planner`, `researcher`, and `reviewer` are unchanged, and
  the **skills** keep their names — `docs` dispatches the `documenter`, `perf` the `profiler`, and
  `build` Phase 1 the `specifier`. Bodies, `agents.json`, `models.json`, the Codex gate snippet
  (`codex-oracle` → `codex-specifier`), every generated per-harness definition, the agent-owned
  `agy` skill symlinks, the skills, eval cases and routing owners, the tests that pin those names,
  the guard's comments, the README, `docs/gates.md`, and the README diagram sources all move
  together. Accepted ADRs 0001–0015, `docs/plans/`, `docs/research/`, `plan.sidecar.json`, and
  earlier entries in this file keep the old names as historical record.
- **The acceptance-test `oracle` field keeps its name.** It is the observable pass condition a
  planner writes and a `specifier` turns into an assertion, and it is unchanged in
  `plan.sidecar.json`, the sidecar contract, `agents/handoff.md`, and the rendered issue checklist.
  Naming the agent after that field is what forced ADR 0015's "the `oracle` agent" phrasing; with
  the collision gone, those sentences read plainly again. Routing rank-1 holds at 79.0% against the
  77% floor.

## [Agents are named for the worker] - 2026-08-30

### Changed

- **Five agents renamed** (ADR-0015): `test-author` → `oracle`, `code-reviewer` → `reviewer`,
  `research` → `researcher`, `docs` → `scribe`, `deploy` → `deployer`. `planner`, `builder`,
  `debugger`, `benchmarker`, and `integrator` are unchanged. The **skills** `research`, `docs`,
  `deploy`, and `code-review` keep their names — a skill is a workflow, an agent is the worker it
  dispatches — and each now dispatches the renamed agent by its new id. The skill
  `code-reviewer-frontend-review` becomes `reviewer-frontend-review`, after the agent that owns it.
  Bodies, `agents.json`, `models.json`, the Codex gate snippet, every generated per-harness
  definition, the skills, eval cases and routing owners, the tests that pin those names, the README,
  `docs/gates.md`, and the README diagram sources all move together. Accepted ADRs 0001–0014,
  `docs/plans/`, `docs/research/`, and `plan.sidecar.json` keep the old names as historical record.
- **`build` and `research` skill descriptions** were reworded around the new agent names, holding
  the routing rank-1 rate at 79.0% against the 77% floor.
- **`repo-setup` and the `scribe` body: one instruction file.** `AGENTS.md` is the single real
  instruction file and `CLAUDE.md` / `GEMINI.md` are symlinks to it (`ln -sf AGENTS.md CLAUDE.md`),
  so there is one source of truth instead of copies that drift. A repository with a divergent
  `CLAUDE.md` has both merged into `AGENTS.md`, shown to the human, before the link replaces it.
  `docs_check.py` now counts a linked instruction file once, under the real path.

### Removed

- **README "How it compares".** The addyosmani/agent-skills comparison table is gone; the README
  describes this repository rather than ranking it against another.

## [One workspace helper across harnesses] - 2026-08-30

### Added

- **`scripts/workcell-ws`:** One shell helper owning agent isolation on all three harnesses —
  `add` / `forget` / `list` / `sweep`. A jj repository gets a jj workspace, a git-only repository a
  git worktree, both at the sibling path `../<repo>-<key>` with the bookmark or branch `<key>`.
  `sweep` names every stranded workspace and every merged local ref and is read-only until
  `--apply` (ADR-0014). It refuses rather than guessing: an independent repository that collides on
  the naming convention is `foreign` and never removed, a dirty git worktree is refused by name
  until it is committed or `--force` is passed, a jj workspace is snapshotted into its commit
  before its directory goes, and a workspace the calling shell is standing in is refused outright. `bootstrap-tools.sh --install` links it onto `PATH` beside the `build-*`
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
