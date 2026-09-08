# 23. Installs are self-contained copies

## Status

Accepted. Supersedes the Antigravity clause and the repository-rooted marketplace layout of
[ADR 0006](0006-plugins-install-through-local-marketplaces.md), and re-grounds
[ADR 0021](0021-deploys-serve-plugins-from-a-durable-path.md) harness by harness.

## Context

ADR 0006 kept one live symlink on purpose: Antigravity reads its plugin directory straight off
disk, so linking the wrapper there meant edits to `agents/` and `skills/` reached a session
without an install step. ADR 0021 then found the cost of resolving an install through a path
this repository owns — deleting the path broke Claude and Codex — and required a durable one,
but left the durable path a human obligation ("keep the checkout") rather than something the
installer provides. The tracked Claude and Codex marketplace manifests still sat at the
repository root, and the hook wrappers, `tdd-guard` and `nova-ws` on `PATH` were symlinks
into a working tree that a `jj workspace forget` or a `git clean` could take away mid-session.

The evidence for changing this was collected on 2026-09-01, from each harness's own
documentation:

- **Claude Code** documents marketplace plugin entries whose `source` is a `command` — a
  producer the CLI runs to obtain the plugin tree — with `mode: copy` taking a copy of what the
  command prints (added in 2.1.229; behaviour confirmed against the local CLI, 2.1.258, whose
  manifest parser requires `command` to be a string, not an array).
- **Antigravity** documents a plugin CLI and an auto-scan of `~/.gemini/config/plugins/`
  (antigravity.google/docs/cli/plugins/). The `~/.gemini/antigravity-cli/plugins/` location the
  CLI installs into has no documented scan status.
- **Grok Build**'s user guide documents `~/.grok/plugins/` as auto-discovered and auto-trusted
  in user scope, with no registration step at all.
- **Codex**'s copy-on-install — which drops symlinks escaping the plugin root — is
  **undocumented**; it is observed behaviour with open upstream issues (openai/codex#18863,
  openai/codex#24770). That is why this repository keeps its own symlink-free staging and its
  own gates rather than trusting the behaviour to stay.

## Decision

**An install is an installer-owned copy at a path the installer owns, on every harness.** No
harness resolves Nova through this repository at runtime.

**Claude Code — a durable command-source marketplace.** The marketplace lives at
`~/.local/share/nova/claude`, and its single plugin entry is a `command` source in `copy`
mode whose command is `stage-nova`, an installer-owned shim in that same durable directory.
This was chosen over a durable _directory_ marketplace because the harness re-takes the
producer's output on refresh and, as observed while building this against CLI 2.1.257, identifies
the cached copy by its content: a changed tree is a new version with nobody bumping a number,
which retires the manual-bump bug class, and the refresh happens by re-running the producer
rather than by uninstalling and reinstalling the plugin, which retires the destructive-refresh
bug class. `mode: link` was rejected because it makes the directory the command prints the plugin
itself: that directory would have to persist and stay authoritative, reinstating exactly the live
dependency on a directory outside the installer's control that this decision exists to remove.

**Codex — a durable owned marketplace copy.** `scripts/build-codex-plugin.py` stages a
symlink-free tree, the installer copies it to `~/.local/share/nova/codex`, and
`codex plugin marketplace add` registers _that_ path. The staged manifest carries a version of
`<semver>+codex.<content hash>` — `0.6.0+codex.` followed by twelve hex digits of the staged
tree's digest — so a content change is always a version change and Codex sees the refresh. This
is the deliberate, documented replacement for the accidental build-stamp version ADR 0021
recorded as unusable.

**Grok — a drop into the documented plugin directory.** Grok auto-discovers and auto-trusts
plugins under `~/.grok/plugins/`, so the installer drops one owned copy at
`~/.grok/plugins/nova` and registers nothing. When the `grok` CLI is present the installer
retires the old marketplace registrations; it never creates a new one, and it installs
correctly with no CLI on `PATH` at all.

**Antigravity — one owned copy at the documented scan directory.**
`scripts/build-agy-plugin.py` stages a symlink-free tree and the installer copies it to
`~/.gemini/config/plugins/nova`, the directory Antigravity documents as scanned. The
`agy plugin` CLI is deliberately not invoked to install or remove anything: it installs into
`~/.gemini/antigravity-cli/plugins/`, whose scan status is undocumented, and its registry is
blind to plugins found by the scan, so an `agy plugin uninstall` aimed at a pre-existing symlink
would be a guess about someone else's state. Only `agy plugin validate` runs, best-effort,
against the staged tree. The `antigravity-cli` location is retired and not recreated, so there
is one loadable copy rather than two.

**ADR 0021 is satisfied per harness, by construction.** Claude and Codex register paths under
`~/.local/share/nova`, which the installer creates and owns and no deploy cleanup removes;
Grok and Antigravity register nothing at all, so the harness's own plugin directory _is_ the
durable path. Nothing depends any more on a human keeping a checkout or a release worktree
alive, and ADR 0021's consequence that a Codex deploy needs a content diff instead of a version
check is retired: the staged Codex version now tracks the release.

**One version, in Go source.** `guard.Version` in `guard/version.go` is the single source of
truth. The four tracked plugin manifests (`plugins/claude`, `plugins/codex`, `plugins/agy`,
`plugins/grok`) must equal it, and `scripts/build-guard-release.py --check` proves it on every
CI run. Link-time `BuildMetadata` only ever appends (`0.6.0+<commit>`), the staged Codex version
only ever appends `+codex.<hash>`, and the version Claude records for its cached copy is the
harness's own business, derived from the copy's content rather than declared by us. A tag-gated
CI job builds the release matrix, uploads the stamped binaries and their `SHA256SUMS` as workflow
artifacts, and attaches them to the tag's GitHub release when one exists.

## Consequences

**Live-edit-without-reinstall is gone on every surface, and that is the point.** Editing
`agents/`, `skills/`, `scripts/hooks/*` or `scripts/nova-ws` in a checkout changes nothing
any harness or hook runs until the next `scripts/bootstrap-tools.sh --install` /
`scripts/bootstrap-plugins.sh` — Claude, below, is the single exception. The capability ADR 0006
preserved for Antigravity is traded for an install that cannot be broken by moving, cleaning, or
deleting the tree it came from.

**Claude is the exception that refreshes itself.** Its command source re-stages from the
repository whenever Claude refreshes the marketplace, which it does when a session starts; the
exact cadence is the harness's to choose, and this decision depends only on it being automatic.
When the repository is gone the shim replays the last staged tree and still exits zero, so a
checkout-less machine keeps working with the plugin it last had.

**The other three freeze until bootstrap runs again.** A Codex, Grok or Antigravity install is
the copy taken at bootstrap time and stays frozen until `scripts/bootstrap-plugins.sh` runs
again. Grok and Antigravity additionally need a new session to pick a refreshed copy up —
neither watches its plugin directory while a session is running — which is why the installer
prints the requirement as it goes (`agy: note: a new agy session is required to load changes`;
`grok: ... start a new session or press 'r' in Grok's Plugins tab to load changes`).

**Drift is reported, not silent.** `scripts/bootstrap-tools.sh` run without `--install` compares
the version recorded in each receipt against the repository's and prints one line per drifted
destination — `stale <name> installed <a>, repository <b> — re-run: scripts/bootstrap-tools.sh
--install` — with the comparison prefix-aware, so `0.6.0+<commit>` is not drift against `0.6.0`,
and the wrappers, which carry no version of their own, compared by content instead. Every staged
tree also carries `.nova-stamp.json` (name, version, builtAt, sourceRoot, contentDigest), so
a copy on disk describes itself even without its receipt.

**Ownership moves from link targets to receipts and stamps.** A link could be checked by reading
where it pointed; a copy cannot, so `install_owned` records a receipt under
`~/.local/state/nova/receipts/` and re-checks it against the destination's current digest.
Every uncertain answer falls on the side of keeping the human's file.

**A copy the human edited is left behind, and named.** `uninstall_owned` removes only a
destination whose digest still matches the receipt; anything else stays exactly as found and is
reported — `left <dst> (locally modified)` or `left <dst> (not ours)`. An uninstall can therefore
leave a stale plugin tree in a harness's directory, which is the correct trade: it is now the
human's file.

**No runtime consumer resolves through a symlink into this repository any more.** The hook
wrappers (`build-hooks`, `build-format`, `build-lint`, `build-guard`), `tdd-guard` and
`nova-ws` in `~/.local/bin` are installed copies rather than links, every staged plugin tree
is symlink-free by construction, and the installer retires the two legacy Antigravity symlinks
instead of leaving them live. The remainder the previous revision of this work left open — the
hook wrappers still pointing into the tree — is closed, not merely narrowed.

**If command plugin sources are disabled, register the same tree as a directory.** A Claude
configuration carrying `disableCommandPluginSources: true` rejects the command source; the
installer says so by name and points at `~/.local/share/nova/claude/nova`, the
already-staged tree, which can be registered as an ordinary directory source. That fallback
costs only the automatic per-session restage. No plugin seed-directory environment variable is
wired into bootstrap; a CI job or container image that needs the plugin without a checkout
registers that same durable directory.

**ADR 0020 is unaffected.** Distribution stays native; APM remains a peer tool that installs
third-party packages, not the layer any of this goes through.
