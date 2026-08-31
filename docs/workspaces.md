# Workspaces

Every unit of agent work happens in its own working copy, and there is exactly one way to make
one, name one, and get rid of one — `scripts/workcell-ws`, linked to `~/.local/bin/workcell-ws`
by `bootstrap-tools.sh --install`. All three harnesses call it through the shell, so the standard
is identical on Claude, Codex, and Antigravity.

## The standard

- **One repository, many working copies.** Never a second clone. A jj repo gets a jj workspace
  (one operation log, so `jj undo` still reaches everything); a git-only repo gets a git worktree.
  The helper picks by looking for `.jj/` at or above the working directory.
- **One naming convention.** The workspace for `<key>` is the sibling directory
  `../<repo-basename>-<key>`, and its bookmark or branch is `<key>`. `<key>` is the issue key from
  the dispatch brief, matching `[a-z0-9][a-z0-9-]*`. Nothing derives a path any other way, which
  is what makes a leak nameable later.
- **One base.** `--base` defaults to `trunk()` on jj and to the default branch on git. Every issue
  in a wave is created on the same base; moving it afterwards invalidates whatever was sealed
  against it.
- **Teardown after the PR exists, never before.** Forgetting a workspace stops tracking the
  working copy and removes the directory. It never deletes the bookmark, the branch, or their
  commits, so the open PR is unaffected. Forgetting first strands the branch.

```sh
workcell-ws add <key> [--base <rev>] [--repo <dir>]   # create ../<repo>-<key>, bookmark <key>
workcell-ws forget <key> [--repo <dir>]               # drop the working copy, keep the bookmark
workcell-ws list [--repo <dir>]                       # name, revision, state, path
workcell-ws sweep [--apply] [--repo <dir>]            # report, or remove, what leaked
```

Every subcommand works from the repository, from one of its workspaces, or with `--repo`.

## The leak check

Agents die. When one does, it leaves a workspace nobody will tear down, and the fleet has
collected orphaned workspaces and stale bookmarks that way. `workcell-ws list` gives each entry a
state:

| State | Meaning |
| --- | --- |
| `active` | registered, and its directory is there |
| `merged` | live, but its bookmark/branch is already contained in the default branch |
| `stale-reg` | registered, directory gone — someone removed the directory without forgetting |
| `stale-dir` | directory there, nothing registered it — an agent died mid-creation |

`workcell-ws sweep` reports every `stale-dir`, `stale-reg`, and `merged` entry plus every local
bookmark or branch already merged into the default branch. Without `--apply` it is strictly
read-only; with `--apply` it removes exactly what it reported. It never touches a remote, never
deletes an unmerged ref, and never touches the primary working copy. Run it in `build`'s resume
step before dispatching the next wave, and after any run that crashed.

"Merged" means *strictly* behind the default branch. A ref sitting exactly on the default tip is
either a workspace an agent created seconds ago — `git worktree add` branches at the tip — or one
that fast-forwarded, and the two are indistinguishable, so the sweep leaves it until the default
branch moves on.
