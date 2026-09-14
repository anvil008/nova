# Self-improvement layout — the in-repository artifact contract

The shapes `skills/si-project/scripts/si.py` writes and the invariants it enforces.
The agent consolidating a project's runs reads this file; the operator reads
[`SKILL.md`](../SKILL.md).

Every field the CLI is given — a kind, a summary, a note, a title — is folded to one line
before it is written, so no argument can smuggle a second line into an append-only file
and have it read back as an entry nothing recorded.

Nothing outside `si.py` writes the store. Every rule below is enforced by the CLI, so
an editor tool reaching into `.nova/si/` does not "save a step" — it removes the only
thing keeping the layer trustworthy.

## Where the store lives

The primary store lives directly in the repository at `<primary-root>/.nova/si/`.
The `.nova/` directory is gitignored and excluded from version-controlled deliverables and pull requests.
It outlives branches and workspaces of the project without polluting repository commits.

`--repo <path>` names the target repository or workspace.
`si.py` resolves the **primary toplevel root** across secondary workspaces and worktrees:
1. For Jujutsu workspaces: resolves the primary workspace via `.jj/repo` (if pointer file, resolves to primary root).
2. For Git worktrees: resolves the primary worktree from `git worktree list --porcelain`.
3. Fallback to repository root (`.git`).

`--store <path>` or the `NOVA_SI_STORE` environment variable allows an explicit store path override,
primarily used in hermetic testing.

## Projects registry

Whenever `si.py init` or `si.py register` runs, the primary repository root is registered in
`~/.nova/known_projects.json` (overridden by `NOVA_PROJECTS_REGISTRY`).
This registry tracks local repositories for cross-project pattern aggregation by `si-global`.
A missing registry is empty; an unreadable or wrongly shaped one (anything other than a list of path
strings or an object whose `projects` is a list of path strings) is refused and left untouched.

```json
{
  "projects": [
    "/home/anvil/repos/nova"
  ]
}
```

## Eval mode is refused

A repository carrying `.nova/eval-mode.json` neither records into nor reads from a persistent
store — every `--repo` subcommand refuses it, including `register`, and a marker in a secondary
workspace or worktree counts too. The only exception is `resolve-root`, which reads no store and
only prints the primary root. That is what keeps an evaluation run from
contaminating — or being contaminated by — a real project's self-improvement history.

## The store layout

```
<primary-root>/.nova/si/
├── project.json          the identity record
├── raw/<id>/             one immutable bundle per recorded run — write-once
├── patterns/<slug>.md    one failure mode or strategy per page — append-only
├── proposals/<id>.json   structured proposals for project rules or skills
├── index.md              the catalog, one row per pattern page
├── logs.md               the evolution log, one line per write
└── skill-impact.md       the accept/reject audit trail for skill-change proposals
```

`si.py init` creates all of it and is idempotent: a second run exits 0 and leaves every
existing file byte-identical. No subcommand deletes anything.

### `project.json`

```json
{
  "primaryRoot": "/home/anvil/repos/nova",
  "createdAt": "2026-09-13T14:00:00Z"
}
```

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

Written by `si.py record --id <id> --kind <kind> --summary <text> --file <path> [--model <model>] [--effort <effort>]`.
Optional `--model` and `--effort` flags record model attribution.
Recording under an ID that already exists exits non-zero: a raw trace is the evidence pattern pages cite,
so it is written once and never overwritten.
Evidence files are stored by basename under `files/`, so two `--file` paths with the same basename are
refused before anything is written.

A bundle is staged under `raw/.staging-*` and renamed into place atomically only once its manifest is written.
A left-behind `.staging-*` directory represents a crashed write and is reported by `check`.

### `patterns/<slug>.md` — append only

```markdown
# Flaky sandbox lock

One failure mode or successful strategy of this project. Evidence accumulates below;
nothing already written here is rewritten to say something different.

## Evidence

- 2026-08-14 — `2026-08-14-build-wave-3` — The integrator timed out waiting on the sandbox lock.
- 2026-08-27 — `2026-08-27-build-wave-1` [claude-sonnet-5·high] — The same lock starved a second wave on a slower runner.
```

Written by `si.py pattern <slug> --evidence <raw-id> --note <prose> [--title <text>]`.
One dated line per call in three fields separated by `—`: date, cited raw IDs (with optional bracketed attribution), and prose.
A cited raw ID must already exist under `raw/`.

### `proposals/<id>.json` — improvement proposals

```json
{
  "id": "2026-09-13-flaky-sandbox-lock",
  "createdAt": "2026-09-13T14:10:00Z",
  "target": "agents-md",
  "targetFile": "AGENTS.md",
  "title": "Retry sandbox lock on contention",
  "patterns": ["flaky-sandbox-lock"],
  "proposal": "When acquiring the test runner sandbox lock, retry once after a 2-second backoff before failing.",
  "applied": true,
  "appliedAt": "2026-09-13T14:12:00Z"
}
```

Written by `si.py propose`.
A proposal file is never overwritten: an automatic `<date>-<pattern>` ID that already exists gets a
`-2`, `-3`, … suffix, and an explicit `--id` that already exists is refused. An explicit `--id`
must match `[a-z0-9][a-z0-9._-]*`, the raw trace ID pattern, so it cannot name a path; `--apply` also accepts an older
proposal's ID if it is a single path component that does not start with `.` and has no control characters. `--skill-name` (and a
stored `skillName`) must be such a component too. The title is folded to one line, and so is the rule
text of an `agents-md` proposal; a `skill` proposal's text is the whole `SKILL.md` and is kept verbatim.
Synthesizes candidate project rules (for `AGENTS.md`) or local project skills (`.nova/skills/<name>/SKILL.md`).
Requires interactive human approval before applying (`--apply`).

### `index.md` — the catalog

```markdown
# Pattern index

One row per pattern page.

| Pattern | Occurrences | Last seen |
| --- | ---: | --- |
| [flaky-sandbox-lock](patterns/flaky-sandbox-lock.md) | 2 | 2026-08-27 |
```

Recomputed on every write to reflect current pattern files.

### `logs.md` — the evolution log

```markdown
# Evolution log

One line per write to this store, oldest first. Appended by `si.py`; never edited.

- 2026-08-27T18:22:41Z record 2026-08-27-build-wave-1 (build-wave) — wave 1 accepted after one re-run
- 2026-08-27T18:22:43Z pattern flaky-sandbox-lock — 2026-08-27-build-wave-1 — The same lock starved a second wave.
- 2026-09-13T14:10:00Z propose 2026-09-13-flaky-sandbox-lock — Retry sandbox lock on contention
- 2026-09-13T14:12:00Z apply 2026-09-13-flaky-sandbox-lock to AGENTS.md
```

### `skill-impact.md` — the audit trail

```markdown
# Skill impact

The accept/reject audit trail for skill-change proposals.

- 2026-09-13 — applied proposal 2026-09-13-flaky-sandbox-lock to AGENTS.md: Retry sandbox lock on contention
```

## `si.py check` — what the gate proves

`check` exits 0 on a healthy store and non-zero naming every offender found:
- a recorded file whose bytes no longer match the sha256 in its `manifest.json`;
- a raw ID `logs.md` records with no bundle under `raw/`;
- a `.staging-*` directory left behind by an interrupted write;
- a raw bundle manifest or pattern line citation tag with unsanitized `model` or `effort` strings;
- a pattern page citing a raw ID with no directory under `raw/`;
- a pattern page with no row in `index.md`, or a count / last-seen date mismatch.
