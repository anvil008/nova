---
name: si-project
description: Project-scoped adaptation and self-improvement: record task traces, extract persistent patterns into an in-repository store, synthesize candidate project rules or local skills, and request human-in-the-loop approval before applying.
---

Read [shared development instructions](../../instructions/development.md) when applying this skill; reuse them if already loaded in this conversation.


# Self-improvement (project)

Use bundled `scripts/si.py` via an absolute path resolved from this skill. It manages the in-repository self-improvement store at `<primary-root>/.nova/si/` and needs no orchestration runtime.

Run `status --repo <target>` before reading or recording. A missing store is not an error: run `init --repo <target>` only when the user explicitly requests initialization or otherwise opts this project in.

## Workflow

1. **Check opt-in**: Run `python3 <skill-dir>/scripts/si.py status --repo .`. If not present, ask the user if they wish to initialize project self-improvement. Honor evaluation-mode checks rather than attempting to bypass them.
2. **Retrieve project patterns**: Inspect relevant pattern entries in `<primary-root>/.nova/si/patterns/` and their source evidence. Load only what can inform the immediate task. Historical findings are hypotheses to verify against current code, not immutable commands.
3. **Record task traces**: Capture completed work with identifiable evidence. Record project-specific lessons, conditions, limitations, and source revisions using:
   ```bash
   python3 <skill-dir>/scripts/si.py record --repo . --id <unique-id> --kind <kind> --summary <summary> --file <evidence> [--model <model>] [--effort <effort>]
   ```
4. **Extract recurring patterns**: Update or create pattern pages:
   ```bash
   python3 <skill-dir>/scripts/si.py pattern <slug> --evidence <raw-id> --note <lesson> --repo . [--title <title>]
   ```
5. **Formulate improvement proposals**: Analyze recurring patterns to synthesize concrete project rules or local skills:
   ```bash
   python3 <skill-dir>/scripts/si.py propose --repo . --pattern <slug> --title <title> --target <agents-md|skill>
   ```
6. **Obtain human confirmation**: Present the candidate proposal to the user. Never apply project rules or create new skills without interactive human approval. When approved, run:
   ```bash
   python3 <skill-dir>/scripts/si.py propose --repo . --id <proposal-id> --apply
   ```
7. **Validate integrity**: Run `python3 <skill-dir>/scripts/si.py check --repo .` to verify hashes, ledger consistency, and pattern citations.

Write exclusively through `si.py` so raw evidence stays write-once, patterns append rather than overwrite history, and proposals maintain an audit trail. Consult [references/si-layout.md](references/si-layout.md) for detailed storage contracts.
