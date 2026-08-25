# Swarm Coder headless run plane

`swarm-runplane` is the Swarm Coder-owned, provider-neutral supervisor for launching
one exact Coding Fleet workflow or specialist in a foreign native harness. It
is not an orchestrator. Coding Orchestrator remains the only durable goal and
overall completion owner.

Same-provider delegation stays in the native harness; this launcher is for
foreign-provider runs only.

## Optional Herdr visibility

Foreign-provider jobs can be projected into independently watchable Herdr tabs
when the optional visibility bridge is enabled. The first slice creates one
non-focused tab and root pane per eligible job, publishes only bounded task
display tokens, and leaves terminal panes open for inspection after completion.

Herdr is the presentation and process-location layer. The admitted control-plane
records, validated workflow result, and `anvil.agent-handoff/v1` record remain
the task and completion authority. Pane or agent IDs are volatile locators and
must not appear in durable task, run, or attempt identifiers.

The supported visibility modes are `off`, `auto`, and `required`. Eligibility
requires `HERDR_ENV=1` plus explicit trusted `HERDR_BIN_PATH`,
`HERDR_SOCKET_PATH`, `HERDR_SESSION`, and `HERDR_WORKSPACE_ID` values. The bridge
never searches `PATH`, uses focused layout or `--current`, accepts caller-chosen
metadata, or exposes briefs, credentials, claim nonces, or provider input.

Herdr receives only the stable absolute `swarm-runplane` binary, the `worker`
subcommand, and the durable job ID. Exact provider argv and initial input stay
in a per-job mode-0600 claim; the worker authenticates over a per-job mode-0600
Unix socket and launches the admitted provider command directly in its own
process group. Worker or pane loss is a transport failure. Metadata-reporting
failure is visibility-only, and terminal metadata expiry or clearing never
closes the retained pane.

This integration currently covers only foreign-provider `swarm-runplane` jobs.
Same-provider native-harness visibility is unsupported and deferred to a future
harness-owned seam. See [Herdr visibility for Coding Fleet
jobs](../docs/herdr-agent-visibility.md) for the full layout, authority, sidebar,
rollout, and rollback contract.

## Bootstrap

Build the stable command into a directory already on `PATH`:

```sh
go build -trimpath -o "$HOME/.local/bin/swarm-runplane" ./cmd/swarm-runplane
```

Start the authenticated loopback service (default `127.0.0.1:8083`):

```sh
swarm-runplane serve
```

The service creates `~/.local/state/swarm-runplane/auth.token` with mode 0600.
Clients using the default state directory read it automatically. For a custom
state directory or a remote shell on the same host, set both:

```sh
export SWARM_RUNPLANE_URL=http://127.0.0.1:8083
export SWARM_RUNPLANE_TOKEN_FILE=/absolute/custom-state/auth.token
```

`SWARM_RUNPLANE_STATE` changes the default state directory. `serve --state`
and `serve --listen` override the service state and address; the listen default
is `127.0.0.1:8083`. Client authentication resolves
`SWARM_RUNPLANE_TOKEN`, then `SWARM_RUNPLANE_TOKEN_FILE`, then the token in the
default state directory.

The HTTP service rejects non-loopback listeners, non-loopback `Host` headers,
and missing or invalid bearer tokens.

## Lifecycle

```sh
swarm-runplane health
swarm-runplane capabilities
swarm-runplane start --request route.json
swarm-runplane list
swarm-runplane status JOB_ID
swarm-runplane events --after 10 JOB_ID
printf '%s\n' 'bounded follow-up' | swarm-runplane send JOB_ID
printf '%s\n' 'bounded resumed turn' | swarm-runplane resume JOB_ID
swarm-runplane cancel JOB_ID
swarm-runplane evidence JOB_ID
```

`start --request -`, `send`, and `resume` accept assignment text only on stdin.
The provider command is always launched directly as an argv array, never
through a shell, and assignment text is never added to provider argv.

A terminal success is accepted only when the child returns the small
`anvil.agent-handoff/v1` record; exit zero or narrative success alone is
insufficient.

The start document is `anvil.run-plane/v1` data:

```json
{
  "route": {
    "sourceHarness": "codex",
    "targetHarness": "agy",
    "exactModel": "gemini-3.7-flash-low",
    "effort": "low",
    "canonicalRoleId": "workflow-research",
    "parentGoalId": "goal-id",
    "capabilityMode": "read-only",
    "repositoryRoot": "/absolute/target/repository",
    "fileOwnership": [],
    "evidenceContract": {
      "requiredChecks": ["report findings"],
      "requiredArtifacts": []
    }
  },
  "brief": "Bounded assignment"
}
```

Admission requires an observed exact model/effort pair and exact installed
canonical role bytes. It rejects Coding Orchestrator, Factory/global-write
roles, same-provider routing, repository escapes, overlapping writer ownership,
and unavailable or conflicting routes. Claude receives a CLI-scoped canonical
`--agents` override with project settings excluded, so a target repository
cannot shadow the verified role with a same-named local definition.

Capability discovery labels provider aliases separately from exact concrete
model IDs. The current Claude CLI exposes canonical `opus`/`sonnet` aliases but
no authoritative concrete-model listing, so those pairs are reported for
diagnostics and fail closed for an `exactModel` route. Codex and agy expose
concrete model slugs and remain launchable when their exact pair is observed.
