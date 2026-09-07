# Workcell plugin migration

Scope: promote the shared templates, replace old orchestration and packaging, validate native bundles in isolated locations. No personal installation, publication, merge, or deployment.

Plan:
1. Promote 14 skills, shared instructions, 9 helper definitions, and post-edit runner. Remove legacy runtime, generated harness trees, and corresponding test/generator machinery.
2. Build self-contained native plugins from shared sources. Use native plugin managers. Handle persistent instructions and optional helper/hook setup explicitly.
3. Replace operating docs and CI; preserve prior architecture records as history and add the new decision.
4. Test package relocation, native discovery, hook behavior, and a representative workflow where authentication permits. Record limitations.

Completed: source promotion and removal of legacy implementation; packaging implementation drafted.
Remaining: tests, docs/CI, isolated native validation, source review.
Workspace: /home/anvil/repos/workcell, jj change kuykmoqn, parent fe8ddc95. Existing templates and HTML edits are part of this migration. Local pre-migration backup: /tmp/workcell-before-plugin-migration.tar.gz.
No workers active for this task. Public guide server remains on 10.0.20.100:8902.
Next: exercise the packager and native loaders, then finish docs and evidence.

## Completion

All four migration steps are complete. Shared sources and native bundles replace the legacy implementation. The final suite passes 26 tests; all native packages validate and install in mount-isolated configuration directories. One Codex refactor fixture completed through Markdown reporting after correcting the outer sandbox's temporary-directory restriction. The public guide and CI use the new source layout.

Evidence: docs/reports/build01-20260907-native-plugin-migration.md. Known support boundaries: explicit Codex helper setup, explicit Agy hook configuration; Claude/Agy model workflows and live helper/hook dispatch remain untrialed. These are documented native capability/trial limits, not silent substitutes.

No task workers or test processes remain active. No personal installations changed. Work is local in jj change kuykmoqn; no publication or merge. Future work is tool development or separately requested installation and broader workflow trials.
