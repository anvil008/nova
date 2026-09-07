---
name: jj
description: Use Jujutsu for changes, isolated workspaces, history repair, and bookmark/PR delivery in the project's trunk-based workflow; honor an explicit plain-Git choice.
---

# Jujutsu

Read [shared development instructions](../../instructions/development.md) once per conversation. They govern scope, authorization, trunk, and verification; this skill supplies jj mechanics.

## Inspect and isolate

- Start with `jj --version`, `jj status`, `jj log -n 10`, `jj workspace list`, `jj git remote list`, and `jj bookmark list --all-remotes`. Prefer installed command help when flags differ from the [official CLI reference](https://docs.jj-vcs.dev/latest/cli-reference/).
- For adoption in Git, inspect staged and unstaged work before `jj git init --colocate`; preserve both. Colocated workspaces share Git refs. Prefer jj mutations; jj ignores the Git staging area.
- Identify main or the configured default trunk and remote. Fetch with `jj git fetch --remote <remote>` before selecting a current base; inspect the graph and bookmarks afterward. Fetch updates remote refs and tracked local bookmarks, but does not rebase work. Do not assume local main, `trunk()`, or `@-` is current.
- Reuse a suitable workspace; otherwise run `jj workspace add -r <base> --name <task> ../<repo>-<task>` and work there. Omission of `-r` uses the current working copy's parents, not necessarily trunk. Independent work starts on verified trunk (e.g. `main@origin`); stack only real dependencies.
- Workspaces isolate files but share history and bookmarks. Give concurrent writers separate changes; coordinate before rewriting another workspace's change or ancestors. If stale, run `jj workspace update-stale` in the affected workspace, then inspect status and diff.

## Work and repair

- Most jj commands snapshot edits; new files are tracked automatically by default unless ignored. Keep temporary output outside the checkout or in ignored paths. `jj describe -m "..."` names the current change. `jj new <base> -m "..."` starts a child at that base; `jj commit -m "..."` describes the current change and starts an empty child.
- Quote revsets; specify mutation sources, destinations, and paths. Inspect the diff and descendants before split, squash, rebase, restore, or abandon. `jj rebase -r <change> -o <base>` moves selected revisions; `-s <change>` moves their descendant trees too. Preserve unrelated work and published history.
- A successful rebase can record conflicts; there is no rebase `--continue`. Check `jj status` and `jj log -r '<base>..<tip> & conflicts()'`. Resolve files in the owning change, inspect the snapshotted diff and descendants, and rerun affected checks.
- Diagnose with `jj op log -n 10` and read-only `jj --at-op=<operation> log`. Inspect the operation before undo/revert: recovery can affect other workspaces. `jj op restore` restores repository-wide state. For a file rollback, prefer `jj restore --from <revision> -- <path>` after reviewing what it overwrites.

## Verify and deliver

- Inspect the complete task diff and outgoing ancestors, resolve file and bookmark conflicts, and run required checks. After final edits/description, capture the candidate with `jj log -r <tip> --no-graph -T 'commit_id ++ "\n"'`. Use the revision containing the work; after `jj commit`, that is normally `@-`. A change ID follows rewrites; a commit ID pins one version.
- Bookmarks follow rewrites but do not advance with new commits. Use `jj bookmark create <task> -r <tested-commit>`, or `jj bookmark set <task> -r <tested-commit>` after inspecting an existing task bookmark.
- For authorized publication, preview `jj git push --remote <remote> --bookmark <task> --dry-run`, then push without `--dry-run` and open one short-lived PR into trunk. Consult installed help for first-push tracking requirements. Avoid bare push and broad selectors. On rejection, fetch and reconcile instead of bypassing safety checks or retrying unchanged.
- Integrate after required checks/review within existing authorization. Direct-to-trunk delivery requires verifying the exact candidate before advancing trunk. Report workspace, tested commit, continuation change ID, bookmark/PR, verification limits, and local/published/integrated state in the owning task's response.

Official details: [workspaces](https://docs.jj-vcs.dev/latest/working-copy/), [bookmarks](https://docs.jj-vcs.dev/latest/bookmarks/), [conflicts](https://docs.jj-vcs.dev/latest/conflicts/), [recovery](https://docs.jj-vcs.dev/latest/operation-log/).
