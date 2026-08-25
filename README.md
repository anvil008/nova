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
- `guard/` and `cmd/anvil-guard/` implement the harness-neutral test-seal and
  diff-review gate the fleet installs as a hook in Claude Code, Codex, and
  Antigravity.
- `scripts/bootstrap-tools.sh` reports and optionally installs the external
  verifier tools the toolchain checks call. Run it yourself; the installer never
  installs software.

## Development

Use Go 1.26.5:

```sh
go build ./...
go vet ./...
go test ./...
go build -trimpath -o bin/anvil-guard ./cmd/anvil-guard
go run ./cmd/codingfleet render --check
go run ./cmd/swarm-runplane conformance --offline --definitions harness-agents/rendered
go run ./cmd/codingfleet install --dry-run
```

`bin/anvil-guard` is a gitignored build output that the installer links into
`~/.local/bin`, so build it before running install in any mode. Because it is
gitignored, a `git clean` or a repository move can leave that link dangling and
the hook command silently unrunnable; every install mode except `--uninstall`
refuses to proceed against an absent binary and names the rebuild command, so
run `go run ./cmd/codingfleet install --check` after any such operation.

The installer also links the run-plane foreign-dispatch document into
`~/.local/share/anvil-coding-fleet/`, which is the absolute path the rendered
orchestrator prompts cite.

Hook configuration files are edited in place and never replaced: a symlinked
`~/.claude/settings.json`, `~/.codex/hooks.json`, or
`~/.gemini/config/hooks.json` fails every mode closed rather than being
followed, and an uninstall that empties `~/.claude/settings.json` leaves `{}`
rather than deleting a file the installer may not have created.

Codex records hook trust under index-based keys it computes itself: after an
authorized install, approve the managed Codex hooks once with `/hooks` inside
Codex. `go run ./cmd/codingfleet install --check` reports any that are still
untrusted.

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
