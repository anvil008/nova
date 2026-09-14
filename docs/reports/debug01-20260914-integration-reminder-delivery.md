# Debug 01 — Integration reminder fired while background children were still running

Date: 2026-09-14. Scope: `hooks/integration.py` (Claude/Codex `handle` path), `scripts/package.py`, their
tests, and the three places that document the hook. Source state: working copy `ztyqltvm` / `5d4f84d4030b` on bookmark
`fix/integration-reminder-delivery`, on top of local `main` at `5787619`. No JJ/Git mutations were run
by this task; the parent commits.

## Symptom

The parent received the integration reminder on a Stop that happened while a delegated background child
was still working, and again after each of that child's later intermediate stops. The reminder is
supposed to arrive once per child result, after the result is available to integrate.

## Evidence

Parent transcript `~/.claude/projects/-home-anvil-repos-nova/6bcaa1ea-1aa5-42b6-af56-e68c9ddaec3c.jsonl`;
markers in `~/.cache/nova/integration/`.

| Time (UTC) | Observation |
|---|---|
| 17:18:49.242 | Child `a75c7ca640fa1d12b` ends its turn |
| 17:18:49.331 | `<task-notification>` for that child written into the parent transcript |
| 17:20:46 | Parent reminder — correct: the result had been delivered |
| 17:30:40 | Child `a127173d6ba1e10bc` launched (background) |
| 17:30:42 | Reminder fires while that child is still running — wrong |
| ~17:33:20 | Reminder fires again; session marker re-created 17:33:15 with no delivered result — wrong |
| 17:37:23 | First `<task-notification>` (`status: completed`) for `a127173d6ba1e10bc` |
| 17:39:25 | A second notification for the same child after a `SendMessage` resume |

The transcript itself documents the mechanism: the notification body carries the note that "a
task-notification fires each time this agent stops with no live background children of its own", and the
same task id may notify more than once.

## Root cause

`SubagentStop` is not a completion event. Claude Code raises it every time a subagent ends a turn,
including the intermediate turns of a still-running background agent. The old `handle` armed an empty
marker file on every non-read-only `SubagentStop` and blocked the next parent `Stop`, so the reminder
tracked child *turns* rather than child *results*. Re-arming also meant a child that stopped twice
produced two reminders even though nothing new had reached the parent.

## Fix

The marker (still `cache / sha256(session_id)`, one per session) now holds JSON state instead of being
an empty file:

```json
{"legacy": false, "pending": {"<agent_id>": true}, "consumed": {"<agent_id>": "<delivery ts>"}}
```

Marker writes go to a sibling temp file and are `os.replace`d onto the marker, so a concurrent hook
invocation cannot read a half-written file.

- **SubagentStop** (non-read-only, unchanged eligibility): under `--harness claude`, with a non-empty
  `agent_id` and `transcript_path`, the child id is added to `pending`; `consumed` is left alone. Every
  other harness marks the state `legacy`. `SubagentStop` never blocks.
- **Stop** with `pending` ids scans the parent transcript at `transcript_path` line by line (substring
  pre-check on the id, then `json.loads`; malformed lines are skipped) for a delivery entry newer than
  `consumed[agent_id]`. A delivery is a `"type": "user"` line that either contains
  `<task-notification>` with `<task-id>AGENT_ID</task-id>` (background child; any `<status>` counts), or
  carries a top-level `toolUseResult` dict whose `agentId` matches and whose `status` is not
  `async_launched` (foreground Agent tool result; the launch acknowledgement is explicitly not a
  delivery).
  - At least one delivered: those ids move from `pending` to `consumed` with the newest delivery
    timestamp, the marker is written back, and the hook blocks once with the unchanged `REMINDER` —
    unless `stop_hook_active`, in which case consumption is still recorded and `{}` returned.
  - None delivered: the marker is untouched and `{}` returned, so a running child never reminds.
- **SessionEnd** deletes the marker, as before.

Keeping `consumed` after the reminder is what stops a bare re-arm (same child stops again with no new
result) from reminding a second time; a genuinely new delivery for that id — for example after a resume —
has a newer timestamp and does remind again. Timestamps are compared as ISO strings.

### Why the harness, not the payload fields, selects the gate

Codex `SubagentStop` supplies the same `agent_id`, `agent_transcript_path`, and `transcript_path` fields
(`hooks/README.md` "Native payload contract"; the fixture in `tests/test_codex_tracking.py`), but a Codex
rollout transcript never contains a `task-notification` or an `agentId` tool result. Discriminating on
field presence would therefore have silenced the Codex reminder permanently. `handle` now takes an
explicit `harness` argument (default `'codex'`) that the CLI passes through from `--harness`, and only
`'claude'` records pending ids. `scripts/package.py` appends `--harness {harness}` to the packaged
`SubagentStop`/`Stop`/`SessionEnd` integration commands, matching the read-routing and write-routing
pattern; `tests/test_packages.py` asserts that each packaged Claude adapter command ends with
`--harness claude` and each Codex one with `--harness codex`.

### Fallbacks (fail open to the old behaviour)

- Any harness other than Claude — Codex today — sets `legacy`, and `Stop` then behaves exactly as
  before: delete the marker, block once unless `stop_hook_active`. A Claude payload missing `agent_id`
  does the same.
- `transcript_path` absent or empty on `Stop`, or the transcript unreadable (`OSError`), takes the same
  legacy path rather than silently suppressing the reminder.
- A marker left by an older Nova version (empty file, not JSON) is read as `legacy`, so an in-flight
  session upgrading Nova still gets its pending reminder.

The module stays stdlib-only; `read_only_agent`, `handle_agy`, the CLI, and the `REMINDER` text are
unchanged.

## Tests

`tests/test_integration_hooks.py` keeps the three existing `IntegrationHooks` cases unmodified — they
send no `agent_id`, so they exercise the legacy path and still pass. A new `DeliveryGatedReminder` class
drives `hook.handle` against a temporary transcript JSONL:

| Test | Covers |
|---|---|
| `test_reminder_waits_for_the_childs_result_and_fires_once_per_delivery` | pending across an intermediate stop; block on delivery; consumed afterwards; re-arm without a new notification stays silent; a newer notification reminds again |
| `test_foreground_agent_result_delivers_but_a_launch_acknowledgement_does_not` | `toolUseResult` shape; `async_launched` is not a delivery |
| `test_undelivered_children_stay_pending_while_a_delivered_one_reminds` | two pending ids, one delivered; the other reminds later (with a non-`completed` status) |
| `test_active_stop_hook_records_consumption_without_blocking` | `stop_hook_active` returns `{}` but consumes |
| `test_unreadable_or_missing_transcript_falls_back_to_arm_on_stop` | missing file and empty `transcript_path` both block once |
| `test_read_only_children_never_become_pending` | a read-only child is never pending and its notification never reminds |
| `test_malformed_transcript_lines_are_ignored` | a truncated JSONL line containing the id does not break the scan |
| `test_a_legacy_child_keeps_arming_the_reminder_alongside_identified_children` | a mixed session falls back to arm-on-stop |
| `test_codex_arms_on_stop_even_though_its_payload_carries_the_same_fields` | a Codex-shaped payload (all three fields) reminds on the next Stop; the same payload under `harness='claude'` waits for a delivery |

## Validation

Working directory `/home/anvil/repos/nova`.

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests -q` | `Ran 192 tests in 33.277s` / `OK` (183 before this change) |
| `python3 scripts/package.py` | writes `dist/plugins/claude/plugins/nova/hooks/hooks.json` with `--harness claude` and the Codex adapter with `--harness codex` on all three integration events |
| `python3 -c "import xml.dom.minidom; xml.dom.minidom.parse('docs/diagrams/nova-hooks.svg')"` | parses; `svg ok` |
| `python3 scripts/update-guide.py --check` | exit 0 |

## Documentation

`hooks/README.md` ("Parent integration reminders"), the README "After delegation" bullet and hook-map
alt text, and the `integration.py` card plus `<desc>` in `docs/diagrams/nova-hooks.svg` now state that the
Claude reminder waits for the child's result to reach the parent conversation, and that Codex keeps the
arm-on-stop behaviour because its transcript has no child-result entries. The SVG card still has five body lines at
`y=380..480`.

## Limitations

- Both transcript shapes are observed, not documented. The background `<task-notification>` shape was
  confirmed against three real deliveries in the session above. **No foreground (non-`async_launched`)
  Agent `toolUseResult` entry exists in any transcript under `~/.claude/projects/` on this machine** —
  every local `toolUseResult` with an `agentId` has `status: "async_launched"`. The foreground branch is
  implemented as specified and covered by a synthetic test, but it has not been exercised against a real
  foreground delegation. If Claude Code changes either shape, the hook degrades to silence for affected
  children rather than to a false reminder.
- Codex is unchanged: it still reminds on the next parent `Stop` after a child stop, with the same
  false-positive risk if its child stops mid-run. Its rollout transcript has no equivalent child-result
  entry, so removing that risk would need a different signal.
- A child whose result never reaches the parent — killed session, dropped notification — leaves an entry
  in `pending` until `SessionEnd`, and no reminder is issued for it. That is the deliberate trade: the
  hook prefers a missed reminder over reminding about work the parent cannot yet integrate.
- The transcript is rescanned on each parent `Stop` with pending children. Parent transcripts are tens of
  thousands of lines at most and the scan short-circuits on a substring check before parsing, so the cost
  is a few milliseconds; there is no incremental offset tracking.
- As before, the hook proves nothing about the child's work. Delivery of a result is not verification of
  it, and the reminder text still says so.
