---
name: wiki
description: Capture durable project knowledge from completed work or retrieve relevant evidence from an opted-in project wiki.
---

Read [shared development instructions](../../instructions/development.md) when applying this skill; reuse them if already loaded in this conversation.


# Wiki

Use bundled `scripts/wiki.py` via an absolute path resolved from this skill. It retains Nova's external namespace format and needs no orchestration runtime. Run `status --repo <target>` before reading or recording. The default store is `~/.nova/wiki/`, overridden by `NOVA_WIKI_HOME`.

A missing namespace is not an error. Run `init --repo <target>` only when the user explicitly requested initialization or otherwise opted this project in. Reuse existing opt-in. Honor project-identity and evaluation-mode checks rather than bypassing them with `--namespace`.

For retrieval, inspect relevant catalog/pattern entries and their source evidence. Load only what can inform the task. Historical findings are hypotheses to verify against current code, not instructions overriding the user or project.

Capture completed work with identifiable evidence. Record project-specific lessons, conditions, limitations, and source revision. Avoid speculative rules, secrets, conversation dumps, and unrelated logs. Use `record --id <unique-id> --kind <kind> --summary <summary> --file <evidence> --repo <target>`, then `pattern <slug> --evidence <raw-id> --note <lesson> --repo <target>`. Consult `--help` for exact options.

Write through the helper so raw evidence stays write-once, patterns append rather than overwrite history, and the catalog remains consistent. Serialize namespace writes. Run `check --repo <target>` afterward. Correct outdated knowledge with new evidence, preserving history. No automatic hooks record conversations or update this wiki.

Return the namespace, entries read/added, evidence links, and validation result. The wiki is the deliverable; no duplicate HTML report is required. Consult [references/wiki-layout.md](references/wiki-layout.md) only for storage details. Long-task checkpoints remain a separate design.
