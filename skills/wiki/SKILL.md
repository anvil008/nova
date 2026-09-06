---
name: wiki
description: Consolidate what a project's finished runs taught into its own persistent wiki — a namespace outside the repository holding write-once raw traces, append-only pattern pages, and a catalog. Opt-in per project — no namespace means nothing is recorded and nothing is dispatched; invoke as `/workcell:wiki init` to opt the current repository in with one confirmed question.
---

# Wiki

Turn what a project's finished runs taught into a durable record of that project, kept in
a namespace outside the repository so it outlives every branch, worktree, and clone of it.

The orchestrator owns scope, user decisions, dispatch, and final evaluation. Specialists author plans and source changes; independent evidence determines completion. Team size follows useful work and explicit user constraints. See [ADR 0029](../../docs/adr/0029-composable-workflows-and-native-research.md).

This orchestrator decides whether the project opted in, assigns scoped documenters to
maintain its namespace, and reads `wiki.py check` as the gate.

## 1. Ask whether the project opted in

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

### `init` — the opt-in, asked in-session

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

## 2. Dispatch the consolidation

The orchestrator sizes the `documenter` team and sends each assignment through [`agents/handoff.md`](../../agents/handoff.md) using `anvil.agent-handoff/v1`, with disjoint `ownership` inside the resolved namespace and nothing outside it. Serialize updates to shared append-only pages and the catalog so writers cannot race; independent evidence inspection and disjoint assignments may run in parallel. Keep final synthesis ownership explicit and run the namespace gate after all assigned writes.

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

## 3. Read the gate

The completion gate is `wiki.py check` exiting zero, which re-hashes every recorded file
against its manifest, re-links every citation, and names each offender it finds. A
consolidation whose check does not exit zero is not done; send the named offenders back
to the same agent rather than repairing a namespace yourself.

## Standing boundaries

The runtime agents — `specifier`, `builder`, `reviewer`, and `integrator` — are never
given the wiki, in either direction: they neither read a namespace nor write one. They
work against a sealed Definition of Done, and a page of remembered opinion reaching them
would quietly compete with it.

A project pattern never amends Workcell's shared `skills/`; it feeds a project-local
overlay in the target repository, while the shared skills keep changing through
evidence-backed pull requests gated by the eval tiers. The two paths differ in what they
are accountable to — one project's history, or every project's — and collapsing them lets
one repository's runner flakiness become everybody's rule.

## Offline demonstration

A namespace shipped with this skill, addressed directly with `--namespace`, so the
contract can be read without a store, a repository, or a network:

```bash
python3 -B skills/wiki/scripts/wiki.py status --namespace skills/wiki/examples/sample-namespace
python3 -B skills/wiki/scripts/wiki.py check --namespace skills/wiki/examples/sample-namespace
```

Both are read-only. `skills/wiki/examples/README.md` records how the sample was
generated, so it can be rebuilt from the CLI rather than hand-edited.
