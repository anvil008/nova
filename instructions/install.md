# Build and install Nova

Nova ships as one native plugin per harness, built from shared sources. Python 3.11+ is needed for packaging and bundled scripts. Installing the plugin does not install jj, linters, or project dependencies.

## Bootstrap from a checkout

Run the bootstrap script to build and install into every supported harness found on PATH:

```sh
./scripts/bootstrap.sh
```

Select one or more harnesses, preview the actions, or include optional Codex helpers:

```sh
./scripts/bootstrap.sh --harness codex --dry-run
./scripts/bootstrap.sh --harness codex --with-codex-helpers
./scripts/bootstrap.sh --harness claude --harness agy
./scripts/bootstrap.sh --harness all
```

Requires Python 3.11+ and the selected native CLIs. `all` requires all three; without a selection, only available CLIs are used. The script does not download prerequisites or run model sessions.

Bundles are stored under `~/.local/share/nova/plugins/`, so installed packages and marketplace sources survive moving or deleting the checkout. Use `--prefix /absolute/path` to choose another stable location. Rerun bootstrap after pulling source changes to update native installations. A content-derived local version makes changed bundles visible to native caches even before the release version changes. This is a development install; the ordinary package builder retains VERSION unchanged for release bundles.

If an existing marketplace named `nova` points elsewhere, bootstrap stops before installation. `--replace-marketplace` explicitly switches that named source to this build. Other marketplaces are preserved. Do not run concurrent bootstraps into the same prefix.

`--with-codex-helpers` copies the optional definitions to the native Codex agents directory. It refuses conflicting files and symlinks. A receipt tracks bootstrap-owned copies so reruns update unchanged copies while preserving user edits. Claude and Agy helpers already travel inside their plugins.

Bootstrap also installs the self-contained `nova-flow` executable into `~/.local/bin/` (override with `--bin-dir`). Add that directory to PATH if needed. Receipt ownership checks preserve conflicting local files or edits. The tool also remains available inside every plugin under `tools/nova-flow`.

Bootstrap installs capabilities. Run repo-setup afterward to reconcile persistent project instructions and configure project-specific checks. Automatic Nova Flow lifecycle and usage tracking is disabled in all packaged harnesses. Rebuilding or reinstalling from this source does not enable it. The standalone tool remains available for explicit use. Bulk-read routing hooks are enabled in new bundles; they direct large reads to the existing scout. Codex needs `--with-codex-helpers` for native scout setup. See [routing and fallback](read-routing.md). Formatter/linter hooks remain inactive without explicit configuration. Native trust settings still apply. Start a new harness session after installation.

If a native command fails, bootstrap returns nonzero and preserves installations that already completed. Resolve the reported issue and rerun. Dry-run performs no writes and runs no native commands; existing registry conflicts are checked during execution.

## Build

From the repository root:

```sh
python3 scripts/package.py
```

This creates three self-contained marketplace directories in `dist/plugins/`. Copy a complete harness directory to a stable location before registering it if this checkout or `dist/` will be deleted. Rebuilds replace only directories marked as Nova build outputs. Build and installation are separate operations.

## Codex

```sh
codex plugin marketplace add /absolute/path/to/dist/plugins/codex
codex plugin add nova@nova
```

Use a new conversation and select the Nova skill from the catalog (for example `$nova:refactor`). Use `codex plugin list` to inspect availability. For updates, rebuild the bundle, use the installed CLI's marketplace upgrade command, and reinstall the plugin if its cached revision has not changed. Inspect `--help` for the installed version.

The plugin packages all skills and default-location post-edit hooks. Codex plugin helper discovery is not assumed: optional TOML helper definitions are shipped in `setup/agents/`. During an explicitly requested helper setup, copy the selected definitions into the target project's `.codex/agents/` or the user's `~/.codex/agents/`, resolving name conflicts first. Those copies must be updated separately when helper definitions change.

## Claude Code

```sh
claude plugin marketplace add /absolute/path/to/dist/plugins/claude
claude plugin install nova@nova
```

Start a new session. Invoke `/nova:refactor`, or another Nova skill. Helpers are in native `agents/`; hooks are in `hooks/hooks.json`. Inspect `claude plugin details nova@nova` for discovery. Update with the native marketplace/plugin update commands after rebuilding.

## Antigravity CLI

```sh
agy plugin install /absolute/path/to/dist/plugins/agy/plugins/nova
```

Inspect `agy plugin list` and `agy agents`; restart the session for changes. The CLI bundle includes skills, native agent definitions, and rules. Use its displayed skill names. For updates, use the installed CLI's supported install/update flow; consult `agy plugin help` first. Antigravity IDE uses different plugin locations and is not covered by the CLI installation trial.

Agy's hook example is shipped under `hooks/agy.example.json`, not activated automatically. When configuring hooks, resolve the installed plugin directory, replace its runner/config placeholders with shell-quoted absolute paths, and merge the native event definition into the supported hook configuration. Enable the configured event only after testing its command. Do not assume plugin-path environment variables are portable across harnesses.

## Workspace isolation

Claude bundles register native WorktreeCreate/WorktreeRemove hooks. Codex and Agy use project AGENTS.md and the shared placement instructions. See [harness comparison](harnesses.md) for base selection, cleanup retention, ignored-file handling, app settings, and the other configured differences.

## Project instructions and checks

Every skill explicitly reads the bundled `instructions/development.md`. That makes the conventions available during Nova tasks without assuming plugin-root instruction files are automatically loaded.

For persistent project guidance, run Nova's repo-setup skill. It reconciles the conventions with existing project instructions and records actual build/test commands. Use `AGENTS.md` for Codex, `CLAUDE.md` or its supported imports for Claude, and the project's supported rules/instruction mechanism for Agy. A plugin-root `CLAUDE.md` is not project context. Personal configuration and command permissions are not overwritten.

The post-edit runner does nothing unless given an explicit config. Copy `hooks/project.example.json` to a chosen project configuration path, set the absolute repository root and actual argv-based commands, then enable it. Codex and Claude hooks read the absolute config path from `NOVA_HOOK_CONFIG`, set in the harness process environment. Agy's configured command can pass `--config` directly. No repository config is auto-discovered or executed merely by opening a repository.

Hook scripts are advisory. Codex/Claude receive diagnostic context; Agy writes diagnostics to logs. Tests and review remain separate workflow checks. Native hook trust/enablement settings still apply.

## Validate before updating a personal installation

```sh
python3 -m unittest discover -s tests -v
python3 scripts/package.py
claude plugin validate dist/plugins/claude/plugins/nova
agy plugin validate dist/plugins/agy/plugins/nova
```

Use isolated native configuration directories for installation trials. Structural validation and component discovery do not establish model execution, behavior compliance, or token savings. Current trial evidence is in the source repository at `docs/reports/build01-20260907-native-plugin-migration.md`.

For a repeatable Linux offline install trial, run `python3 scripts/native-smoke.py --output /tmp/nova-native-evidence` from the source checkout after building. This requires bubblewrap and all three native CLIs. It mounts temporary configuration directories over the normal paths, keeps the rest of the filesystem read-only, and disables networking. It does not execute a model. Add `--bootstrap` to exercise the bootstrap entrypoint twice, including optional Codex helper installation.

## Native references

- [Codex plugins](https://learn.chatgpt.com/docs/build-plugins), [hooks](https://learn.chatgpt.com/docs/hooks), [subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Claude plugins](https://code.claude.com/docs/en/plugins), [plugin reference](https://code.claude.com/docs/en/plugins-reference)
- [Antigravity CLI plugins](https://www.antigravity.google/docs/cli/plugins)

Bootstrap preserves existing Codex/Claude versioned hook and tool dependencies under `~/.local/share/nova/hook-compat/` and restores missing cache paths after native updates, including failures. This keeps running sessions functional until restarted. Compatibility files are retained deliberately; do not prune them while sessions still reference those versions.
