# Herdr visibility for Coding Fleet jobs

This document defines the first supported Swarm-to-Herdr visibility slice. It
makes eligible foreign-provider Coding Fleet jobs independently watchable in
Herdr without making Herdr a scheduler, task store, or workflow authority.

The first slice applies only to foreign-provider jobs admitted and supervised by
`swarm-runplane`. Same-provider delegation still runs inside its native harness
and is not made visible by this integration. Native-dispatch visibility needs a
separate harness-owned seam and is intentionally deferred; a same-provider job
must not be routed through `swarm-runplane` merely to obtain a pane.

This feature does not register definition-only Coding Fleet roles as live ADK
agents and does not change role manifests, run-plane admission, or workflow
result semantics.

## Authority boundary

Herdr answers **where the process can be watched**. The admitted control-plane
records and validated terminal result answer **what work is true**.

- Goal, assignment, generation, dispatch, ownership, and budget records remain
  the durable identity and authority chain.
- A successful job still requires its validated workflow result and
  `anvil.agent-handoff/v1` record. Exit zero, narrative output, an open pane, or
  a Herdr `done` indicator is not proof of success.
- Herdr's detected lifecycle state remains the authority for its own sidebar
  icon, attention rollups, and notifications. Swarm publishes display metadata;
  it does not call `report-agent` or replace Herdr's semantic state authority.
- A live pane does not prove that an agent is working. A closed, detached, or
  unreachable client does not by itself change the durable job result.
- Terminal panes are retained after terminal success, failure, or cancellation
  so the operator can inspect the transcript. Retention is presentation policy,
  not a different run-plane status.

Herdr workspace, tab, pane, and agent IDs are volatile locators. They may be
recorded in bounded operational evidence, but must never be embedded in a goal,
task, assignment, generation, dispatch, run, or attempt ID. Always consume the
IDs returned by Herdr instead of predicting them.

## Layout contract

Each eligible job gets exactly one new, non-focused tab in the explicitly
selected Herdr workspace. Creating the tab also creates its root pane; that root
pane hosts the supervised provider job. The first slice does not split panes or
reuse a focused pane.

The bridge must:

1. complete normal run-plane admission before creating Herdr layout;
2. create the tab with the admitted repository root as its working directory,
   the explicit workspace ID, and no focus change;
3. capture the returned root pane ID and address that pane explicitly for every
   later operation;
4. give Herdr's `layout.apply` only the fixed Swarm worker argv described below;
   and
5. leave the tab and root pane open when the job reaches a terminal state.

It must never discover the Herdr executable through `PATH`, target whichever
pane or workspace happens to be focused, or use `--current`. Operator focus must
not move when a job starts or changes state.

### Worker transport

Herdr launches the Swarm worker, not the provider command directly. The
`layout.apply` argv is limited to:

```text
<stable-absolute-swarm-runplane-binary> worker <durable-job-id>
```

The job ID is the only per-job value on worker argv. Before layout creation, the
supervisor stores the exact admitted provider command and initial input in a
per-job mode-`0600` claim and creates a per-job mode-`0600` Unix socket. The
worker loads that claim, authenticates to the supervisor over the socket, and
then launches the exact admitted provider command directly in its own process
group. Cancellation addresses that provider process group, never a terminal or
pane shell PID.

The claim path, socket path, authentication nonce, provider argv, brief, and
provider input are transport-private. None is placed in Herdr metadata, the tab
label, the worker argv, or public job events. This preserves the existing
direct-argv and stdin boundaries while allowing the provider terminal to remain
watchable.

## Trusted environment

Visibility is eligible only when all of the following inherited values are
present and valid:

| Variable | Requirement |
| --- | --- |
| `HERDR_ENV` | Exactly `1`, proving the supervisor was launched inside a Herdr-managed environment. |
| `HERDR_BIN_PATH` | Explicit absolute path to the trusted executable; do not resolve `herdr` through `PATH`. |
| `HERDR_SOCKET_PATH` | Explicit absolute local socket path used for every automation call. |
| `HERDR_SESSION` | Explicit Herdr session namespace. |
| `HERDR_WORKSPACE_ID` | Explicit existing workspace in which the job tab is created. |

These values belong to trusted supervisor configuration. A start request, task
brief, provider response, or follow-up message cannot supply or override them.
The bridge must fail closed on malformed values or a workspace/session mismatch
rather than falling back to UI focus.

## Visibility modes

The deployment mode is operator configuration, not request input.

| Mode | Behavior |
| --- | --- |
| `off` | Do not contact Herdr. Preserve the existing headless foreign-provider launch path. |
| `auto` | Use Herdr only when the complete trusted environment and preflight succeed. Before provider start, a visibility setup failure falls back to the existing headless path with a sanitized diagnostic. |
| `required` | Require a successful trusted-environment and Herdr preflight before provider start. Reject the start if visibility cannot be established; never silently fall back to headless execution. |

The mode governs visibility admission and initial placement. Once a provider has
started, a metadata-reporting failure is a visibility degradation, not
permission to launch a duplicate provider and not a substitute terminal job
result. A worker or pane loss after worker start is a transport failure and is
handled by the existing failure/reconciliation path. Detaching or losing a
Herdr UI client is not pane loss; the server-owned pane continues running. The
supervisor accepts success only through the existing validated result boundary.

## Display projection

Swarm owns one internal metadata reporter for its job pane. It may publish only
these bounded display tokens:

| Token | Safe projection |
| --- | --- |
| `taskRef` | Short stable operator-facing reference, such as `NEX-142`. |
| `task` | Sanitized short task title approved for sidebar display. |
| `phase` | Bounded workflow phase label, such as `research`, `execution`, `review`, or `verification`. |
| `summary` | Fixed, synthesized activity label derived from admitted lifecycle events, never provider output. |
| `model` | Exact admitted model label. |
| `attempt` | Bounded attempt ordinal or display reference derived from durable records. |

Token values are presentation only. They cannot change admission, ownership,
agent lifecycle state, job status, workflow disposition, or handoff validation.
The reporter should sequence its updates so an older event cannot overwrite a
newer phase.

The bridge must not expose a bounded brief, prompt, provider input or output,
provider session content, bearer or API token, claim nonce, credential, raw
environment value, or arbitrary request metadata to Herdr. It must not expose a
public HTTP, MCP, or CLI surface for callers to mutate arbitrary Herdr metadata.
All labels must be constructed from the allowlisted fields above, normalized,
redacted, and length-bounded before invoking Herdr. Herdr's own 80-character
normalization is defense in depth, not the primary data boundary.

Typical projections are deliberately terse:

| Event | `phase` | `summary` |
| --- | --- | --- |
| admitted and preparing | `starting` | `preparing agent` |
| provider is active | role-derived phase | `agent working` |
| validated handoff accepted | `complete` | `result accepted` |
| terminal failure | `failed` | `agent failed` |
| canceled | `canceled` | `agent canceled` |

The `complete` projection may be emitted only after the normal validated result
boundary accepts the workflow result and handoff. It must not be inferred from
Herdr state or process exit alone. Terminal display tokens may be cleared or
given a bounded Herdr TTL according to operator policy; expiry removes only the
sidebar projection and never closes the retained pane or changes job history.

## Sidebar configuration

Herdr 0.8.2 supports custom pane metadata as `$name` tokens in expanded Agent
sidebar rows. Operators can add the safe Swarm projection to
`~/.config/herdr/config.toml`:

```toml
[ui.sidebar.agents]
row_gap = 0
rows = [
  ["state_icon", "agent", "state_text"],
  ["$taskRef", "$task"],
  ["$phase", "$summary"],
  ["$model", "$attempt"],
  ["workspace", "tab"],
]
```

Missing values and empty rows disappear. This setting affects only the expanded
desktop sidebar; it does not alter lifecycle detection or task truth. After
editing the file, use Herdr's normal config reload procedure. Metadata is
reported only by the Swarm-owned bridge; operators should not need to patch
individual panes manually.

## Failure behavior

- A malformed or incomplete trusted environment disables visibility in `auto`
  and rejects setup in `required`.
- A tab-creation response without a valid returned root pane ID is a setup
  failure. Do not guess a pane ID and do not target the focused pane.
- A metadata update failure is recorded as a sanitized visibility diagnostic.
  It cannot change the validated provider result.
- Actual worker or pane loss after the worker starts is a transport failure.
  Merely detaching the Herdr UI client is not a worker or pane loss.
- If setup has created an empty tab but provider start fails, leave enough
  bounded diagnostic context for operator inspection. Never close a pane that
  may contain a live or completed provider process as automated cleanup.
- Restart recovery may reconnect a locator to a durable job only with explicit
  verified evidence. Pane liveness alone cannot recover a job as running or
  successful.

## Rollout and rollback

Roll out in stages:

1. deploy with mode `off` and validate that existing run-plane behavior is
   unchanged;
2. enable `auto` for a small foreign-provider, read-only canary and confirm one
   non-focused tab/root pane, safe tokens, cancellation, and validated handoff;
3. expand `auto` to eligible foreign-provider workspace-write jobs after the
   canary is stable; and
4. choose `required` only after Herdr availability and recovery behavior meet
   the operator's reliability expectations.

At every stage, test that start requests cannot select the executable, socket,
session, workspace, pane, metadata source, or arbitrary token values. Also test
that focus is unchanged and same-provider routes remain rejected by the foreign
run plane. Use the local fake worker/provider and fake Herdr boundary for these
checks; documentation and rollout validation must not invoke a real provider or
model.

To roll back, set the mode to `off` for new jobs and restart the run-plane
service through the normal service procedure. Do not delete Herdr state or close
active/completed panes as part of rollback. Existing jobs continue under their
original supervision record; their durable status is reconciled through the
normal workflow result and handoff contracts. The custom sidebar rows may stay
configured because missing metadata tokens simply disappear.

## Upstream Herdr references

This contract was checked against Herdr 0.8.2:

- [Agent automation](https://herdr.dev/docs/agent-automation/)
- [CLI reference](https://herdr.dev/docs/cli-reference/)
- [Configuration](https://herdr.dev/docs/configuration/)
- [Agents and status authority](https://herdr.dev/docs/agents/)
