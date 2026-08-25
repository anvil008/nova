# Swarm Coder

Swarm Coder owns Foundry Zero's provider-neutral coding-agent catalog, native
harness projections, installer, control-plane contracts, and the
`swarm-runplane` supervisor. It is intentionally separate from the sibling
[`swarm`](https://github.com/anvil008/swarm) repository, which owns executable Google ADK agents, their
registry, models, telemetry, and durable agent run API.

The command and operational names remain stable across the repository split:
`codingfleet`, `swarm-runplane`, `SWARM_RUNPLANE_*`, and the default state under
`~/.local/state/swarm-runplane` are unchanged.

## Layout

- `harness-agents/` contains the canonical catalog and generated Codex, Claude
  Code, and Antigravity definitions.
- `codingfleet/` validates, renders, and installs those definitions.
- `controlplane/` defines authority, selection, lifecycle, and verification
  contracts.
- `runplane/` and `cmd/swarm-runplane/` implement the authenticated foreign
  harness supervisor and offline conformance suite.
- `herdrbridge/` contains the optional Herdr visibility integration.
- `cmd/codingfleet/` provides catalog render and install commands.

## Development

Use Go 1.26.5:

```sh
go build ./...
go vet ./...
go test ./...
go run ./cmd/codingfleet render --check
go run ./cmd/swarm-runplane conformance --offline --definitions harness-agents/rendered
```

Rendering is repository-relative. The installer and run-plane retain their
existing explicit safety boundaries; development and verification do not
install global symlinks or start the service.

The sibling Swarm repository currently carries a temporary `harness-agents`
compatibility symlink so already-installed Claude, Codex, and Gemini paths keep
resolving without a global mutation during this split. A later authorized
`go run ./cmd/codingfleet install` from this repository should repoint those
global paths directly here; the Swarm compatibility link can then be removed.

See [the Coding Fleet guide](harness-agents/README.md) and
[the run-plane guide](runplane/README.md) for operational details.
