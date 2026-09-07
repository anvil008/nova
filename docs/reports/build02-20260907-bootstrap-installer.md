# Bootstrap installer

Added `scripts/bootstrap.sh` with a Python implementation that builds stable self-contained bundles and calls native plugin managers. By default it selects CLIs present on PATH. `--harness` selects specific harnesses, `--dry-run` previews without writes/native commands, and `--prefix` chooses stable package storage.

Existing marketplace names pointing elsewhere require `--replace-marketplace`. Optional `--with-codex-helpers` installs absent/identical helpers or updates bootstrap-owned copies that remain unchanged. Conflicting user edits and symlinks are preserved. Project instructions, prerequisites, and formatter/linter activation remain separate setup work.

Local package versions include a content fingerprint to invalidate native caches when source changes without a release bump. Completed native installations remain intact if a later command fails; bootstrap returns nonzero and can be rerun.

Verification:

- Full suite: 31 tests passed, including dry-run no-write/no-native-call behavior, marketplace conflict handling, helper ownership/symlink protection, and native failure propagation.
- Shell syntax and guide synchronization checks passed.
- `scripts/native-smoke.py --bootstrap --output /tmp/workcell-bootstrap-smoke-final` exercised fresh installation and an unchanged rerun across all three native CLIs with optional Codex helpers. Both succeeded inside temporary mount-isolated configurations with networking disabled.
- A separate changed-content trial updated all three plugins and verified the marker file in each installed cache. Evidence: `/tmp/workcell-bootstrap-kphgbnnx/update-result.json` (ephemeral).
- Rebuilt default distribution using `python3 scripts/package.py`.

No personal installation or configuration was modified. All changes remain local. Native model execution and project-specific hook activation were not part of this installer task.
