# Workspaces

Every unit of agent work happens in its own working copy, and there is exactly one way to make
one, name one, and get rid of one — `scripts/workcell-ws`, installed as a versioned copy at
`~/.local/bin/workcell-ws` by `bootstrap-tools.sh --install`, never a link, so editing the script
in a checkout changes nothing until the next `--install`. All four harnesses call it through the
shell, so the standard is identical on Claude, Codex, Antigravity, and Grok Build.

## The standard

- **One repository, many working copies.** Never a second clone. A jj repo gets a jj workspace
  (one operation log, so `jj undo` still reaches everything); a git-only repo gets a git worktree.
  The helper picks by looking for `.jj/` at or above the working directory.
- **One naming convention.** A key is `<type>/<slug>` — the type says what kind of work it is,
  the slug is the issue key from the dispatch brief — and each part matches `[a-z0-9][a-z0-9-]*`.
  The key _is_ the bookmark or branch, verbatim. A directory and a jj workspace name cannot carry
  the slash, so both write it as a dash: key `feature/xyz` is bookmark `feature/xyz`, jj workspace
  `feature-xyz`, and sibling directory `../<repo-basename>-feature-xyz`. A bare slug with no type
  is still a key, and its three spellings are identical. Nothing derives a path any other way,
  which is what makes a leak nameable later.

  | Type           | Minted by                                                  |
  | -------------- | ---------------------------------------------------------- |
  | `feature/`     | `build` issues by default, `new-feature`                   |
  | `bug/`         | `debug`, and a `build` issue the planner labelled a defect |
  | `doc/`         | `docs`                                                     |
  | `refactor/`    | `code-refactor`                                            |
  | `perf/`        | `perf`                                                     |
  | `test/`        | work that only authors tests                               |
  | `release/`     | `deploy` release branches                                  |
  | `chore/`       | maintenance no other type covers                           |
  | `review/`      | a review-fix pass on a branch of its own                   |
  | `integration/` | a wave's integration branch                                |

  Two names predate the table and stay as they are: `review-fix-loop` works on `loop-branch`, and
  `build`'s single-PR mode integrates on `<planId>-integration`.

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

| State       | Meaning                                                                               |
| ----------- | ------------------------------------------------------------------------------------- |
| `active`    | registered, and its directory is there                                                |
| `merged`    | live, but its bookmark/branch is already contained in the default branch              |
| `stale-reg` | registered, directory gone — someone removed the directory without forgetting         |
| `stale-dir` | ours by its pointer, but nothing registered it — an agent died mid-creation           |
| `foreign`   | matches the naming convention but is an independent repository — never a sweep target |

`workcell-ws sweep` reports every `stale-dir`, `stale-reg`, and `merged` entry plus every local
bookmark or branch already merged into the default branch. Without `--apply` it is strictly
read-only; with `--apply` it removes exactly what it reported and nothing it refused. It never
touches a remote, never deletes an unmerged ref, and never touches the primary working copy. Run
it in `build`'s resume step before dispatching the next wave, and after any run that crashed.

"Merged" means _strictly_ behind the default branch. A ref sitting exactly on the default tip is
either a workspace an agent created seconds ago — `git worktree add` branches at the tip — or one
that fast-forwarded, and the two are indistinguishable, so the sweep leaves it until the default
branch moves on.

## What it refuses, and why

A working copy is deleted irreversibly, so the helper refuses rather than guessing. Every refusal
names the reason and, where one exists, the override.

- **A sibling that is not ours.** A directory is a workspace of this repository only when it
  carries a _pointer_ back to it: a `.git` file holding `gitdir: <common-dir>/worktrees/<name>`, or
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
- **A merged ref whose workspace the sweep just kept.** Deleting it would fail anyway on git,
  where the surviving worktree still holds the branch, and would silently drop the bookmark of a
  working copy the sweep deliberately kept on jj. It is reported as
  `kept ref <key> — workspace kept, remove it first` and the sweep still exits zero, so an
  unattended resume step is never tripped by it.
- **A workspace the calling shell is standing in.** Removing it leaves that shell with a dead
  working directory. No flag overrides this one; `cd` out first.
