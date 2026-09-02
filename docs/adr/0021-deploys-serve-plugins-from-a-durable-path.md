# 21. Deploys serve plugins from a durable path, not a temporary worktree

## Status

Accepted

Re-grounded by [ADR 0023](0023-installs-are-self-contained-copies.md): the durable paths this ADR
requires are now installer-owned directories under `~/.local/share/workcell` rather than a
checkout a human has to keep, and the Codex consequence below — that a manifest version cannot
confirm a release — is resolved there, so a Codex deploy no longer needs a content diff as its
confirmation step. The rest of this record stands.

## Context

The v0.4.0 deploy ran the plugin build and install from a temporary worktree,
`/home/anvil/repos/workcell-v0.4.0-plugins`, then removed it once the deploy step reported
success. Claude and Codex both broke immediately after: `claude plugin list` /
`codex mcp list`-adjacent status reported `✘ failed to load — cache-miss` for `workcell`.

Both harnesses copy plugin content on install, but they do not re-copy it on every load — they
resolve the installed plugin through the **registered marketplace path**, which for a local
marketplace is a filesystem path recorded at install time, not a snapshot of the content at that
path. Deleting the worktree deleted the path the marketplace entry still pointed at, so both
harnesses' next load found nothing there. The one-time copy Codex makes into its own plugin cache
(`scripts/build-codex-plugin.py`'s reason for existing at all — see ADR 0005) is not a defense
against this: the _marketplace_ entry that names where to find a fresh copy is still the
worktree's now-deleted path, so a reinstall or update through that marketplace fails the same way
even though a previous copy sits untouched in the cache.

## Decision

**A deploy that installs or updates the plugin runs from a path that outlives the deploy step.**
The primary repository checkout is the default durable path; a dedicated release worktree is
acceptable only if it is kept — never deleted as deploy cleanup — until the next bootstrap run
re-registers the marketplace from a different path. `scripts/bootstrap-plugins.sh` and
`scripts/bootstrap.sh` are unchanged by this decision; the rule binds the human or agent invoking
them, not the scripts themselves, since neither script can detect in advance that its caller's
`cwd` is about to be removed.

v0.4.0 currently serves from `/home/anvil/repos/workcell-v0.4.0-plugins`, which must **not** be
deleted until a bootstrap run from the primary repository (`/home/anvil/repos/workcell`)
re-registers the marketplace at that path instead.

## Consequences

- **The next bootstrap from the primary repository will collide, not merge.** Both harnesses
  already have a `workcell` marketplace entry pointing at the release worktree: Codex refuses a
  second registration under the same name from a different source ("already added from a
  different source"), and Grok ends up with duplicate marketplace entries rather than one updated
  in place. Whoever re-runs bootstrap from the primary repository must remove the stale
  registration first (`codex plugin marketplace remove` / `grok plugin marketplace remove` for the
  worktree path) — `docs/install.md` carries this as an upgrade note.
- **Grok has no v0.3.0 to roll back to.** It is net-new in v0.4.0, so its "rollback" is
  registration-level, not a version downgrade: `grok plugin uninstall workcell` followed by
  removing the marketplace entry, not a re-point at an earlier release.
- **Codex's manifest version cannot confirm a release on its own.** `plugins/codex/.codex-plugin/plugin.json`
  carries an independent build-metadata version (`0.1.0+codex.<buildstamp>`, unrelated to this
  repository's tracked semver — see the v0.4.0 release notes) that a `jq .version` check cannot
  use to confirm which release is installed. The v0.4.0 deploy instead verified Codex's staged
  content byte-for-byte against the source tree. A GitHub issue is open to give the Codex manifest
  a version that actually tracks the release; until it lands, a Codex deploy needs a content
  diff, not a version-string check, as its confirmation step.
- Any future harness whose install model resolves through a registered path rather than a fresh
  copy inherits this same rule by construction, without a new ADR.
