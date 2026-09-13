# 32. Native Claude workspace hooks and instruction-driven Codex/Agy placement

## Status

Accepted.

## Context

Nova uses `<primary-checkout>/.workspaces/<task>/` for JJ workspaces and Git worktrees. Project instructions can guide agent shell commands but do not configure an app's internal worktree creator. Claude exposes dedicated creation/removal events; equivalent events are not documented for Codex or Agy.

## Decision

Package WorktreeCreate and WorktreeRemove hooks only for Claude. Resolve the primary checkout, prefer JJ when its metadata is present, and create under `.workspaces/` from identified trunk refs. Retain all JJ workspaces and Git worktrees containing modified, untracked, or ignored files during native cleanup. Use project AGENTS.md and shared instructions for Codex and Agy.

Document the complete behavior and other harness differences in [the harness comparison](../../instructions/harnesses.md). Do not claim control over desktop-managed worktrees or intercept arbitrary shell commands.

## Consequences

Claude native isolation follows the placement convention through executable code. Its replacement hook does not fetch, honor Claude's baseRef setting, or copy `.worktreeinclude` files. JJ cleanup remains explicit. Codex/Agy compliance remains instruction-driven. Native plugin trust and session reloads still govern activation.
