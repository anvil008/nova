# Task-file routing to native implementers

Nova routes recognized task-file edits to the native implementer so the parent can plan, observe, verify, review, and integrate. It covers code, tests, documentation, configuration, generated source, and file-backed reports. The hook supplies guidance only: it never starts a worker, creates parallel work, or decides product behavior.

## Parent workflow

The parent assigns one coherent writing task with a source base, owned paths, expected behavior, acceptance checks, and handoff evidence. It can run reads, builds, tests, and version-control integration; incidental cache and build output is outside task authorship. It schedules writers concurrently only when the harness supports it and all ownership is disjoint, including fixtures, generated files, lockfiles, docs, and output directories. Coupled work is serialized and the same implementer handles scoped repairs.

The parent starts the native implementer. The hook cannot do that. An unavailable implementer is reported to the user; the parent needs an explicit user exception before it authors a task file directly.

## What the hook recognizes

`write-routing.py --harness codex|claude|agy` handles packaged `PreToolUse` events. Agy matches `write`, `write_file`, `write_to_file`, `replace`, `replace_file`, `replace_file_content`, `multi_replace_file_content`, and `run_command`; Claude and Codex match `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, `apply_patch`, `Bash`, `exec_command`, and `shell_command`. A recognized authored edit is denied with a compact implementer handoff.

Claude permits ordinary native writes only when its event has an `agent_id` and `agent_type: implementer`. Agy and Codex do not provide safe per-helper identity on those tool events, so the implementer uses the absolute runner path supplied in the routing guidance:

```sh
python3 '<absolute bundle path>/tools/nova-write' -- COMMAND [ARGS...]
```

For example, an implementer can write one assigned file without a shell:

```sh
python3 '<absolute bundle path>/tools/nova-write' -- python3 -c 'from pathlib import Path; Path("/repo/docs/assigned.md").write_text("Updated text\\n")'
```

The runner passes argv directly, without an implicit shell. Native sandbox and permission rules still apply. Its exemption is limited to one complete runner invocation; shell chains are still assessed. Only the assigned implementer uses it, never the parent.

## Boundaries and override

This is cooperative routing, not a security boundary. Unknown command shapes, arbitrary scripts, and shell-written files are not universally intercepted. Errors return a diagnostic without a routing decision; the hook keeps no shared state. `NOVA_WRITE_ROUTING=off` is an explicit user override only. It does not create a helper, relax native permissions, or change the requirement to verify and review work.

Validation covers local hook and package behavior. It does not establish a live model trial, universal interception, or token savings.

Native contracts: [Agy hooks](https://antigravity.google/docs/hooks/), [Claude hooks](https://code.claude.com/docs/en/hooks), and [Codex hooks](https://learn.chatgpt.com/docs/hooks). Agy/Codex tool events do not safely identify the calling helper; do not infer it from a shared session, transcript, or timing.
