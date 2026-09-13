# Native writer routing

## Status

Accepted.

## Context

The parent agent was expected to decide when to use an implementer, so it could author task files itself. That concentrated implementation context in the parent and made delegation inconsistent. A hook cannot start native subagents or safely schedule parallel work. Codex and Agy PreToolUse payloads also lack safe per-helper identity, so blocking all parent writes would block their implementers too.

## Decision

The parent plans, observes, verifies, reviews, and integrates. Native implementers author task files, including code, tests, documentation, configuration, generated source, and file-backed reports. The parent supplies owned paths and acceptance checks, schedules only independent writers with disjoint ownership, serializes coupled work, and reuses an implementer for scoped repairs.

The packaged PreToolUse hook cooperatively redirects recognized authored edits to that workflow. It never starts a worker. Claude permits ordinary writes only when the event has an `agent_id` and `agent_type: implementer`; Codex and Agy implementers use the hook-supplied absolute `nova-write` argv runner. The runner remains subject to native permissions. `NOVA_WRITE_ROUTING=off` is an explicit user override.

## Consequences

Task-file authorship moves out of the parent context, but the parent still runs reads, checks, builds, and version-control integration; incidental command output is outside task authorship. The routing is not a security boundary: arbitrary scripts and unknown shell shapes are not universally intercepted, and errors return diagnostics without a routing decision. If an implementer is unavailable, the parent reports that limitation and needs a user exception before directly authoring a task file. This design does not claim a live model trial or token savings.
