# 35. Self-improvement skills and in-repository stores

## Status

Accepted; supersedes ADR 0019.

## Context

ADR 0019 placed the wiki outside every repository in `~/.nova/wiki/<project-key>/` to prevent task-scoped agents from leaking historical notes into pull requests or eval scoring passes. While that prevented untracked artifact pollution in naive setups, operational experience exposed several severe failure modes:

1. **Remote normalization fragility**: Determining project identity from remote URLs (`git remote get-url origin`) proved fragile across HTTPS, SSH, credential-bearing URLs, and mirrors. Different workspaces of the same repository frequently computed different project keys or failed when remotes were unset.
2. **Failure modes of remote mismatches**: When local clones lacked remotes or used different remote aliases, knowledge was siloed across multiple disparate namespaces or silently dropped.
3. **Open-loop accumulation without skill derivation**: The external wiki was an open loop. Agents recorded traces and appended pattern notes, but no mechanism existed to convert recurring project lessons into concrete operational rules or specialized skills. The stored observations remained passive hypotheses that were rarely read or acted upon.
4. **Semantic confusion**: The "wiki" nomenclature implied a user-facing documentation portal or knowledge base rather than an active agent self-improvement (SI) feedback loop.

## Decision

We replace the external wiki with an in-repository self-improvement architecture composed of two specialized skills: `si-project` and `si-global`.

### 1. In-repository store at `<primary-root>/.nova/si/`

The primary store for a project lives directly inside the repository at `<primary-root>/.nova/si/`. The `.nova/` directory is gitignored and excluded from version-controlled deliverables and pull requests, preserving cleanliness for eval suites and branch diffs.

Primary root resolution ensures that secondary Jujutsu workspaces (`.jj/repo` pointer files) and Git worktrees (`git worktree list --porcelain`) resolve to the single primary repository root, sharing a consistent `.nova/si/` store across all concurrent workspaces.

### 2. Store layout contract

The `<primary-root>/.nova/si/` directory maintains an immutable, append-only structure:
- `raw/<id>/`: Write-once bundles containing `manifest.json` (recording trace ID, kind, summary, timestamp, optional model/effort attribution, and file checksums) and captured evidence files.
- `patterns/<slug>.md`: Append-only pattern files documenting recurring failure modes, flaky runners, or project conventions, linking back to raw trace citations.
- `proposals/<id>.json`: Structured candidate proposals for project rule changes or local skills synthesized from pattern evidence.
- `index.md`: Catalog table summarizing known patterns, occurrence counts, and last-seen timestamps.
- `logs.md`: Append-only ledger of store mutations.
- `skill-impact.md`: Audit trail tracking proposed and applied skill changes.
- `project.json`: Metadata linking the store to the resolved primary repository root.

### 3. Closed-loop project adaptation (`si-project`)

The `si-project` skill operates within a repository:
- Checks project opt-in via `si.py status --repo <path>`.
- Initializes the in-repo store via `si.py init --repo <path>`, automatically registering the project in the global registry.
- Captures task traces via `si.py record` and distills recurring lessons into `si.py pattern`.
- Analyzes patterns and synthesizes candidate project rules (e.g. additions to `AGENTS.md`) or project-local skills (`.nova/skills/<name>/SKILL.md`) using `si.py propose`.
- Applies approved proposals (`si.py propose --apply`) only after interactive human-in-the-loop confirmation.

### 4. Cross-project pattern synthesis (`si-global`)

To enable core skill evolution across projects:
- Local projects initialized with `si-project` register their primary root in `~/.nova/known_projects.json` (configurable via `NOVA_PROJECTS_REGISTRY`).
- The `si-global` skill inspects registered projects, clusters recurring systemic issues across repositories (patterns observed across >= 2 distinct projects), and formulates candidate updates to Nova's shared skills (`skills/*`).
- Any updates to shared global skills are strictly gated by Nova's CI verification (`python3 -m unittest discover -s tests`, `python3 scripts/update-guide.py --check`, `python3 scripts/package.py`) before publication.
  - Amendment: this gate originally named `evals/run_evals.py`, which was removed with the `evals/` directory; the gate now names the checks CI actually runs.

## Consequences

- ADR 0019 is superseded.
- Local repository knowledge stays colocated with the repository code under `.nova/si/`, eliminating remote URL normalization errors and remote mismatch failures.
- Multiple workspaces and worktrees of the same repository cleanly share one `.nova/si/` store through robust primary root resolution.
- The feedback loop is closed: raw evidence leads to pattern synthesis, which leads to proposed rules or skills, applied with human oversight.
- Core skill evolution is evidence-based and gated by evaluations.
