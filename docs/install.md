# Install

Depth for the one-command Quick Start in the [README](../README.md): what `scripts/bootstrap.sh`
does step by step, choosing models and thinking levels, installing into one project instead of a
whole machine, and upgrading from an earlier install.

### What `bootstrap.sh` does

`scripts/bootstrap.sh` is a thin orchestrator over three existing scripts, run in dependency order:

1. Installs the [`apm`](https://github.com/microsoft/apm) CLI when absent
   (`curl -sSL https://aka.ms/apm-unix | sh`) — the package manager for third-party global agent
   packages. Workcell's own plugin does not ship through it; apm is a peer tool, not the
   distribution layer ([ADR 0020](adr/0020-apm-is-a-peer-tool-not-the-distribution-layer.md)).
2. Ensures the [`vercel-labs/agent-browser`](https://github.com/vercel-labs/agent-browser) package
   is present in apm's single global scope (`~/.apm/apm.yml`), the CLI the `builder` and `reviewer`
   drive browsers through on every harness.
3. Runs `scripts/bootstrap-tools.sh --install` (external dependencies, the `tdd-guard` gate, and the
   `agent-browser` CLI binary itself), then `scripts/bootstrap-plugins.sh` (MCP servers and the
   Workcell plugin, into every harness found).

`bootstrap-plugins.sh` also registers the `chrome-devtools` MCP server (`npx -y
chrome-devtools-mcp@latest`, the `debugger`'s deep diagnostic surface — see
[docs/gates.md](gates.md)) at user scope in whichever of Claude, Codex, Antigravity, and Grok are
installed, through each harness's own CLI — apm's MCP entries are project-scoped only. It retires
any `playwright` MCP entry it previously registered under that exact command, and never touches an
entry it did not write.

Each step is idempotent and safe to re-run; `scripts/bootstrap.sh --uninstall` reverses only the
plugin installer (the tools stay, since other work may share them).

### Choosing models and thinking levels

[`agents/models.json`](../agents/models.json) is the single source for which model and thinking
level every agent runs at, on every harness. Edit it and re-run `scripts/bootstrap-plugins.sh`;
the installer applies it before installing anything.

```json
"planner": {
  "claude": { "model": "opus", "effort": "xhigh" },
  "codex":  { "effort": "high" },
  "agy":    { "model": "pro" }
}
```

Each harness gets only the knobs it actually honours, which differ more than they look:

| Harness     | Model                                   | Thinking level     | Where it takes effect                                                |
| ----------- | --------------------------------------- | ------------------ | -------------------------------------------------------------------- |
| Claude      | `opus` / `sonnet` / `haiku` / `inherit` | `low` – `xhigh`    | agent frontmatter — fully per-agent                                  |
| Codex       | any model id                            | `low` – `max`      | generated `spawn_agent` routing; profiles for manual launches        |
| Antigravity | `pro` / `flash` / `inherit`             | _(none per-agent)_ | agent frontmatter                                                    |
| Grok        | `inherit` / any model id                | _(none per-agent)_ | agent frontmatter; read-only agents also set `permission_mode: plan` |

The Codex plugin manifest has no per-agent model surface, and `agents/openai.yaml` is UI metadata.
Workcell therefore generates an explicit routing contract into every staged Codex skill: each
specialist dispatch must pass its resolved `model` and `reasoning_effort` to `spawn_agent`, with a
bounded context fork, and must fail rather than silently inherit the parent.

The installer also writes `$CODEX_HOME/workcell-<agent>.config.toml` profiles for manually launching
one role with `codex --profile workcell-<agent>`. It never touches a profile it did not write, and
`--uninstall` removes only its own.

Because Codex has no plugin-level agents, each of Workcell's 10 agents ships as a Codex skill named
`agent-<name>` with an `agents/openai.yaml`. Those agent skills and the 18 shared workflow skills
arrive as 28 entries, all namespaced `workcell:<name>`. Every staged skill carries the generated
model-and-effort routing table used for subagent dispatch.

Antigravity does have reasoning effort, but session-wide via `/effort` or `--effort` — there is no
frontmatter key, so the manifest deliberately offers none rather than writing a value that does
nothing. Grok is a single-model harness today, so its knob is `model` alone (`inherit` follows the
session); it has no verified per-agent effort surface or per-agent tool list, so read-only Grok
agents are scoped with `permission_mode: plan` instead. Anything an agent leaves out falls back to
`defaults`. To apply or verify by hand:

```sh
scripts/sync-agent-models.py                    # write into every agent's frontmatter
scripts/sync-agent-models.py --codex-profiles   # ...and emit the Codex profiles
scripts/sync-agent-models.py --check            # report drift, exit non-zero (what CI runs)
```

### Per-project install

To set up one repository instead of your whole machine:

```sh
scripts/bootstrap-project.sh --install --with-hooks /path/to/project
```

This detects the project's stack, installs the formatters and linters that stack needs,
installs the plugin at project scope, and wires the advisory format/lint/guard hooks
into the project. Everything it writes is added to the repository's `info/exclude`, so
none of it shows up in `git diff` or a commit.

## Upgrading from an earlier install

Earlier versions linked agents and skills straight into `~/.claude/agents`,
`~/.codex/skills`, and friends, and later linked plugin wrappers into
`~/.claude/plugins/`. Neither Claude Code nor Codex ever discovered those links.

```sh
scripts/bootstrap-plugins.sh --uninstall   # sweeps the legacy links
scripts/bootstrap-plugins.sh               # installs through the marketplaces
```

See [ADR 0006](adr/0006-plugins-install-through-local-marketplaces.md) for why the
mechanism changed.
