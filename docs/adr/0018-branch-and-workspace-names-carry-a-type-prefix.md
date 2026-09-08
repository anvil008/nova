# 18. Branch and workspace names carry a type prefix

## Status

Accepted

## Context

[ADR 0014](0014-one-workspace-helper-across-harnesses.md) settled on one helper and one name:
the unit of work is a key, and that key was the sibling directory, the jj workspace, the
bookmark, and the git branch, all spelled identically. One string, no mapping, nothing to
derive — which is what made a leaked workspace nameable weeks later.

What the key did not say is what kind of work it was. A repository with a dozen branches in
flight across `build`, `debug`, `docs`, `code-refactor`, and `perf` runs shows a flat list of
slugs: `waves-py-selection` gives no hint whether it is new behaviour, a repair, or a
documentation pass, and `git branch --list 'bug/*'` is not a question that can be asked at
all. Every git convention a human already has for this — `feature/`, `bug/`, `release/` —
uses a slash, and the reason the helper avoided one was mechanical rather than aesthetic: a
sibling directory name cannot carry a `/` without nesting itself inside a parent that does
not exist, and a jj workspace name is a flat identifier.

That constraint applies to the directory and the jj workspace. It does not apply to the
bookmark or the git branch, where a slash is ordinary and expected.

## Decision

**A key is `<type>/<slug>`.** The type is one of `feature`, `bug`, `doc`, `refactor`, `perf`,
`test`, `release`, `chore`, `review`, `integration`; each part matches `[a-z0-9][a-z0-9-]*`.
`nova-ws` accepts at most one slash and refuses anything else by name, so `a/b/c`, a
leading slash, and a trailing slash are all rejected before the repository is touched.

**The key is the bookmark and the branch, verbatim.** The directory and the jj workspace
write its slash as a dash: `feature/xyz` is bookmark `feature/xyz`, jj workspace
`feature-xyz`, directory `../<repo>-feature-xyz`. A bare slug with no type is still a key,
and its three spellings are identical — which is exactly what every key was before this ADR,
so nothing already on disk changes meaning.

**The reverse mapping is read from the refs, never guessed.** Dashing a slash out is lossy,
so `list`, `forget`, and `sweep` recover a key by asking which local bookmark or branch
dashes to the directory's name — an exact match first, so a dash-only key answers itself
even where a slashed namesake exists, and the directory name itself when no ref explains it.
A workspace therefore round-trips under the key it was created with, and `forget` also
accepts the directory spelling of it.

**Each skill mints one type**: `build` issues take `feature/` unless the planner labelled the
issue `type:bug`, `debug` takes `bug/`, `docs` `doc/`, `code-refactor` `refactor/`, `perf`
`perf/`, `new-feature` `feature/`, `deploy` release branches `release/`, and test-only work
`test/`. The planner assigns the feature-or-bug distinction when it writes the plan, because
that is the point at which somebody has decided what the issue is.

**Two existing names are left alone.** `review-fix-loop` works on `loop-branch` and `build`'s
single-PR mode integrates on `<planId>-integration`. Both are load-bearing literals in
`loop_state.py` and its tests; renaming them buys nothing this ADR is about.

## Consequences

A branch name now says what kind of work it is, `git branch --list 'bug/*'` answers, and a
sibling directory listing groups by type without anyone maintaining an index. The cost is one
mapping where there were none: the key and the directory are no longer the same string, and
every place that joins a name to a path or a ref has to know which of the two it holds. That
mapping lives in one script and is exercised in both directions by the helper's tests, on
both the jj and the git path.

The recovery is only as good as the ref. A workspace whose bookmark someone deleted by hand
lists under its dashed name rather than its key — the documented fallback, not an error, and
`forget` takes either spelling — and a `foreign` sibling that happens to dash to a real ref
is displayed under that ref's name. Neither affects what is removed: `foreign` is still never
a sweep target, and every removal is decided by the directory's pointer, not by its name.

Two keys that differ only in a slash — `feature-x` and `feature/x` — collide on one
directory. The helper refuses the second `add` because the target already exists, which is
the same refusal it has always given, and git independently refuses `feature/x` while a
branch named `feature` exists. Both surface as the refusal that caused them rather than as a
silent overwrite.

Nothing about the base, the seal, teardown, or the sweep's safety rules changes. This ADR
changes what a workspace is called and nothing about what may be done to one.
