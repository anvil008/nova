# Harness configuration and workspace behavior

Nova shares skills and development conventions across Codex, Claude Code, and Antigravity CLI (Agy). Native capabilities and installation mechanisms differ. This page describes the configuration shipped by this repository; desktop app settings are separate. Update this comparison when changing packaging, hooks, helper definitions, or bootstrap behavior.

## Workspace placement

The common destination is `<primary-checkout>/.workspaces/<task>/`. For Nova on the development box it is `/home/anvil/repos/nova/.workspaces/<task>/`. Both JJ workspaces and Git worktrees use this container. It is outside `.git/` and `.jj/`, which contain version-control metadata. Existing sibling workspaces are not moved.

| Behavior | Codex | Claude Code | Agy |
| --- | --- | --- | --- |
| Nova task workspace creation | Follow project `AGENTS.md` and shared instructions | Packaged `WorktreeCreate` hook for native isolation | Follow project `AGENTS.md` and shared instructions/rules |
| JJ repository | Agent runs `jj workspace add` | Hook detects JJ and runs `jj workspace add` | Agent runs `jj workspace add` |
| Git-only repository | Agent runs `git worktree add` | Hook runs `git worktree add` | Agent runs `git worktree add` |
| Dedicated creation/removal hook | No documented equivalent | `WorktreeCreate` and `WorktreeRemove` | No documented equivalent |
| Arbitrary shell-created workspace | Instructions apply | Instructions apply; native worktree hooks do not intercept shell commands | Instructions apply |
| Cleanup | Explicit agent workflow | Clean Git worktrees removed; dirty/ignored files and all JJ workspaces retained | Explicit agent workflow |

### Claude hook contract

The package builder registers `hooks/workspace.py` for both native events only in the Claude bundle. It activates when Claude invokes its native isolation flow, including `--worktree` and supported isolated subagents. Native hook trust and plugin enablement still apply. It does not start a model or change app settings.

Creation resolves the primary repository through `.jj/repo` or Git's common directory, even when invoked from a secondary workspace. A conventional non-bare Git checkout is required for the Git path. Names must be single slugs, up to 100 characters, containing letters, digits, dashes, or underscores and starting with a letter or digit. Existing paths, invalid names, and symlinked workspace containers are refused.

JJ creation starts from local `main` so unpublished integrated results are included; absent local main, it falls back to `trunk()`. A conflicted main is refused. Git creation prefers the local branch named by `origin/HEAD`, then that remote ref; without origin/HEAD it tries local main/master before remote main/master, on a new `worktree-<task>` branch. If none exists it fails and asks for `origin/HEAD` to be configured; it never falls back to an unrelated checked-out task. The hook does not fetch; refresh remote refs before starting isolation when an up-to-date remote base is required. Claude's `worktree.baseRef` setting does not control this replacement hook.

For Git and colocated JJ, the hook adds `/.workspaces/` to the main Git repository's local `info/exclude` if absent. For non-colocated JJ, add that exact line to the primary `.gitignore` before use. Nova itself includes the tracked ignore rule. Search/build tools that ignore neither file need their own exclusion.

The hook replaces Claude's built-in creation behavior, including automatic `.worktreeinclude` copying. It copies no ignored environment files or dependencies. Set up required local files inside the new workspace explicitly.

Removal accepts only a direct child of the primary `.workspaces/` directory. Git cleanup checks modified, untracked, and ignored files before calling `git worktree remove`, without force or branch deletion. JJ cleanup deliberately returns a retention diagnostic and a nonzero status: inspect the workspace, preserve any needed files, then use `jj workspace forget <name>` from another workspace and remove the directory explicitly. This prevents native session cleanup from discarding JJ task files. Retained workspaces can require manual session cleanup in Claude.

### Desktop apps are a separate layer

| App-created worktrees | Documented control | Nova coverage |
| --- | --- | --- |
| Codex app | Settings → Worktrees → Worktree root; default `$CODEX_HOME/worktrees` | Markdown and tool hooks do not configure the app's internal creator |
| Claude Desktop | Settings → Claude Code → Worktree location; default `<project>/.claude/worktrees/` | CLI/native-hook behavior does not prove the desktop host uses that hook for its own isolation |
| Antigravity app | Offers a new-worktree project mode | A per-repository location override has not been verified |

A fixed app-wide directory is not necessarily a template relative to each repository. Do not point every project's app-created worktrees at Nova's directory. No desktop location settings are changed by bootstrap. To use the exact Nova layout reliably, create the workspace through the documented agent/hook workflow and open that directory in the app.

Inspect registered locations with `jj workspace list` and `git worktree list --porcelain`; neither list substitutes for the other in a colocated repository.

## Other configured differences

| Area | Codex | Claude Code | Agy CLI |
| --- | --- | --- | --- |
| Persistent project guidance | `AGENTS.md` | `CLAUDE.md` or supported imports | Project `AGENTS.md`/supported rules; personal `GEMINI.md` on this box |
| Shared skill instructions | Each Nova skill reads bundled `instructions/development.md` | Same | Same; also packaged as `rules/nova.md` |
| Native plugin marker | `.codex-plugin/plugin.json` | `.claude-plugin/plugin.json` | `plugin.json` |
| Optional helper installation | `setup/agents/*.toml`; bootstrap `--with-codex-helpers` installs owned copies | Native `agents/*.md` inside plugin | Native `agents/<role>/agent.md` inside plugin |
| Scout model in source | `gpt-5.6-luna` | `haiku` | `gemini-3.8-flash-low` |
| Implementer model in source | `gpt-5.6-terra`, high effort | `claude-opus-5`, medium effort | `gemini-3.8-flash-high` |
| Large-read routing | Packaged PreToolUse hook | Packaged PreToolUse hook | Packaged PreToolUse hook with Agy payload/response shape |
| Post-edit formatting/linting | Packaged runner; inactive without `NOVA_HOOK_CONFIG` | Same | Explicit adapter setup; diagnostics go to logs |
| Automatic Nova Flow tracking | Disabled | Disabled | Disabled |
| Explicit Nova Flow CLI | Available | Available | Available |

Models above are configured helper values, not guarantees of provider availability or overrides of the main conversation's model. Reviewers have no explicit model override in the current helper definitions. Read routing uses the existing scout; it does not launch a mandatory team or enable Flow. See [read routing](read-routing.md) and [development conventions](development.md).

## Installation and verification

Run `./scripts/bootstrap.sh --harness all` from the source checkout to refresh the three installed bundles. Optional Codex helper updates require `--with-codex-helpers`. Bootstrap uses content-derived development versions and self-contained files under `~/.local/share/nova/plugins/`; native managers may copy them into separate caches. Source edits alone do not update an installed copy. Start new sessions after installation.

Bootstrap automatically aligns host global instruction files (`~/.codex/AGENTS.md`, `~/.claude/CLAUDE.md`, and `~/.gemini/GEMINI.md`) from `instructions/global/` using ownership receipts, keeping trunk-based development and workspace placement standards consistent across all tools. Pass `--no-align-global` to skip host file synchronization, or `--force-global` to overwrite unmanaged modifications. Reconcile project/personal guidance during repo setup; the shared package remains the portable source of Nova conventions.

Verify package contents and native discovery separately from actual hook execution. Workspace tests exercise real Git/JJ creation, secondary-workspace routing, collision refusal, and file retention. A successful install alone does not establish desktop app behavior, model compliance, or automatic hook trust. See [installation](install.md) for commands and update behavior.

## Native references

- [Claude worktree hooks](https://code.claude.com/docs/en/hooks#worktreecreate)
- [Claude CLI worktrees](https://code.claude.com/docs/en/worktrees)
- [Claude Desktop worktrees](https://code.claude.com/docs/en/desktop)
- [Codex hooks](https://learn.chatgpt.com/docs/hooks)
- [Codex app worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)
- [Agy hooks](https://antigravity.google/docs/hooks)
- [Agy projects](https://www.antigravity.google/docs/projects)
- [JJ workspaces](https://docs.jj-vcs.dev/latest/working-copy/#workspaces)

## Task integration and completion

All harnesses follow the parent-owned integration policy summarized in development.md and detailed in [integration.md](integration.md) for both JJ and Git. Codex and Claude packages register SubagentStop, Stop and SessionEnd command hooks: a child exit schedules one parent Stop reminder to finish verified integration and local-main synchronization. The hook never blocks the child or merges code itself. It consumes its marker and respects stop_hook_active to avoid a continuation loop; it is a reminder, not proof that integration happened. A read-only child also triggers the reminder, which explicitly requires no merge in that case. Sessions with no child event rely on the standing instructions. Session markers live under XDG_CACHE_HOME/nova/integration (default ~/.cache/nova/integration).

Agy uses persistent rules plus a PostToolUse/Stop adapter: successful invoke_subagent calls arm a conversation marker, and a normal fully idle Stop consumes it and returns continue once with the integration reminder. This is a delegation signal, not a native child-completion event. Errors/background work do not trigger continuation; an unused marker can persist until the same conversation resumes. No Flow tracking is enabled. Claude WorktreeRemove also refuses clean Git worktrees whose HEAD is not an ancestor of local trunk. Squash/rebase equivalents require explicit parent verification and manual cleanup. JJ cleanup remains explicit.

Hook contracts: [Codex hooks](https://learn.chatgpt.com/docs/hooks), [Claude hooks](https://code.claude.com/docs/en/hooks).

All parents integrate ready verified results into local main promptly; children keep intermediate commits local. Publication uses one integration bookmark and PR for accumulated results, with explicit merged/superseded branch cleanup and safe reconciliation of local-only descendants after a remote squash merge. See [the complete delivery policy](integration.md#parent-owned-task-integration).
