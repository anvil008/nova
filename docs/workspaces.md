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
- **One base.** Every issue in a wave is created on the same base; moving it afterwards
  invalidates whatever was sealed against it. `--base` defaults to `trunk()` on jj — but only once
  `trunk()` is known to resolve to a real commit. In a repository with no remote for it to resolve
  through, `trunk()` degrades to the root commit, and branching there would hand an agent an empty
  tree, so the helper falls back to the local `main` / `master` / `trunk` bookmark and refuses
  outright if there is none. On git the default is `origin/HEAD`, else `main` / `master` / `trunk`.
- **Teardown after the PR exists, never before.** Forgetting a workspace stops tracking the
  working copy and removes the directory. It never deletes the bookmark, the branch, or their
  commits, so the open PR is unaffected. Forgetting first strands the branch.

```sh
workcell-ws add <key> [--base <rev>] [--repo <dir>]     # create ../<repo>-<key>, bookmark <key>
workcell-ws forget <key> [--force] [--repo <dir>]       # drop the working copy, keep the bookmark
workcell-ws list [--repo <dir>]                         # name, revision, state, path
workcell-ws sweep [--apply] [--force] [--repo <dir>]    # report, or remove, what leaked
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
| `stale-dir` | ours by its pointer, but nothing registered it — an agent died mid-creation |
| `foreign` | matches the naming convention but is an independent repository — never a sweep target |

`workcell-ws sweep` reports every `stale-dir`, `stale-reg`, and `merged` entry plus every local
bookmark or branch already merged into the default branch. Without `--apply` it is strictly
read-only; with `--apply` it removes exactly what it reported and nothing it refused. It never
touches a remote, never deletes an unmerged ref, and never touches the primary working copy. Run
it in `build`'s resume step before dispatching the next wave, and after any run that crashed.

"Merged" means *strictly* behind the default branch. A ref sitting exactly on the default tip is
either a workspace an agent created seconds ago — `git worktree add` branches at the tip — or one
that fast-forwarded, and the two are indistinguishable, so the sweep leaves it until the default
branch moves on.

## What it refuses, and why

A working copy is deleted irreversibly, so the helper refuses rather than guessing. Every refusal
names the reason and, where one exists, the override.

- **A sibling that is not ours.** A directory is a workspace of this repository only when it
  carries a *pointer* back to it: a `.git` file holding `gitdir: <common-dir>/worktrees/<name>`, or
  a `.jj/repo` file resolving to `<repo>/.jj/repo`. A full `.git/` or `.jj/repo/` directory is
  somebody else's repository that merely collides on the naming convention. It is listed `foreign`,
  reported by `sweep` as a note, and never removed — `--force` does not change that.
- **Uncommitted work in a git worktree.** `git status --porcelain` decides; the refusal names the
  paths. `--force` overrides, and only then does the helper pass `--force` to
  `git worktree remove`. A jj workspace needs no such refusal: its working copy is a commit, so
  the helper snapshots it into the repository first and the content stays recoverable from the
  bookmark after the directory is gone.
- **A `stale-dir` whose registration is gone.** Neither jj nor git can say what is uncommitted in
  it — `jj st` there answers "No working copy" and exits zero, which is not a snapshot — so
  reclaiming it needs `sweep --apply --force` or `forget <key> --force`. A plain `--apply` keeps
  it and prints why.
- **A workspace the calling shell is standing in.** Removing it leaves that shell with a dead
  working directory. No flag overrides this one; `cd` out first.
