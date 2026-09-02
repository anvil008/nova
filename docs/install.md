# Install

Depth for the one-command Quick Start in the [README](../README.md): what `scripts/bootstrap.sh`
does step by step, how each harness's copy refreshes, taking `tdd-guard` from a release without a
checkout, choosing models and thinking levels, installing into one project instead of a whole
machine, and upgrading from an earlier install.

### What `bootstrap.sh` does

`scripts/bootstrap.sh` is a thin orchestrator over the existing scripts, run in dependency order:

1. Installs the [`apm`](https://github.com/microsoft/apm) CLI when absent
   (`curl -sSL https://aka.ms/apm-unix | sh`) — the package manager for third-party global agent
   packages. Workcell's own plugin does not ship through it; apm is a peer tool, not the
   distribution layer ([ADR 0020](adr/0020-apm-is-a-peer-tool-not-the-distribution-layer.md)).
2. Ensures the [`vercel-labs/agent-browser`](https://github.com/vercel-labs/agent-browser) package
   is present in apm's single global scope (`~/.apm/apm.yml`), the CLI the `builder` and `reviewer`
   drive browsers through on every harness.
3. Runs `scripts/bootstrap-tools.sh --install`: external dependencies and the `agent-browser` CLI
   binary, then it builds `tdd-guard` from source with the version stamp and installs it, the four
   `build-*` hook wrappers, and `workcell-ws` into `~/.local/bin` as owned copies. Run the same
   script with no flags for a report instead of an install; it names any destination whose
   installed version or content no longer matches this checkout, one `stale` line each.
4. Runs `scripts/bootstrap-plugins.sh` — for every harness found, it stages a link-free plugin
   tree with that harness's `scripts/build-*-plugin.py`, copies it to a path the installer owns,
   and, for Claude and Codex only, registers a marketplace at that owned path. No harness loads
   out of this checkout, and every staged tree carries a `.workcell-stamp.json` recording the
   version and content digest it was made from
   ([ADR 0023](adr/0023-installs-are-self-contained-copies.md)).

No MCP server is registered: every browser surface, the `debugger`'s diagnostics included
(network waterfall, HAR capture, performance traces), runs through the `agent-browser` CLI
(ADR 0012), which costs no per-session tool tokens. `bootstrap-plugins.sh` retires the
`playwright` and `chrome-devtools` MCP entries earlier versions registered — only when an entry
still runs exactly the command Workcell wrote; it never touches an entry it did not write.

Each step is idempotent and safe to re-run; `scripts/bootstrap.sh --uninstall` reverses only the
plugin installer (the tools stay, since other work may share them). An uninstall removes only what
is still byte-for-byte the copy the installer wrote: a destination you have edited since, or one
that was never ours, is left where it is and named on stdout.

### How each copy refreshes

Every install is an installer-owned copy, so editing `agents/`, `skills/`, `scripts/hooks/*`, or a
wrapper in this checkout changes nothing a harness or a hook runs until you re-install — with
Claude the one exception. What that means per harness:

| Harness     | Where its copy lives                 | Refreshes when                                                                   |
| ----------- | ------------------------------------ | -------------------------------------------------------------------------------- |
| Claude Code | `~/.local/share/workcell/claude`     | by itself — the marketplace entry is a command source that re-stages per session |
| Codex       | `~/.local/share/workcell/codex`      | `scripts/bootstrap-plugins.sh`                                                   |
| Grok Build  | `~/.grok/plugins/workcell`           | `scripts/bootstrap-plugins.sh`, then a new session                               |
| Antigravity | `~/.gemini/config/plugins/workcell`  | `scripts/bootstrap-plugins.sh`, then a new session                               |

Claude is the only harness that refreshes itself: its command source re-stages from this
repository when the repository is there, and replays the last staged tree when it is not, so the
plugin keeps working on a machine with no checkout at all. Grok and Antigravity find their plugin
by scanning that directory when a session starts, so a session already running will not see a
refreshed copy — start a new session (in Grok, `r` in the Plugins tab does the same). The tools in
`~/.local/bin` refresh only on `scripts/bootstrap-tools.sh --install`.

### Installing `tdd-guard` without a checkout

`bootstrap-tools.sh --install` builds the gate from source, which needs Go and this repository. On
a machine with neither, take the binary from a tagged release instead: pushing a `v*` tag makes CI
build `tdd-guard-<version>-<os>-<arch>` for linux and macOS on amd64 and arm64, plus a
`SHA256SUMS` covering them, and upload them as workflow artifacts — and attach the same release
artifacts to that tag's GitHub release, if the release itself has been created. Download the asset
for your platform, verify it, and put it on `PATH` — no checkout, no clone, no Go toolchain:

```sh
v=0.6.0; a=tdd-guard-$v-linux-amd64
gh release download "v$v" --pattern "$a" --pattern SHA256SUMS
grep " $a\$" SHA256SUMS | sha256sum -c -
install -m 0755 "$a" ~/.local/bin/tdd-guard
tdd-guard version    # tdd-guard 0.6.0+<commit>
```

If `gh release download` reports nothing found, the tag's release has not been published yet —
the assets are still on the workflow run, reachable with `gh run download`. Each binary is stamped
at link time with the version plus the commit that built it, and `guard/version.go` is the single
source both the stamp and all four plugin manifests come from — CI fails the build if they
disagree. Installed this way the guard carries no receipt, so `bootstrap-tools.sh`'s report says
nothing about it; the hook wrappers and the plugin itself still come from a checkout.

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
`agent-<name>` with an `agents/openai.yaml`. Those agent skills and the 16 shared workflow skills
arrive as 26 entries, all namespaced `workcell:<name>`. Every staged skill carries the generated
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
scripts/bootstrap-plugins.sh --uninstall   # sweeps the legacy installs
scripts/bootstrap-plugins.sh               # installs owned copies
```

See [ADR 0006](adr/0006-plugins-install-through-local-marketplaces.md) for why the
mechanism changed the first time, and
[ADR 0023](adr/0023-installs-are-self-contained-copies.md) for why it changed again.

**Upgrading from a symlink install.** The installer retires its own old links for you and puts no
link in their place. It removes what it wrote at `~/.gemini/config/plugins/workcell` and
`~/.gemini/antigravity-cli/plugins/workcell` before copying, and does not recreate the second
location, so there is one loadable copy rather than two. The same applies to `~/.local/bin`, where
`tdd-guard`, the `build-*` wrappers, and `workcell-ws` become copies. A link the installer did not
write is never touched — it is named and kept.

**Upgrading from a marketplace registration rooted at this repository.** Claude and Codex now
register `~/.local/share/workcell/claude` and `~/.local/share/workcell/codex`, so a registration
pointing at the repository root, at `dist/`, or at a release worktree has to be removed first;
`bootstrap-plugins.sh` does the remove-then-re-add itself, in that order, because removing a
Claude marketplace also uninstalls the plugins that came from it. Re-running the installer is the
whole upgrade. If you undo one by hand, keep the same order: uninstall the plugin, remove the
marketplace, then re-run `bootstrap-plugins.sh`.

If a previous install ran from a path that no longer exists — a deleted release worktree, for
example — and the installer's own sweep did not reach it, remove the stale registration by hand
(`claude`/`codex`/`grok plugin marketplace remove <old-path>`) before re-running
`bootstrap-plugins.sh`; otherwise the harness refuses a second registration under the same name,
or ends up with a duplicate entry that never resolves. See
[ADR 0021](adr/0021-deploys-serve-plugins-from-a-durable-path.md).
