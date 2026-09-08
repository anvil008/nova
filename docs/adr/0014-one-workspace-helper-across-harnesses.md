# 14. One workspace helper across harnesses

## Status

Accepted

## Context

Agent isolation had drifted into four different stories. The `test-author` ran `jj workspace add`
by hand; `code-refactor` had the orchestrator type a slightly different `jj workspace add` with a
sibling path spelled out inline; a git-only repository had no story at all beyond "adopt jj first";
and the teardown was prose in the builder body — `jj workspace forget` plus `rm -rf` — that nothing
checked. Nothing named the convention, so nothing could recognise a violation of it.

The cost is leaks. An agent that dies between creating its workspace and opening its PR leaves a
working copy nobody will forget, and a merged branch leaves a bookmark nobody will delete. One
session of this fleet found four orphaned workspaces and eighteen stale bookmarks, none of which
any command could have listed, because there was no shared definition of what "stranded" meant.

## Decision

One helper, `scripts/nova-ws`, owns creation, teardown, listing, and sweeping, and it is the
only thing any agent body or skill tells an agent to run. It is a shell script, so all three
harnesses reach it the same way, and `bootstrap-tools.sh --install` links it onto `PATH` beside the
`build-*` hooks.

It fixes one naming convention: the workspace for `<key>` is the sibling directory
`../<repo-basename>-<key>` and its bookmark or branch is `<key>`. A jj repository gets a jj
workspace, a git-only repository a git worktree, with the same names, the same base defaults
(`trunk()` and the default branch), the same refusals, and the same teardown.

Because the convention is now mechanical, so is the leak check. `nova-ws list` labels every
entry `active`, `merged`, `stale-reg`, or `stale-dir`, and `nova-ws sweep` reports exactly
those plus every local ref already merged into the default branch. It is read-only until
`--apply`, it never deletes an unmerged ref or touches a remote, and `merged` means strictly
behind the default branch so a workspace created seconds ago is never mistaken for a finished one.
The standard is written down in [docs/workspaces.md](../workspaces.md).

## Consequences

`agents/bodies/test-author.md`, `agents/bodies/builder.md`, `skills/build`, and
`skills/code-refactor` now name the helper where they used to spell out `jj` commands. Each keeps
the raw equivalent in a comment, so the underlying jj commands remain valid, remain readable, and
remain usable in a repository where the helper is not installed — the helper is the standard, not
a new dependency of the workflow.

Git-only repositories gain parity: they can run isolated waves without adopting jj, which makes
`repo-setup`'s jj recommendation an optimisation for parallel work rather than a prerequisite.
Adopting jj is still the recommendation, because one operation log and `jj undo` are what make
many concurrent working copies recoverable.

Because the helper now deletes directories on the fleet's behalf, it is deliberately reluctant.
Ownership is decided by a pointer, not by a name: a sibling is ours only when its `.git` file
resolves under this repository's `worktrees/` directory or its `.jj/repo` file resolves to this
repository's store. A full `.git/` or `.jj/repo/` directory is an independent repository that
merely collides on the naming convention, is listed `foreign`, and is never removed — the sweep
reports it as a note and `--force` does not change that.

Uncommitted work is likewise never destroyed silently, and the two version-control systems earn
different treatment because they genuinely differ. A jj working copy *is* a commit, so `forget`
snapshots it into the repository first and the content stays recoverable from the bookmark after
the directory is gone. A git working tree is not, so a dirty one is refused by name until it is
committed or `--force` is passed, and only then is `--force` passed on to `git worktree remove`.
A `stale-dir` is refused in both, because once the registration is gone neither system can say
what is uncommitted in it — `jj st` there answers "No working copy" and exits zero, which is not a
snapshot. A workspace the calling shell is standing in is refused with no override at all, since
removing it strands that shell.

The cost is that the routine reclaim is now two commands in the worst case: `sweep --apply` clears
merged and stale registrations, and `sweep --apply --force` is needed for a stale directory. That
is the intended trade — every refusal prints its reason and its override on the line, so nothing
is hidden, and the sweep still exits zero so a resume step can run it unattended. That invariant
reaches into the ref cleanup too: a merged ref belonging to a workspace the sweep kept is reported
and skipped rather than deleted, since deleting it would fail on git and would silently drop a kept
working copy's bookmark on jj. Only an unexpected delete failure is a failure.

The sweep is only as good as the convention: a workspace created outside `../<repo>-<key>` is
still visible while it is registered, but once its registration is gone the sweep cannot recognise
the directory as one of ours.
