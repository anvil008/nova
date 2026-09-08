# Build 04 — Codex lifecycle and usage tracking

Nova's Codex plugin now bundles lifecycle tracking hooks. They create or resume project-local `.nova/run.json`, register native session identities, read matching-session model/effort and token telemetry, and preserve task outcomes when execution stops.

## Behavior

- SessionStart, UserPromptSubmit, PostToolUse, SubagentStart, SubagentStop, Stop, and Interrupt are connected by the generated Codex hook configuration.
- Task meaning remains agent-authored. The adapter does not infer milestones, success, or dependencies from transcripts.
- Task usage requires an explicit session-to-attempt binding and a subsequent complete turn boundary with known counter baselines. Other usage stays on the session and is labeled session-only in both views.
- Repeated cumulative counters do not add usage twice. Sparse counter fields retain prior baselines. A new counter with no baseline cannot be charged to the current task.
- Parent event model/transcript data is not used for a child. Transcript identity must match the registered session.
- Archived session events cannot create a replacement run. An explicit `session attach SESSION --archive RUN` supports deliberate reuse of the same conversation while retaining only identity and telemetry cursor/baseline, not old tasks or usage records.

See [hook setup and limits](../../hooks/README.md) and [CLI usage](../../tools/README.md).

## Verification

The delegated implementation passed all 50 repository tests, including six adapter tests. The main agent independently ran `python3 -m unittest discover -s tests`: all 50 passed. Cases cover nested project roots, resumption, deduplication, stopped-but-unfinished work, child identity separation, partial transcript lines, sparse counters, archive late events, and explicit reattachment. The implementer also rebuilt plugin bundles and passed the Codex plugin validator.

The main agent then invoked the adapter with the real current Codex session identity and transcript path. It read model `gpt-6-astra`, effort `medium`, and 412 usage records with no telemetry warning. Historical counts remained session-only: zero task-attributed usage records were created. This was a manual adapter invocation with real metadata, not proof that installed native hooks fired.

The restarted LAN viewer displayed those session counters and scope labels; browser inspection reported no JavaScript errors. No prompt or tool-result content was emitted by the metadata check or copied into run state.

## Limits and delivery

Changes remain local; personal plugin installations were not changed. Install the rebuilt Codex plugin and restart Codex to enable its hooks. Native installed-hook execution has not been exercised in this change. Codex transcript format is documented as unstable; the adapter may need changes when that format changes. Collection occurs at hook boundaries, not continuously during a model request. Claude and Agy lifecycle/usage adapters are not implemented.

The companion [gap review](review01-20260907-herdr-dagr-gaps.md) prioritizes the remaining renderer and diagnostics work. No upstream Herdr implementation was copied.
