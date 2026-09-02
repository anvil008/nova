---
name: wiki
description: Consolidate what a project's finished runs taught into its own persistent wiki — a namespace outside the repository holding write-once raw traces, append-only pattern pages, and a catalog. Opt-in per project — no namespace means nothing is recorded and nothing is dispatched; invoke as `/workcell:wiki init` to opt the current repository in with one confirmed question.
---

# Wiki

Turn what a project's finished runs taught into a durable record of that project, kept in
a namespace outside the repository so it outlives every branch, worktree, and clone of it.

Invocation: `/workcell:wiki`
Prompting Reference: [`docs/models/claude-sonnet-5/prompting.md`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents, hold the human gates, run `git` / `jj` / `gh` for branch, merge, and issue-state operations, and read gate output and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator decides whether the project opted in, dispatches the one agent that
writes its namespace, and reads `wiki.py check` as the gate.

## Ordered Gates

Execution proceeds through four strict, ordered gates:
1. **project opt-in**: Verify whether the target repository has opted into persistent memory via `wiki.py status`.
2. **write-once trace**: Securely record immutable run traces, handoffs, and verification logs with unique IDs.
3. **append-only pattern**: Consolidate durable insights onto append-only topic pattern pages linked to trace evidence.
4. **catalog update**: Update catalog index and mechanically verify namespace integrity with `wiki.py check`.

## 1. Ask Whether the Project Opted In

```bash
python3 -B skills/wiki/scripts/wiki.py status --repo .
```

The answer is one JSON object carrying the resolved `projectKey` and `present`. The store
it looks in is `$WORKCELL_WIKI_HOME`, defaulting to `~/.workcell/wiki/`, one namespace per
project key; the key derivation is in
[`references/wiki-layout.md`](references/wiki-layout.md). A project
with no namespace means no record, no dispatch, and no tokens spent — `present: false` is
an ordinary answer, not a failure, and it ends this workflow unless the human opts in
right here. Opting a project in is a human act: a namespace exists only because a person
ran `wiki.py init --repo <path>` for it, or answered yes to the one question below, and
nothing else creates one.

### `init` — The Opt-in, Asked In-session

When the skill is invoked as `/workcell:wiki init`, or when `status` answers
`present: false` and a human is present to ask, put the opt-in to them as one question —
opt this project in, yes or no — naming the resolved `projectKey` and the namespace path
`status` printed, so they see exactly what would be created. On an explicit yes, run:

```bash
python3 -B skills/wiki/scripts/wiki.py init --repo .
```

then re-run `status` and continue. On no — or in a non-interactive run, where there is no
one to ask — the workflow still ends at `present: false`. The answered question is the
only shortcut; it is never a default, and no run creates a namespace unasked.

Two more answers end the workflow before any dispatch. A repository carrying
`.workcell/eval-mode.json` is refused by name, because a benchmark run neither records
into nor reads from a persistent namespace. A namespace whose `project.json` no longer
matches what the repository resolves to is refused naming both sources; that is a
collision for a human to settle, never something to work around.

## 2. Dispatch the Consolidation

Consolidation is exactly one `documenter` dispatch conforming to
[`anvil.agent-handoff/v1`](../../runtime/handoff.md), whose `ownership` is the resolved
namespace path and nothing else. One dispatch, because the layer's whole value is a
single coherent reading of the run; a fan-out would race on the same append-only pages.

Give the brief:

- the **namespace path** `status` printed, as its `ownership`;
- the **evidence** to record — handoff records, gate output, review findings, the
  integrator's verdict — as real paths the agent can copy;
- the **question**: what recurred, what worked, and what this project's runs say that a
  generic skill does not;
- the **boundaries** below, in full.

That agent writes only through `wiki.py` and never with an editor tool — never Write,
never Edit, never a shell redirect into a page. The CLI is what enforces write-once raw
bundles, append-only pattern pages, a derived catalog, and one log line per write; an
editor reaching past it removes the only thing that makes the layer trustworthy. The
artifact contract it writes to is [`references/wiki-layout.md`](references/wiki-layout.md).

Its three verbs:

```bash
python3 -B skills/wiki/scripts/wiki.py record --repo . --id <raw-id> --kind <kind> --summary "<one line>" --file <path> --file <path>
python3 -B skills/wiki/scripts/wiki.py pattern <slug> --repo . --evidence <raw-id> --note "<what this run showed>"
python3 -B skills/wiki/scripts/wiki.py check --repo .
```

## 3. Read the Gate

The completion gate is `wiki.py check` exiting zero, which re-hashes every recorded file
against its manifest, re-links every citation, and names each offender it finds. A
consolidation whose check does not exit zero is not done; send the named offenders back
to the same agent rather than repairing a namespace yourself.

## Standing Boundaries

The runtime agents — `specifier`, `builder`, `reviewer`, and `integrator` — are never
given the wiki, in either direction: they neither read a namespace nor write one. They
work against a sealed Definition of Done, and a page of remembered opinion reaching them
would quietly compete with it.

A project pattern never amends Workcell's shared `skills/`; it feeds a project-local
overlay in the target repository, while the shared skills keep changing through
evidence-backed pull requests gated by the eval tiers. The two paths differ in what they
are accountable to — one project's history, or every project's — and collapsing them lets
one project's habit silently bind another.

## Harness Limitations

Native context forks and workflows are omitted with notes in Claude Code; procedures execute sequentially within the primary session.
