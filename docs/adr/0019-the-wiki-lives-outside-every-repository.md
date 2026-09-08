# 19. The wiki lives outside every repository

## Status

Accepted

## Context

Every Nova run learns something about the project it ran against — which suite is slow, which
runner is flaky, which module's tests lie, which review finding keeps coming back — and every run
throws it away. The next `build` on the same repository starts from the same generic skills with
the same blind spots, and the same review pass rediscovers the same failure mode a week later.
The skills encode what is true of _every_ project; nothing encodes what is true of _this_ one.

The obvious place to keep that knowledge is the repository itself, in a tracked or ignored
directory beside the code. That design has to argue its way past a property the eval tiers depend
on: an eval scores a patch, so anything the agent writes inside the task repository is either
scored as part of the deliverable or has to be excluded by a rule that someone has to write,
maintain, and prove. The same argument repeats for `build`'s per-issue workspaces, whose diffs
become pull requests, and for the working copy a reviewer reads. Every one of those is a place a
per-repository store would have to be _kept out of_, and "kept out of" is a rule, and a rule is
something a guard has to enforce and a test has to pin.

Two other constraints shape the store. A repository resolves to more than one directory in normal
use — [ADR 0014](0014-one-workspace-helper-across-harnesses.md) gives every issue its own jj
workspace, and a project may be cloned twice on one machine — so anything keyed by "the current
directory" would fork a project's memory across its own workspaces. And
[ADR 0013](0013-eval-mode-removes-the-human-pauses-not-the-gates.md) draws a hard line around
benchmark runs: an eval measures the shipped harness, so a run that could read remembered advice
about the task repository, or write into a store a later run reads, is measuring something else.

Nova has no user-level state today. This decision introduces one, which is a cost worth
naming rather than a detail: the mechanism ships in the repository and is reviewed like code, but
the data it produces is per machine and per user from the first write.

Keeping the store outside every repository settles where knowledge accumulates, not where it ends
up. Some of what a project learns eventually belongs in the repository, reviewed and committed
like anything else a team relies on — an instruction file, a checked-in convention. Those two
things are not in tension as long as the direction is one-way and the crossing is a human-reviewed
commit rather than an agent writing into a working copy: accumulation is local and untracked,
publication is a pull request. This ADR settles the direction; it builds only the accumulating
half.

## Decision

- **One store, outside every repository.** The mechanism ships in Nova; the data lives in one
  store at `$NOVA_WIKI_HOME`, defaulting to `~/.nova/wiki/`, with one namespace per
  project at `~/.nova/wiki/<project-key>/`. `~/.nova/` is a new root this decision
  introduces, and the override is named after `NOVA_EVAL_TASK_DIR`, the only prior precedent
  for an environment variable that relocates something Nova owns.
- **Per-project namespacing is absolute.** There is no flat shared wiki and no cross-project
  namespace: a namespace holds one project's history, is never merged with another project's, and
  cannot be read across projects. One project's runner flakiness is not evidence about anything
  else.
- **The project key is the normalized `origin` remote**, falling back — with no remote — to the
  toplevel basename plus the first eight hex characters of a sha256 hash of the resolved absolute
  toplevel, so two checkouts that merely share a directory name stay apart. Normalizing strips the
  scheme, user, and port and any trailing `.git`, lower-cases the rest, and joins host and path
  segments with dashes, so `git@github.com:anvil008/nova.git` and
  `https://github.com/anvil008/nova` are one project.
- **The key is resolved from the repository's primary toplevel**, exactly the way `nova-ws`
  resolves one — through the `.jj/repo` indirection for a secondary jj workspace, through the
  first `git worktree list --porcelain` entry for git — so every workspace of a repository shares
  the same key rather than growing a memory of its own. It is spelled in the character class
  `nova-ws` already enforces, `[a-z0-9][a-z0-9-]*`, so a wiki key and a workspace key obey one
  rule and neither can carry a path separator.
- **Identity is recorded rather than inferred.** `project.json` names the source the namespace was
  created from, every later command re-resolves and compares, and a mismatch is refused by name —
  printing both the recorded source and the resolved one — rather than silently sharing or forking
  a namespace. Settling a collision is a human act, like entering eval mode.
- **A namespace's existence is the entire opt-in.** A project without one behaves exactly as it
  does today: nothing is recorded, nothing is dispatched, and no tokens are spent. Creating one is
  a person running `wiki.py init` once, and nothing else creates a namespace.
- **Three layers, three durability rules.** `raw/` holds write-once evidence bundles under hashed
  manifests; the wiki proper — `patterns/`, `index.md`, `logs.md`, `skill-impact.md` — is
  append-only and is never reset or rolled back, because a page that is edited cannot be told
  apart from a page that was always right; and `skills/` is untouched by this decision.
- **The ablation now holds structurally.** Because the store is outside every repository, no
  working copy, no `build` workspace, no pull-request diff, and no scored eval patch can contain
  it — the property the earlier per-repository design would have had to argue for is a consequence
  of where the bytes live.
- **No guard change was needed, and that was checked rather than assumed.** `build-guard` has no
  outside-repository write rule to relax: its only path denials are the eval-mode marker and
  RAM-backed build target directories. `tdd-guard`'s sealed-path check returns false for any path
  that resolves outside the repository, so a namespace can never be mistaken for a sealed test.
- **A repository in eval mode neither records nor consolidates.** The `.nova/eval-mode.json`
  marker is checked against the target repository the namespace was resolved from, never against
  the store or the caller's directory, and every `--repo` subcommand refuses on it — reads
  included, so a benchmark run cannot contaminate or be contaminated by a real project's history.
- **Runtime agents are never given the wiki.** The `specifier`, `builder`, `reviewer`, and
  `integrator` neither read a namespace nor write one; they work against a sealed Definition of
  Done, and a page of remembered opinion reaching them would quietly compete with it. Only the
  orchestrator asks whether a project opted in, and only one `documenter` dispatch writes.
- **The split is two-layered: local memory, then committed overlay.** The wiki is untracked local
  working memory, and only its distilled output feeds committed project-local overlays in the
  target repository — the direction is settled here, and no mechanism that writes such an overlay
  is built by this decision or scheduled by it. What holds from today: a project pattern never
  amends Nova's shared
  `skills/`, which keep changing through evidence-backed pull requests gated by the eval tiers,
  because a model- or project-specific workaround promoted into a shared skill transfers
  negatively to every other project.
- **One writer.** Everything above is enforced by `skills/wiki/scripts/wiki.py`, the store's only
  writer, and re-proved by `wiki.py check`; the artifact contract is
  [`skills/wiki/references/wiki-layout.md`](../../skills/wiki/references/wiki-layout.md).

## Consequences

The wiki is per machine and per user rather than per team: two people working the same repository
build two independent memories, and a fresh machine starts empty. `NOVA_WIKI_HOME` is the
relocation lever — a synced or shared directory works today because the store's location is the
only thing that binds it to a machine — but a real export path, with the review that sharing one
project's remembered opinions deserves, is deferred to the later milestone that adds the proposer.
That milestone is named here only as where the work is expected to land; nothing about its design
is decided by this ADR, and it is a separate question from the committed overlay above and from
the skill-change proposal entries whose shape `skill-impact.md` already documents and nothing yet
writes.

Because the store sits outside the repository, the repository's own guards do not reach it, and
the harness's own permission model is the remaining surface protecting it. That is why every write
goes through one `wiki.py` invocation rather than an editor tool: a single CLI is what enforces
write-once bundles, append-only pages, a derived catalog, and one log line per write, and it is a
surface a permission rule can name, while `Write` and `Edit` against a path under `~/.nova/`
are not.

The layer is opt-in and silent by default, so nothing changes for a project that never runs
`wiki.py init` — which also means the layer earns its keep only where a human deliberately turned
it on, and an unused namespace decays into stale advice with no one reading it. `wiki.py check`
proves a namespace is internally consistent; it does not prove the prose is still true.

`~/.nova/` is a new user-level root, and future user-level state — caches, configuration —
now has an obvious home and an obvious naming convention to follow.
