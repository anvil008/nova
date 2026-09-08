# Nova native plugin migration

## Result

The reviewed templates are now the primary Nova implementation. Fourteen skills, shared development instructions, three optional helper roles in native formats, eleven HTML report assets, and the advisory post-edit runner ship through a single package builder. VERSION is 1.0.0-dev.1.

Removed the legacy guard/control plane, mandatory role pipeline and contracts, duplicated harness source trees, bootstrap installers, generators, and their obsolete tests. Preserved the wiki storage implementation and its executable storage regressions. Historical architecture records remain; obsolete operating guides are under docs/history/. ADR 0030 records the replacement. README, installation guidance, CI, changelog, and the public guide describe the new setup.

## Packaging

`python3 scripts/package.py` creates `dist/plugins/{codex,claude,agy}/`, with one native marketplace and self-contained `plugins/nova/` package per harness. Skills and instructions are copied unchanged. No package relies on source-tree symlinks. Rebuilds remove stale generated files and refuse arbitrary unowned output directories.

All skills explicitly load the bundled common instructions. Persistent project guidance remains repo-setup work. Claude/Agy helpers ship in native agents directories. Codex helpers ship in setup/agents for explicit native setup because automatic plugin helper discovery has not been established.

Codex/Claude native post-edit hooks call the relocated package script and remain no-ops without NOVA_HOOK_CONFIG. Agy ships an adapter requiring installed-path configuration. No hook infers executable configuration from an opened repository.

## Verification

- `python3 -m unittest discover -s tests -q`: 26 tests passed. Includes 17 retained wiki storage regressions, 5 post-edit regressions, and 4 packaging tests covering relocation, native command execution, default no-op behavior, source/resource parity, marketplace resolution, stale-file removal, and output ownership.
- All 14 skills passed the available skill-creator metadata validator.
- Codex plugin-creator validator passed the built Codex package.
- `claude plugin validate dist/plugins/claude/plugins/nova`: passed.
- `agy plugin validate dist/plugins/agy/plugins/nova`: passed; 14 skills and 3 agents processed.
- `python3 scripts/update-guide.py --check`: passed. Browser checked all 14 skill controls and all jj steps; no JavaScript errors.
- `python3 scripts/native-smoke.py --output /tmp/nova-migration-smoke`: passed all three native installation/list operations and installed-asset checks. Bubblewrap mounted temporary configuration directories over personal paths, kept other filesystem paths read-only, and disabled networking. Native evidence is `/tmp/nova-migration-smoke/results.json` (ephemeral).
- Claude's native inventory reported 14 skills, 3 agents, and one PostToolUse hook. Codex listed the installed, enabled 1.0.0-dev.1 package. Agy installed 14 skills and 3 agents. Agy's agent-list command returned no entries in the offline unauthenticated trial, so that command is not evidence of live helper availability.

## Executed workflow

An isolated Codex session used the installed refactor skill on a two-file Python fixture. It read the shared instructions, ran the baseline, replaced a redundant temporary variable with a direct return, ran the same test afterward, preserved the test file, and wrote `docs/reports/refactor01-20260907-simplify-double.md`. No HTML, delegation, VCS initialization, or publication occurred. The main conversation independently reran the fixture test successfully.

The first attempt could not launch tools because the outer read-only filesystem blocked Codex's synthetic mount lock. The same session was resumed after allowing temporary-directory writes. Native workspace sandboxing remained enabled. The final process exited zero and the actual source/report were inspected.

Fixture: `/tmp/nova-native-6l8umybh/fixture`. Test SHA-256 before and after: `bcef4b662690c1791f6af17d6fa3218817b5ff6232ec38b862dd5732c7417957`. Native trace: `/tmp/nova-native-6l8umybh/workflow.log` (ephemeral). This is one small behavior trial, not a general workflow benchmark.

## Limits

Claude and Agy model workflows, native helper execution, hook-event dispatch/trust UI, Antigravity IDE integration, and token/cache efficiency were not trialed. Hook command execution and output contracts were tested directly. Agy hooks and Codex helper copies require explicit setup as documented. No runtime parity or token savings are claimed. The remaining behavioral scenarios are in docs/validation/scenarios.md.

## Source and delivery

Validation covered working-copy source at jj commit `c0c4b67f` in change `kuykmoqn`; subsequent edits add only this evidence and completion note. Parent trunk: `fe8ddc95`. Review was self-review of source, outputs, and retained behavior tests; no independent reviewer was used.

All changes and plugin bundles remain local. No bookmark was published, no PR/merge or release was created, and no personal plugin/configuration installation was changed. Local native trials used temporary mount-isolated configurations. The existing authorized LAN guide remains at http://10.0.20.100:8902/nova-next.html.
