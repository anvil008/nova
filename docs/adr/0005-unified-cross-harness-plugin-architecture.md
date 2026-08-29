# 5. Unified Cross-Harness Plugin Architecture

## Status

Accepted

## Context

Previously, Swarm Coder installed its agents and skills directly into harness-specific directories (e.g., `~/.claude/agents` or `~/.codex/skills`). As we support more harnesses like Antigravity, and as the number of agents and skills grows, managing these components directly in the global namespace of each harness leads to clutter and potential naming collisions.

Furthermore, workspaces needed a way to provide local, repo-specific tooling without polluting the global environment. A unified structure is necessary to encapsulate all components under a single plugin identity.

## Decision

We introduce a unified cross-harness plugin architecture. All agents, skills, and configuration rules are packaged inside harness-specific wrappers under the `plugins/` directory:
- `plugins/agy/swarm-coder`
- `plugins/claude/swarm-coder`
- `plugins/codex/swarm-coder`

The global installation command (`scripts/install-harness.sh --install`) links these plugin wrappers into their respective harness plugin directories (e.g., `~/.claude/plugins/swarm-coder`). 
The workspace local setup (`scripts/project-bootstrap.sh --install`) links them directly into `.agents/plugins`, `.claude/plugins`, and `.codex/plugins` within a given project repository, automatically ignoring them from Git.

## Consequences

- **Cleaner Global Namespace:** Agents and skills are grouped under the `swarm-coder` plugin, preventing clutter in the harness root directories.
- **Project-Local Tooling:** It becomes trivial to install Swarm Coder per project, ensuring the project workspace has the exact agents and hooks needed without relying on a global install.
- **Migration Required:** Existing users must run the uninstall command to remove legacy direct links before installing the new plugin-based layout.
