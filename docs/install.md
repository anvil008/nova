# Install

Depth for the two-command Quick Start in the [README](../README.md): choosing models and
thinking levels, installing into one project instead of a whole machine, and upgrading
from an earlier install.

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

| Harness     | Model                                   | Thinking level     | Where it takes effect                             |
| ----------- | --------------------------------------- | ------------------ | ------------------------------------------------- |
| Claude      | `opus` / `sonnet` / `haiku` / `inherit` | `low` – `xhigh`    | agent frontmatter — fully per-agent               |
| Codex       | any model id                            | `low` – `xhigh`    | a **profile**, `codex --profile workcell-<agent>` |
| Antigravity | `pro` / `flash` / `inherit`             | _(none per-agent)_ | agent frontmatter                                 |

Codex reads no per-agent model surface at all — its plugin manifest has no `agents` key, and a
skill's `agents/openai.yaml` is UI metadata only. So the installer also writes
`$CODEX_HOME/workcell-<agent>.config.toml`, which `codex --profile workcell-<agent>` layers over your
base config; that is the half that works today. It never touches a profile it did not write, and
`--uninstall` removes only its own.

Antigravity does have reasoning effort, but session-wide via `/effort` or `--effort` — there is no
frontmatter key, so the manifest deliberately offers none rather than writing a value that does
nothing. Anything an agent leaves out falls back to `defaults`. To apply or verify by hand:

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
