---
name: jj
description: Use Jujutsu for changes, isolated workspaces, history repair, and bookmark/PR delivery in the project's trunk-based workflow; honor an explicit plain-Git choice.
---

# Jujutsu

Read [shared development instructions](../../instructions/development.md) once per conversation. They govern scope, authorization, trunk, and verification; this skill supplies jj mechanics.

Before revision changes or delivery, read [integration procedures](../../instructions/integration.md); reuse them if already loaded.

## Inspect and isolate

- Start with `jj --version`, `jj status`, `jj log -n 10`, `jj workspace list`, `jj git remote list`, and `jj bookmark list --all-remotes`. Prefer installed command help when flags differ from the [official CLI reference](https://docs.jj-vcs.dev/latest/cli-reference/).
- For adoption in Git, inspect staged and unstaged work before `jj git init --colocate`; preserve both. Colocated workspaces share Git refs. Prefer jj mutations; jj ignores the Git staging area.
- Identify main or the configured default trunk and remote. Fetch with `jj git fetch --remote <remote>` before selecting a current base; inspect the graph and bookmarks afterward. Fetch updates remote refs and tracked local bookmarks, but does not rebase work. Do not assume local main, `trunk()`, or `@-` is current.
- Reuse a suitable workspace; otherwise, from the primary checkout, run `jj workspace add -r <base> --name <task> .workspaces/<task>` and work there. Honor the shared workspace placement convention and any explicit repository override; from a secondary workspace, use the primary checkout's absolute destination path. For an explicitly plain-Git workflow, use `git worktree add -b <branch> .workspaces/<task> <base>` from the primary checkout. Omission of `-r` in JJ uses the current working copy's parents, not necessarily trunk. Independent work starts on verified local `main` after reconciling fetched remote updates; keep accumulated local-only results. Stack only real dependencies.
- Workspaces isolate files but share history and bookmarks. Give concurrent writers separate changes; coordinate before rewriting another workspace's change or ancestors. If stale, run `jj workspace update-stale` in the affected workspace, then inspect status and diff.

## Work and repair

- Most jj commands snapshot edits; new files are tracked automatically by default unless ignored. Keep temporary output outside the checkout or in ignored paths. `jj describe -m "..."` names the current change. `jj new <base> -m "..."` starts a child at that base; `jj commit -m "..."` describes the current change and starts an empty child.
- Quote revsets; specify mutation sources, destinations, and paths. Inspect the diff and descendants before split, squash, rebase, restore, or abandon. `jj rebase -r <change> -o <base>` moves selected revisions; `-s <change>` moves their descendant trees too. Preserve unrelated work and published history.
- A successful rebase can record conflicts; there is no rebase `--continue`. Check `jj status` and `jj log -r '<base>..<tip> & conflicts()'`. Resolve files in the owning change, inspect the snapshotted diff and descendants, and rerun affected checks.
- Diagnose with `jj op log -n 10` and read-only `jj --at-op=<operation> log`. Inspect the operation before undo/revert: recovery can affect other workspaces. `jj op restore` restores repository-wide state. For a file rollback, prefer `jj restore --from <revision> -- <path>` after reviewing what it overwrites.

## Verify and deliver

- Inspect the complete task diff and outgoing ancestors, resolve file and bookmark conflicts, and run required checks. After final edits/description, capture the candidate with `jj log -r <tip> --no-graph -T 'commit_id ++ "\n"'`. Use the revision containing the work; after `jj commit`, that is normally `@-`. A change ID follows rewrites; a commit ID pins one version.
- Children hand off immutable local commits without pushing or opening PRs. The parent integrates each ready, verified result promptly into local main. Inspect descendants and conflicts, test the combined result, then `jj bookmark set main -r <verified-commit>` and synchronize the primary checkout when safe. Local main may be ahead of remote main.
- Bookmarks follow rewrites but do not advance with new commits. Use `jj bookmark create <task> -r <tested-commit>`, or `jj bookmark set <task> -r <tested-commit>` after inspecting an existing task bookmark.
- For authorized publication, preview `jj git push --remote <remote> --bookmark <task> --dry-run`, then push without `--dry-run` and open or update the single publication PR into remote main for the accumulated local-main result. Push only its integration bookmark, never main or child bookmarks. Consult installed help for first-push tracking requirements. Avoid bare push and broad selectors. On rejection, fetch and reconcile instead of bypassing safety checks or retrying unchanged.
- After remote merge, capture the merge commit, compare its tree with the published candidate, and account for any newer local descendants before reconciling main. A squash merge can make local main and main@origin divergent despite equivalent content. Preserve immutable mappings and local-only descendants before moving the bookmark; never blindly reset or discard work. Only after proven equivalence and preservation may an explicit bookmark move replace a local equivalent revision with the remote merge revision. Synchronize the primary checkout safely.
- Verify the publication branch is deleted. For superseded PRs, prove their work reached main, record the replacement, close them, and delete only unused heads. Inspect all remaining remote branches for active ownership; do not delete based only on age or closed status. Fetch to prune stale remote refs.
- Report workspace, local and remote main commits, publication PR, branch cleanup, verification limits, and primary-checkout synchronization. A local-only task can finish integrated locally without creating a PR.

Official details: [workspaces](https://docs.jj-vcs.dev/latest/working-copy/), [bookmarks](https://docs.jj-vcs.dev/latest/bookmarks/), [conflicts](https://docs.jj-vcs.dev/latest/conflicts/), [recovery](https://docs.jj-vcs.dev/latest/operation-log/).
