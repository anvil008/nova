# Workcell Dagr run tracking

## Status

Accepted on 2026-09-07 for an independent Workcell implementation. This does not adopt Herdr Dagr's schema, binary, producer skill, or scheduling semantics.

## Context

The shared-skill workflow needs a live view of milestones, tasks, phases, and actual agent assignments without reinstating the old orchestration runtime. Users also need completed runs to remain inspectable.

## Decision

Ship a self-contained Python command named workcell-dagr in tools/ and every native plugin. Bootstrap installs a receipt-owned executable. Use a Workcell-specific schema with the marker workcell_dagr: 1, one current run.json per store, and terminal snapshots under archive/<run-id>/run.json.

Record milestones, dependency-linked tasks, attempts, evidence, workflow phases, and parent/subagent activity. Phases and roles are open descriptive values. The main conversation supplies semantic updates; no process scheduling, inferred completion, or model/tool execution occurs in the tracker. CLI writers serialize updates with a file lock and atomically replace validated state. Archived runs are not mutated by the CLI.

Provide terminal snapshots/watch mode and a read-only browser viewer. The browser reads validated JSON and renders it as text and SVG, with archive selection. Serve localhost by default; LAN binding is explicit. Markdown specs, plans, reports, and resumption notes remain the durable narrative, referenced from the run along with tested source revisions.

## Consequences

The tool works independently of Herdr and any specific coding harness, using Python 3.11+ on Linux/macOS. It carries no third-party runtime dependencies. JSON history is a local artifact; filesystem owners can still alter it, and references are not copied into an archive. Evidence levels are explicit producer assertions backed by references, not claims that the tracker executed checks. Runtime telemetry, automatic liveness detection, operator messaging, and Windows locking support are outside this version.
