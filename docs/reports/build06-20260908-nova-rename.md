# Nova rename

The project, GitHub repository, documentation, CLI (`nova-flow`), environment variables (`NOVA_*`), plugins (`nova@nova`), and runtime store (`.nova`) now use Nova. No legacy command alias is installed.

Global Codex, Claude, and Agy installations were replaced. Existing sessions must restart to load the new plugin; inert retired hook scripts prevent errors from cached absolute paths until then.

Migrated the home wiki from `~/.workcell` to `~/.nova`, including the renamed repository namespace. Migrated Forge and Nova project stores, preserving run/task identities and reference mappings. A newer duplicate Agy run remains active; the older snapshot is retained under Forge's `.nova/migration-history/` to avoid double-counting telemetry.

Validation: 82 unit tests passed, generated guide check passed, native packages built, Codex manifest validator passed, all three native installs succeeded, and both migrated project stores validated.
