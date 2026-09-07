# Review 01 — Workcell Dagr gaps against Herdr Dagr

Date: 2026-09-07. Scope: capability and reliability comparison, not a source-code transplant or a security audit. Reviewed upstream revision `52991f9a95a2b8c11518ed66f9530d938c1ba254`; Workcell is the current local working copy. Codex lifecycle/usage integration is being implemented separately in the same working copy.

## Main finding

Workcell has a usable run store and a small renderer, but the producer integration and operational navigation are incomplete. More visual styling cannot fill missing task facts. Keep Workcell's shared skills responsible for task meaning; adapters should report runtime facts and preserve their provenance. Do not rebuild the former mandatory orchestration pipeline.

Herdr also relies on a producer to maintain its run file. Its viewer consumes that file; its documented runtime connection adds location and activity information rather than authoring task truth. [Producer skill](https://github.com/aemrebarut/herdr-dagr/blob/52991f9a95a2b8c11518ed66f9530d938c1ba254/skills/dagr-producer/SKILL.md).

The inspected typed contract includes attempt models and liveness, but no token-usage fields. Automatic task token attribution is additional Workcell work, not an upstream feature we can assume exists. [Typed contract](https://github.com/aemrebarut/herdr-dagr/blob/52991f9a95a2b8c11518ed66f9530d938c1ba254/src/contract.rs).

## Recommended order

| Priority | Workcell gap | Concrete next change |
|---|---|---|
| Now | Runtime facts require manual CLI writes. | Codex hook adapter, stable session bindings, observed model/effort, source-identified usage records, deduplication, and honest session-level counters when task attribution is uncertain. This is the delegated implementation. |
| Next | Retry records exist, but only the current task occupies a graph row. | Expand attempts as `T1·a1`, `T1·a2`, showing outcome, model, time, evidence, and the recorded retry reason. Keep task identity stable. |
| Next | The terminal projects multiple dependencies onto one parent and puts remaining dependencies into potentially truncated text. | Give joins a distinct row treatment, display the blocking task IDs, and highlight direct inputs/outputs on selection. Milestone grouping must remain independent of dependency edges. |
| Next | The large detail box repeats information and grows with history. | A stable compact inspector for identity, current progress, model, and timing; a separate scrollable full-details view. Preserve selection by task/attempt ID during refresh. |
| Next | A working state can remain visible after the producer stops reporting. | Show last observed event age and last semantic progress age separately. Expose stopped/interrupted sessions without asserting task failure or success. Do not label ordinary silence as a crashed process. |
| Next | Empty or sparse runs give little explanation of missing data. | A diagnostic view showing resolved project/store, active/archive selection, adapter enabled state, session binding, last event, and which fields are unavailable. Explain each missing model/token value. |
| Later | Long runs have scrolling but no search, folding, or attention summary. | Search IDs/titles/agents; fold settled work without hiding blocked/failed counts; provide a short attention list. Add these when graph navigation, rather than data ingestion, becomes the bottleneck. |
| Later | Timestamp data exists but no operational summary does. | Elapsed attempt duration, in-progress/blocked counts, retry counts, and per-model reported token totals. Avoid an ETA until there is enough comparable evidence. |
| Later | Milestones are flat. | Add nested scopes only when actual multi-project runs need them. Keep ungrouped discovery tasks valid. |

Herdr provides attempt-level traces, explicit joins, derived readiness, compact details, and navigation for larger graphs. These are useful interaction references; Workcell can implement the relevant subset with its own contract. [README and navigation](https://github.com/aemrebarut/herdr-dagr/blob/52991f9a95a2b8c11518ed66f9530d938c1ba254/README.md).

## Reliability gaps to address alongside growth

- Add admission limits for document bytes, task/attempt/event counts, and oversized field values. Workcell currently reads and validates the full file on refresh. Keep errors actionable, and avoid freezing the interface on an unexpectedly large run.
- Persist terminal rendering checks for narrow widths, Unicode display cells, resize, graph scroll, and selection stability. The current automated Dagr tests cover state/storage/API behavior; terminal checks performed during development also need a repeatable home.
- Keep provider counters attributable. Cached input and reasoning may be subsets of other counters; do not add them into a synthetic grand total. Session usage should not be repeated under every task.
- Keep evidence claims distinct from validation receipts. Workcell's `--verified` is a producer assertion accompanied by a reference; the tool does not execute or independently prove that reference.
- Keep archives immutable. Delayed usage and lifecycle events need a documented disposition rather than reopening a finished run or contaminating the next run.

Upstream has explicit input-size limits and structured validation findings; those are useful robustness references. Its published contract also keeps runtime addresses separate from stable work identities. [Bounds implementation](https://github.com/aemrebarut/herdr-dagr/blob/52991f9a95a2b8c11518ed66f9530d938c1ba254/src/scale.rs), [contract](https://github.com/aemrebarut/herdr-dagr/blob/52991f9a95a2b8c11518ed66f9530d938c1ba254/CONTRACT.md).

## Deliberately defer

Do not add conditional future branches, a policy interpreter, an operator-message transport, pane interruption controls, recursive project configuration, or four evidence tiers solely for visual parity. The existing user conversation already carries decisions and authorization. If pane controls are later requested, define their actual transport and authority before exposing buttons.

Herdr's message controls are explicit addressed messages with journaled delivery, not a hidden scheduler. Its future branches require declared policy data. Those semantics would be substantial new scope in Workcell. [Contract: messages and policies](https://github.com/aemrebarut/herdr-dagr/blob/52991f9a95a2b8c11518ed66f9530d938c1ba254/CONTRACT.md).

## Coverage

Inspected upstream README, producer skill, contract, and selected typed model, statistics, validation, and size-bound sources. Compared with Workcell's schema/CLI, terminal renderer, browser renderer, and Dagr tests. No upstream executable was installed or exercised, and no upstream implementation was copied. Findings above are capability gaps and design recommendations, not a claim that every upstream behavior is bug-free. Integration verification belongs in the companion build report.
