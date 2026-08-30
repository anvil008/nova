# 11. Merge authority is the main conversation

## Status

Accepted

## Context

ADR 0007 made the primary agent a pure orchestrator and gave it, among other things, leave to
"run `git`, `jj`, and `gh` for merge, branch, and issue-state operations". `build-guard` did not
know that. Its `rule_gh` denied `gh pr merge` and any `pulls/<n>/merge` API path unconditionally,
on every harness, for every caller. The one participant the architecture names as the merge
authority was the one participant a mechanical gate stopped from merging, so merges happened by
hand or by working around the guard — the state a mechanical gate exists to remove.

The blanket deny was there because the guard could not tell an orchestrator's tool call from a
subagent's. The environment does not distinguish them: same working directory, same `PATH`, same
variables, verified empirically. The payload does. Claude Code's `PreToolUse` payload carries
`agent_id` (and `agent_type`) only when the call originates in a subagent and omits both for the
top-level conversation; Codex's hooks surface is modelled on the same schema and carries the same
fields. Antigravity has no equivalent — it registers plugin hooks for the whole session, and the
payload names no caller at all.

## Decision

`gh pr merge` and the `pulls/<n>/merge` API path are allowed for a harness's top-level session and
denied for a subagent, with the existing builder messages unchanged for the deny. The discriminator
is the payload's caller identity, read once as `.agent_id // .agent_type // empty`; empty means the
top-level session. Claude Code and Codex are treated identically, because their payloads carry the
same fields.

Antigravity fails closed. With no identity to read and hooks registered session-wide, an allowed
merge there would be unattributable, so every merge stays denied whoever asked. That is the one
asymmetry between the harnesses, and it is deliberate.

`--admin` and `--auto` are denied for every caller, top-level session included, with their own
message. They are the two flags that decouple a merge from the checks: `--admin` overrides branch
protection, `--auto` commits to a merge on checks no human has read yet. What the orchestrator gets
is an ordinary merge of a pull request that is already reviewed and already green.

## Consequences

The guard now agrees with ADR 0007 instead of contradicting it, and the orchestrator can close a
wave without a human merging on its behalf.

The residual risk is real and is accepted: the main conversation can merge, so the guard is no
longer what stops a bad merge. The gates that remain are the human ones — pull-request review and
green CI — plus `tdd-guard status --json` and `gh pr checks`, which the orchestrator already reads
before it decides. What the guard still guarantees is that no agent can override a red check:
`--admin` is denied to everyone, so a merge that CI has not passed is not available to any caller
on any harness.

One gap follows from Codex's trust model rather than from this decision. Codex plugin hooks stay
inactive until the user trusts them with `/hooks`, and its agent definitions document explicit
`build-guard codex` calls as the fallback for an untrusted session. A fallback payload the agent
builds itself names no caller, so it reads as a top-level session and a merge would be allowed.
That fallback was always advisory — an agent that skips the call is unguarded either way — and the
agent definitions independently forbid a builder from merging.

The test corpus gains a payload-shape dimension. `scripts/hooks/tests/guard-corpus.txt` expectations
may now be scoped as `expected@shape` (`claude`, `codex`, `claude-agent`, `codex-agent`, `agy`), and
an unscoped probe must hold for a top-level session, a subagent, and Antigravity alike. A rule whose
verdict depends on who asked has to say so in the corpus rather than in prose.
