# Wiki layout — the artifact contract

The shapes `skills/wiki/scripts/wiki.py` writes and the rules it enforces. The agent
consolidating a project's runs reads this file; the operator reads
[`SKILL.md`](../SKILL.md).

Every field the CLI is given — a kind, a summary, a note, a title — is folded to one line
before it is written, so no argument can smuggle a second line into an append-only file
and have it read back as an entry nothing recorded.

Nothing outside `wiki.py` writes a namespace. Every rule below is enforced by the CLI, so
an editor tool reaching into a namespace does not "save a step" — it removes the only
thing keeping the layer trustworthy.

## Where the store lives

`$WORKCELL_WIKI_HOME`, defaulting to `~/.workcell/wiki/`, with one namespace per project
at `<root>/<project-key>/`. The store is outside every repository on purpose: a namespace
outlives the branches, worktrees, and clones of the project it describes, and no working
copy can carry it into a diff.

`--repo <path>` names the **target repository** and is how the key, the eval-mode marker,
and the identity check are all resolved; it defaults to the working directory.
`--namespace <path>` names a namespace directory outright and bypasses both resolutions —
the mode the shipped demonstration and the tests use.

## The project key

`wiki.py key --repo <path>` prints the derivation so it can be inspected on its own:

```json
{
  "projectKey": "github-com-anvil008-workcell",
  "source": "remote",
  "derivedFrom": "git@github.com:anvil008/workcell.git"
}
```

1. **Resolve the primary toplevel** exactly as `scripts/workcell-ws` does: through the
   `.jj/repo` indirection for a secondary jj workspace, through the first
   `git worktree list --porcelain` entry for git. Every per-issue workspace `build`
   creates therefore answers with the key of the repository it came from, not its own.
2. **With an `origin` remote**, the key is the normalized remote: scheme, user, and port
   stripped, a trailing `.git` stripped, lower-cased, and host and path segments joined
   with dashes. `git@github.com:anvil008/workcell.git` and
   `https://github.com/anvil008/workcell` are one project, so both collapse to
   `github-com-anvil008-workcell`. `source` is `remote`.
3. **With no remote**, the key is `<toplevel basename>-<first 8 hex of the sha256 of the
resolved absolute toplevel>`, so two checkouts that merely share a directory name stay
   apart. `source` is `path`.
4. Either way the key is reduced to the character class `workcell-ws` already enforces
   for a key part — `[a-z0-9][a-z0-9-]*`, every other character written as a dash and
   runs collapsed. A wiki key and a workspace key obey one spelling rule, and neither can
   carry a path separator.
5. A namespace addressed with `--namespace` has no repository behind it: its key is the
   directory name and its `source` is `namespace`.

**Collisions are refused, not resolved.** `project.json` records the identity, every
later command re-resolves and compares, and a mismatch exits non-zero naming both the
recorded source and the resolved one. The comparison is exact, so re-spelling a
repository's own `origin` — ssh to https — is a mismatch even though both spellings key to
the same namespace; that is deliberate, because the alternative is guessing which of two
identities the store should now believe. Renaming or retiring a namespace is a human act,
like entering eval mode: a person edits `project.json`, or moves the namespace aside and
runs `init` again.

**Eval mode is refused.** A repository carrying `.workcell/eval-mode.json` neither
records into nor reads from a persistent namespace, so _every_ `--repo` subcommand
refuses it — reading included, not only the writes. The marker is read from the
repository `--repo` names, never from the store. That is what keeps a benchmark run from
contaminating — or being contaminated by — a real project's history.

## The namespace

```
~/.workcell/wiki/<project-key>/
├── project.json      the identity record
├── raw/<id>/         one immutable bundle per recorded run — write-once
├── patterns/<slug>.md one failure mode or strategy per page — append-only
├── index.md          the catalog, one row per pattern page
├── logs.md           the evolution log, one line per write
└── skill-impact.md   the accept/reject audit trail for skill-change proposals
```

`wiki.py init` creates all of it and is idempotent: a second run exits 0 and leaves every
existing file byte-identical. No subcommand deletes anything — there is no reset and no
rollback.

### `project.json`

```json
{
  "projectKey": "github-com-anvil008-workcell",
  "source": "remote",
  "derivedFrom": "git@github.com:anvil008/workcell.git",
  "createdAt": "2026-08-31T09:14:02Z"
}
```

`source` is `remote`, `path`, or `namespace`; `derivedFrom` is the origin URL, the
resolved toplevel, or the namespace path that produced the key.

### `raw/<id>/` — write once

```
raw/2026-08-27-build-wave-1/
├── manifest.json
└── files/integrator-handoff.json
```

```json
{
  "id": "2026-08-27-build-wave-1",
  "kind": "build-wave",
  "recordedAt": "2026-08-27T18:22:41Z",
  "summary": "wave 1 accepted after one re-run",
  "files": [{ "path": "files/integrator-handoff.json", "sha256": "9f2c…" }],
  "model": "claude-sonnet-5",
  "effort": "high"
}
```

Written by `wiki.py record --id <id> --kind <kind> --summary <text> --file <path> [--model <model>] [--effort <effort>]`, which
prints the id it wrote and may be given `--file` repeatedly. Optional `--model` and `--effort` flags record
the model string (e.g. `claude-sonnet-5`, `gemini-3.7-flash`) and reasoning effort level (e.g. `low`, `medium`, `high`)
in `manifest.json`. When omitted or not passed, `"model"` and `"effort"` are null or omitted, preserving full backward
compatibility with legacy manifests. Recording under an id that
already exists exits non-zero and changes nothing: a raw trace is the evidence every
pattern page cites, so it is written once and never rewritten. New evidence goes under a
new id.

A bundle is staged under `raw/.staging-*` and renamed into place only once its manifest is
written, so an interrupted `record` cannot leave a half-copied bundle that `check` would
later call mutated. A `.staging-*` directory left behind is a crashed write: `check` names
it, and it is the one thing in a namespace that is safe to delete by hand.

### `patterns/<slug>.md` — append only

```markdown
# Flaky sandbox lock

One failure mode or successful strategy of this project. Evidence accumulates below;
nothing already written here is rewritten to say something different.

## Evidence

- 2026-08-14 — `2026-08-14-build-wave-3` — The integrator timed out waiting on the sandbox lock.
- 2026-08-27 — `2026-08-27-build-wave-1` [claude-sonnet-5·high] — The same lock starved a second wave on a slower runner.
```

Written by `wiki.py pattern <slug> --evidence <raw-id> --note <prose> [--title <text>]`,
with `--evidence` repeatable. One dated line per call, in three fields separated by `—`:
the date, the cited raw ids (with optional bracketed attribution), and the prose.
When citing a raw bundle, `wiki.py pattern` inspects the bundle's `manifest.json`:
- If both `model` and `effort` are recorded: the citation is formatted with bracketed attribution using middle dot `·`: `<raw-id>` [<model>·<effort>] (e.g. `` `2026-08-27-build-wave-1` [claude-sonnet-5·high] ``).
- If only `model` is recorded (effort is null/omitted): the citation is formatted as `<raw-id>` [<model>] (e.g. `` `2026-08-27-build-wave-1` [claude-sonnet-5] ``).
- If `model` is omitted (legacy): the citation is formatted unbracketed as legacy `<raw-id>` (e.g. `` `2026-08-14-build-wave-3` ``).

Citations are read back out of
the second field alone, so a backtick in the prose cannot forge one; the prose of an
earlier call stays present verbatim. A page that turns out
to be wrong gains a new dated entry saying so — **it is never rewritten to say something
different**, because the value of the layer is the record of what was believed when, and
an edited page cannot be told apart from a page that was always right.

A cited raw id must already exist under `raw/`; `wiki.py` refuses a citation it cannot
resolve rather than writing a dangling one.

### `index.md` — the catalog

```markdown
| Pattern                                              | Occurrences | Last seen  |
| ---------------------------------------------------- | ----------: | ---------- |
| [flaky-sandbox-lock](patterns/flaky-sandbox-lock.md) |           2 | 2026-08-27 |
```

One row per pattern page: the slug, how many evidence entries it has accumulated, and the
date of the most recent. The catalog is _derived_ — `wiki.py` recomputes it from the
pages on every write, so it cannot drift silently, and `check` reports it when it has.

### `logs.md` — the evolution log

```markdown
- 2026-08-27T18:22:41Z record 2026-08-27-build-wave-1 (build-wave) — wave 1 accepted after one re-run
- 2026-08-27T18:22:43Z pattern flaky-sandbox-lock — 2026-08-27-build-wave-1 — The same lock starved a second wave.
```

Exactly one appended line per write, oldest first.

### `skill-impact.md` — the audit trail

v1 creates the file and documents the entry shape here; **nothing writes an entry yet**.
The proposer that would write one is out of scope until validation-gated skill updates
land. The shape it will take:

```markdown
- 2026-09-04 — `flaky-sandbox-lock` → proposed `skills/build` change "retry the sandbox
  lock once" — **rejected** — the evidence is one project's runner, not a shared failure
  mode. Decided by: @maintainer.
```

Accept or reject, the entry names the pattern page the proposal came from, the shared
skill it aimed at, the decision, the reason, and who decided.

## `wiki.py check` — what the gate proves

`check` exits 0 on a healthy namespace and non-zero naming every offender it found:

- a recorded file whose bytes no longer match the sha256 in its `manifest.json`, or a
  file present in a bundle that its manifest does not list — the write-once proof;
- a raw id `logs.md` records with no bundle under `raw/` — nothing here deletes, so a
  missing bundle was removed out of band, and the ledger is what catches one no page
  happens to cite;
- a `.staging-*` directory, the residue of an interrupted `record`;
- a raw bundle manifest or pattern line citation tag with unsanitized `model` or `effort` strings (containing newlines, tabs, or carriage returns) — maintaining backward compatibility for legacy records;
- a pattern page citing a raw id with no directory under `raw/`, or citing something that
  is not a raw id at all;
- a pattern page with no row in `index.md`, a row whose count or last-seen date disagrees
  with its page, or a row with no page.

Because the offenders are named, a failed check is a work item, not a puzzle.

What it does **not** prove: only the raw layer is hashed, so `check` cannot tell that a
pattern page's earlier prose was edited, and a deletion covered up by editing `logs.md`
takes the ledger with it. The never-rewritten rule is upheld by `wiki.py` being the only
writer, which is why an agent reaching a namespace with an editor tool is a contract
violation and not a shortcut.
