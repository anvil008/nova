# 6. Plugins Install Through Local Marketplaces

## Status

Accepted. Supersedes the install mechanism in [ADR 0005](0005-unified-cross-harness-plugin-architecture.md).

## Context

ADR 0005 installed every harness wrapper the same way: a symlink from the harness's
plugin directory back into `plugins/<harness>/workcell`. That works for Antigravity,
which reads its plugin directory straight off disk. It does not work for Claude Code or
Codex. Both discover plugins through a registry — `installed_plugins.json`,
`known_marketplaces.json`, and `enabledPlugins` for Claude; `codex plugin list` for
Codex — and neither ever scans its plugin directory for unregistered entries. A wrapper
symlinked into `~/.claude/plugins/workcell` was therefore inert: `claude plugin list`
did not show it, and none of its agents, skills, or hooks ever loaded.

The layout had also accumulated avoidable depth. Each wrapper sat at
`plugins/<harness>/workcell`, a directory whose only child was the wrapper, and Codex
needed a fourth top-level directory, `plugins/codex-marketplace/`, holding nothing but a
manifest and a symlink back to the wrapper it described.

## Decision

Claude and Codex install through a local marketplace instead of a symlink. Both
marketplace manifests live at the repository root — `.claude-plugin/marketplace.json`
and `.agents/plugins/marketplace.json` — and both are registered and installed by the
harness's own CLI:

```
<cli> plugin marketplace add <repo>
<cli> plugin install workcell@workcell
```

The root is the marketplace root deliberately. Each wrapper reaches the single source
through symlinks (`agents -> ../../agents/<harness>`, `skills -> ../../skills`), and an
install drops any symlink that escapes the marketplace root. Rooting the marketplace at
the repository is what keeps those targets inside it.

Antigravity keeps the ADR 0005 symlink. Although `agy plugin` provides plugin-management commands,
its install paths are not a stable documented contract for this bootstrap flow; the explicit links
use the known locations and remain live as the source tree changes.

The wrapper directories lose a level — `plugins/<harness>` rather than
`plugins/<harness>/workcell` — and `plugins/codex-marketplace/` is deleted. The
plugin's name comes from its manifest, not from its directory name.

The three entry points are renamed to one symmetric set: `scripts/bootstrap-tools.sh`
(external dependencies), `scripts/bootstrap-plugins.sh` (the plugin, formerly
`install-harness.sh`), and `scripts/bootstrap-project.sh` (one project, formerly
`project-bootstrap.sh`).

## Consequences

- **Claude and Codex actually load the plugin.** Both CLIs now list it, and its agents,
  skills, and hooks reach a session.
- **Claude and Codex install a copy.** Edits to `agents/`, `skills/`, or a wrapper's
  `hooks.json` reach them on the next `scripts/bootstrap-plugins.sh` run, not
  immediately. The Antigravity links remain live. The Codex CLI happens to reference the
  wrapper in place today, but that is its choice, not a guarantee this repository makes.
- **Ownership refusal narrows to Antigravity.** It is the only harness this repository
  still writes a symlink for, so it is the only one where a foreign target can be
  refused. Claude and Codex targets are owned by their own CLIs.
- **Antigravity skill links are derived, not listed.** `bootstrap-plugins.sh` regenerates
  `plugins/agy/skills/` from `skills/` minus the skills owned by an agent under
  `agents/agy/<agent>/skills/` (ADR 0003), so adding a skill never means editing the
  installer.
