# Nova

Shared development skills for Codex, Claude Code, and Antigravity. The main agent applies a skill in the current conversation, uses helpers for useful independent tasks, and verifies the result.

[System guide](docs/proposals/nova-next.html) · [Installation](docs/install.md) · [Architecture](docs/adr/0030-shared-skills-native-plugin-delivery.md)

## Nova Flow

The bundled `nova-flow` command tracks milestones, tasks, dependencies, workflow phases, and parent/subagent activity. It provides a terminal view and a live browser view, with attempt evidence and archives of completed runs. It is independent of Herdr Flow. Automatic tracking is disabled for now across all packaged harnesses; use the command only when explicitly requested.

```sh
nova-flow init 'My feature'
nova-flow milestone discovery 'Define behavior'
nova-flow task add spec 'Agree on behavior' --milestone discovery --phase spec
nova-flow serve
```

Bootstrap installs the self-contained command to `~/.local/bin/`; use `--bin-dir` to change that location. It refuses to overwrite modified or conflicting files. The [tool guide](tools/README.md) covers updates, subagents, results, archiving, and LAN binding.

## Skills

| Work | Skills |
| --- | --- |
| Define and prepare | spec, plan, multiplan |
| Change code | build, debug, refactor |
| Check and document | review, docs |
| Measure and release | profile, deploy |
| Support | repo-setup, jj, wiki, use-other-harness |

Spec is an interactive discovery session, with prototypes when requested. Plan breaks accepted behavior into tasks and acceptance tests. Build implements and verifies. Small clear tasks can start directly with the relevant skill. Multiplan explicitly requests separate Antigravity, Claude, and Codex drafts and one synthesis.

Reports use Markdown under `docs/`; HTML is generated only on request. Substantial unfinished tasks keep a short checkpoint. Development uses jj with small changes based on main, local integration, and authorized publication. See [development conventions](instructions/development.md).

## Install from this checkout

```sh
./scripts/bootstrap.sh --dry-run
./scripts/bootstrap.sh
```

Installs into available native harnesses. Use `--harness codex` (or claude/agy) to select one and `--with-codex-helpers` for optional Codex helper setup. Reruns update the stored bundles. See the [installation guide](instructions/install.md) for existing marketplace conflicts, prerequisites, and project configuration.

## Build and check

Requires Python 3.11+. Tests also require PyYAML (see requirements-dev.txt).

```sh
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -v
python3 scripts/update-guide.py --check
python3 scripts/package.py
```

The build produces `dist/plugins/{codex,claude,agy}/`, each containing a native marketplace and a complete `plugins/nova/` bundle. It does not install anything. A package contains copies, so it remains usable after moving it away from this checkout. Version comes from `VERSION`.

```text
skills/          One source for each workflow, references, and report assets
instructions/    Shared development conventions
agents/          Native optional scout, implementer, and reviewer definitions
hooks/           Shared advisory post-edit runner and configuration examples
tools/           Shared utilities as they are added
packaging/       Native manifest differences
scripts/         Package build and validation
tests/          Executable package and hook checks
docs/           Guide, installation, decisions, and task evidence
```

Generated distributions are ignored. Change the sources, rebuild, then use the native plugin manager to update an installed copy. Hook configuration and project instructions are separate setup steps; see the installation guide for each harness.

## Migration from 0.6

This replaces the mandatory role pipeline, sealed-test guard, control plane, contract sidecars, duplicated harness trees, and bootstrap installers. Their source remains in version history. Existing home-directory installations are not changed by building this repository.

Disable or uninstall the previous plugin through its native manager before installing this version. Separately inspect old standalone skills, hooks, and binaries; plugin removal may not own those files. Never delete unrelated user configuration. Historical ADRs and research describe earlier designs; ADR 0030 establishes the current design.
