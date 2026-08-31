# 20. APM is a peer tool, not the distribution layer

## Status

Accepted

## Context

Microsoft APM (`microsoft/apm`, evaluated at 0.29.0) is a package manager for agent
primitives: one manifest (`apm.yml`), a lockfile, and an installer that projects skills,
agents, instructions, hooks, and MCP/LSP configuration into every harness it detects. On
paper it replaces exactly the plumbing this repository maintains by hand — the per-harness
`plugins/` wrappers, the staging scripts, and the bootstrap installer — and the question of
adopting it for Workcell's own distribution came up repeatedly as harnesses were added.

The evaluation was empirical: probe packages were built and installed, deployments
inspected, and APM's own source consulted where behaviour needed explaining. Three findings
decided the matter.

**APM translates formats, not content.** Its projection takes _one_ canonical agent
definition and converts it per target — Claude markdown, Codex TOML, per-harness paths.
That handles format differences. Workcell's harness differences are _content_ differences,
owned by `agents/models.json` and the body conditionals: per-agent models that do not exist
on other harnesses (`opus` / `gpt-5.6-sol` / `pro` / `inherit`), disjoint tool vocabularies
(`Read, Grep` vs `view_file, grep_search`), effort semantics only some harnesses expose,
per-harness body text, and ADR 0003's rule that an Antigravity agent's skill must not also
be offered globally. A single canonical agent cannot encode any of that; APM's own installer
printed a "lossy agent compilation" warning (Codex `tools` dropped) when handed one of ours.

**This repository cannot even be an APM package.** APM's format detection
(`src/apm_cli/models/format_detection.py`) is a first-match cascade in which a
`.claude-plugin/` directory at the package root classifies the whole tree as
`MARKETPLACE_PLUGIN` before `apm.yml` is ever considered, with no override. Workcell's root
_is_ a Claude plugin marketplace, so `apm install <repo>` decomposes it blindly — in the
probe it flattened every `.md` under `agents/` (jj skill references included) into installed
agent files. Decomposition also strips the `workcell:` plugin namespace, leaving skills with
collision-bait bare names (`build`, `debug`, `docs`) in shared skill directories.

**The remaining bootstrap work is out of APM's scope.** APM wires MCP and LSP
_configuration_ but installs no binaries (`bootstrap-tools.sh`'s actual job), and it
refuses global MCP registration outright ("MCP servers are project-scoped; --global is not
supported for MCP entries"), so user-scope MCP servers go through each harness CLI.

Meanwhile the native path kept winning on its own merits: Codex and Grok both consume the
Claude plugin layout (Grok reads `.claude-plugin/` manifests directly and aliases
`CLAUDE_PLUGIN_ROOT` for hooks), so adding the fourth harness cost one staging script and a
bootstrap section, with the namespace, hooks, and per-agent models intact.

## Decision

**Workcell's own distribution stays native.** `agents/bodies/` + `agents/agents.json` +
`agents/models.json` remain the single source; `sync-agents.py` generates the per-harness
variants; the `plugins/<harness>/` wrappers, staging scripts, and `bootstrap-plugins.sh`
install them as _plugins_ — namespaced, hook-carrying, model-tuned — via each harness's own
marketplace mechanism.

**APM is a peer tool, ensured but not depended on.** `scripts/bootstrap.sh` installs the
`apm` CLI when absent and uses its one global scope (`~/.apm/apm.yml`) for third-party
packages the agents rely on (currently `vercel-labs/agent-browser`). That manifest is
shared with whatever the human installs globally themselves; entries coexist and are
managed line-by-line (`apm install -g` / `apm uninstall -g` / `apm deps list -g`).

**No `apm.yml` at the repository root.** Adding one is what _unlocks_ the broken
`MARKETPLACE_PLUGIN` install path for anyone who runs `apm install` against the repo —
today that attempt fails cleanly. If APM distribution of the shared skills is ever wanted,
the clean shape is a CI-published skills-only bundle (a tree APM classifies as
`SKILL_BUNDLE`) in a separate branch or repository, not a manifest here.

## Consequences

Adding a harness remains a deliberate act — an emitter branch, a wrapper, a bootstrap
section, tests — rather than a free ride on APM's target matrix. Grok cost roughly that
much and lost nothing in fidelity; that trade is accepted.

The per-harness knowledge stays encoded where it is verified: `models.json` documents what
each CLI actually honours, and the generators refuse what they cannot express. No external
projection layer silently degrades an agent.

Re-evaluate if APM grows per-target agent overrides (one definition, per-harness model and
tool blocks), honours plugin namespaces on decomposition, or drops the marketplace-first
detection precedence. Any of those would reopen the distribution question; none existed at
0.29.0.
