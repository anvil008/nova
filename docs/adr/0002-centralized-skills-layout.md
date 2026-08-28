# 2. Centralized skills layout

## Status
Accepted

## Context
In our previous architecture (detailed in ADR 1), skills were conceptually associated with specific agents. However, as the ecosystem expanded to support multiple execution harnesses (Claude, Codex, and Antigravity) across different developer environments, keeping skill definitions scattered or tightly coupled to individual agents led to duplication, inconsistent behaviors, and testing friction. We need a unified structure to define, maintain, and test skills, while still enabling each harness to selectively discover and load them.

## Decision
We establish a centralized `skills/` directory at the project root containing all shared agent skills (e.g., `planner`, `research`, `build`, `code-review`, `docs`, `deploy`, `use-other-harness`, `builder-frontend`, `code-reviewer-frontend-review`).

These centralized skills are projected into each respective harness directory structure via `scripts/install-harness.sh`. The installer handles each harness as follows:

1. **Claude**:
   - Symlinks agent markdown files from `agents/claude/<agent>.md` into `~/.claude/agents/<agent>.md`.
   - Symlinks centralized skill directories from `skills/<skill>` into `~/.claude/skills/<skill>`.
2. **Codex**:
   - Parses the frontmatter and body of agent files in `agents/codex/<agent>.md` and projects them into `~/.codex/<agent>.config.toml`.
   - Symlinks centralized skill directories from `skills/<skill>` into `~/.codex/skills/<skill>`.
   - Injects corresponding agent blocks into `~/.codex/config.toml`.
3. **Antigravity**:
   - Copies agent files from `agents/agy/<agent>/` (both `agent.md` and `hooks.json`) into `~/.gemini/config/agents/<agent>/`.
   - Symlinks centralized skill directories from `skills/<skill>` into `~/.gemini/config/skills/<skill>` (and `~/.agents/skills/<skill>` if it exists).

This approach ensures a single source of truth for all skill logic and configurations.

## Consequences
- **DRY (Don't Repeat Yourself)**: Skills are authored once in `skills/` and shared across all platforms, preventing divergence in behavior.
- **Improved Testability**: We can easily discover and run automated tests directly against the centralized `skills/` directories in CI.
- **Explicit Harness Symlinking**: Development environments must execute `scripts/install-harness.sh` to project skills into the corresponding harness directories. Symlinking requires the host environment to support symlinks.
- **Decoupled Evolution**: Adding or refining a skill can be done purely in the centralized `skills/` directory without altering harness-specific configurations directly.
