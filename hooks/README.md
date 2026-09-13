# Nova hooks

## Claude workspace hooks

`workspace.py` handles native WorktreeCreate/WorktreeRemove events in Claude packages. It creates JJ workspaces or Git worktrees in the primary checkout’s `.workspaces/<task>/`. Cleanup retains JJ workspaces and any Git worktree with modified, untracked, or ignored files. Codex/Agy placement remains instruction-driven. See [harness comparison](../instructions/harnesses.md) for the full contract and app limitations.

## Optional post-edit hooks

Plugin sources; formatting/linting remains disabled until explicitly configured. `post-edit.py` runs a project's explicitly configured single-file format and lint commands in order. It has no model calls, transcript capture, wiki writes, test seals, builder identities, or unbounded Stop continuation loop. Final tests, review, and delivery remain workflow responsibilities.

Keep the shared runner once. The JSON adapters differ only in native configuration shape and tool names. During a separately requested setup, replace `/ABSOLUTE/PATH/` entries with correctly shell-quoted paths, select the target root and existing tools in a project config, review the commands, and enable that config. Merge native event entries with existing configuration rather than replacing it. Commands are trusted executable configuration: enabling a formatter authorizes its scoped edits; the runner is not a security sandbox.

The example config is disabled. It demonstrates formatting followed by linting for Python, and ShellCheck for shell files. Replace these with the project's actual commands. Do not download tools from hooks. Commands use argv arrays, require a separate `{file}` argument, and run without a shell. Paths with spaces or shell metacharacters stay literal. Only existing edited files within the configured root are selected; `.git`, `.jj`, outside-root symlinks, and configured exclusions are skipped. Add protected tests or generated paths to exclusions when applicable. No shell-command parsing attempts to discover shell-written files; final checks cover those edits.

Codex apply_patch edits support multiple Add/Update/Move paths. Claude editor paths and Agy TargetFile paths are supported. Ambiguous relative multi-workspace paths are skipped. The hook is advisory: bounded diagnostics, per-command timeouts, and no success output for clean Claude/Codex checks. Missing tools and failures are reported, not silently called successful. Native hook timeout bounds the complete invocation; keep matching commands few and fast. Formatters and their subprocesses must themselves stay scoped and bounded.

Claude and Codex receive PostToolUse additionalContext. Agy's documented PostToolUse response is `{}`; diagnostics go to stderr for hook logs, with no claim they enter model context. Consult those logs or run lint directly on Agy. No hook blocks completion or claims to enforce acceptance. Automatic post-edit formatting can race with overlapping writers; keep write ownership separate.

Native configuration references: [Codex hooks](https://learn.chatgpt.com/docs/hooks), [Claude hooks](https://code.claude.com/docs/en/hooks), [Agy hooks](https://www.antigravity.google/docs/hooks/). The packager wires Codex/Claude native hooks to the bundled runner; NOVA_HOOK_CONFIG selects the explicit configuration. Without it the runner exits quietly. Agy retains an explicit setup adapter. See ../instructions/install.md and the migration report for native trial coverage.

## Scout read routing

`read-routing.py` runs on packaged PreToolUse read/shell events. It uses local bounded file inspection, never invokes a model or writes Flow state, and redirects large reads to the native scout. Claude/Codex use `hookSpecificOutput.permissionDecision: deny`; Agy uses `decision: deny`. Nonmatches emit `{}` with no decision or permission override, never an allow decision. Agy CLI 1.0.16+ documents handling empty pre-tool decisions; the native install check used 1.2.1. Agy runs hook commands relative to its root hooks.json, so the bundle remains relocatable. See [thresholds, supported syntax, scout handoff, and fallback](../instructions/read-routing.md).

## Codex run lifecycle and usage

Automatic Nova Flow tracking is disabled in packaged Codex, Claude, and Agy plugins for now. Builds include the adapter source for future use, but register no tracking hooks. Formatter/linter hooks remain independently opt-in. The sections below describe the retained adapters when explicitly wired by a user.

The adapter locates the nearest Git/JJ project root from the event cwd (otherwise cwd), then creates/resumes `.nova/run.json`. It registers stable hashed agent IDs while retaining the native session ID, and uses actual parent/child event identities. It does not capture prompts, messages, or tool results. A stop marks only the agent idle; it cannot complete a task. Repeated unchanged events do not append events. Terminal runs are untouched. Events belonging to archived sessions are ignored unless the session is explicitly attached to the new active run. After `nova-flow init "Next task"`, use `nova-flow session attach NATIVE_SESSION_ID --archive OLD_RUN_ID` to continue the same conversation. This carries the telemetry cursor/baseline, never historical usage or task bindings. This prevents delayed hooks from replaying an old conversation into unrelated work.

Model comes from Codex's hook payload for the root agent, or from that session's transcript turn context. Parent model data is never applied to children. Effort and token usage come from matching-session JSONL `turn_context` and cumulative `token_count` records. Codex documents transcript format as unstable: unsupported records produce a telemetry warning, missing fields stay unknown, and future Codex changes may require an adapter update. Only appended complete lines are processed. Counters are differenced and deduplicated; cache/reasoning are breakdowns, not extra tokens to add to input/output. Decreasing counters are reported and skipped rather than estimated.

Usage initially stays on the agent as **session-only**. To associate future work with a started attempt:

```bash
nova-flow task set T1 working
nova-flow session bind NATIVE_SESSION_ID --task T1
# Later, detach:
nova-flow session bind NATIVE_SESSION_ID --task -
```

Only usage intervals with a known prior baseline and a turn context beginning after binding go to that attempt. Mid-turn bindings, pre-existing conversation usage, and late data after task completion remain session-only. Starting a new attempt requires a fresh binding. Hook-driven usage therefore updates at hook boundaries; it is not a live stream during a long model request. Claude/Agy lifecycle and token adapters are not yet implemented.

Native payload contract: [Codex hooks](https://learn.chatgpt.com/docs/hooks). Payload includes session_id, cwd, model, transcript_path; subagent events use the parent's session_id and child's agent_id. SubagentStop supplies agent_transcript_path. Hooks do not document token counts or effort directly.

A temporary current-session bridge may call the adapter with `TranscriptPoll` while waiting for a Codex restart. This only consumes available transcript metadata and preserves the reported agent state; it is not a native lifecycle event or process-health observation. It requires an existing active run.

## Retained native tracking adapters

Bootstrap does not register tracking hooks. For explicit custom hook setup, Codex retains its transcript adapter. The Claude adapter supports SessionStart/UserPromptSubmit/tool events, child sessions, Stop, and SessionEnd. The Agy adapter supports PreInvocation, PostInvocation, PostToolUse, and Stop using its camelCase conversationId/workspacePaths payload. Its first invocation registers the session; opening an empty prompt does not yet emit that event. Agy Stop records idle, never terminal closure. Claude SessionEnd can close a participant and trigger archival after all work and participants settle.

With custom tracking hooks explicitly configured, launches need no `track` wrapper for registration. Agy/Claude token extraction remains separate; these adapters record only observed lifecycle/model fields. Agy's documented hook contract does not supply token counters or a session-close event. Use the optional launcher when process-exit detection is needed. Multiple mounted Agy directories must resolve to one repository or routing is rejected with a diagnostic.

Agy hook commands reference bootstrap's stable bundle path; rebuilding at a new prefix regenerates those paths. Native installation leaves unrelated global hooks unchanged. Start fresh harness sessions after installation to reload discovery.

Sources: [Claude hooks](https://code.claude.com/docs/en/hooks), [Agy hooks and payloads](https://antigravity.google/docs/hooks/), [Agy plugin layout](https://antigravity.google/docs/cli/plugins/).

`integration.py` supplies a one-shot parent Stop reminder after SubagentStop in Codex/Claude. It never merges, inspects transcripts, or treats its marker as integration evidence. See the harness comparison for boundaries. Git workspace cleanup requires HEAD ancestry in local trunk as well as a clean checkout.
