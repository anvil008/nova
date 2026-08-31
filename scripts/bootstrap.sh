#!/usr/bin/env bash
# bootstrap.sh — the whole Workcell setup in one command, at user (global) level.
#
#   scripts/bootstrap.sh              # apm + external tools + the plugin, every harness
#   scripts/bootstrap.sh --uninstall  # remove everything the plugin installer owns
#
# A thin orchestrator over the existing trio, in dependency order:
#
#   1. apm                      installed first when absent (official installer) — the
#                               package manager for third-party global agent packages
#                               (`apm install -g owner/repo`). Workcell's own plugin
#                               cannot ship through it (see docs/adr — per-harness
#                               agents and the marketplace layout are outside APM's
#                               package model), so apm is a peer tool here, not the
#                               installer.
#   2. bootstrap-tools.sh       external binaries + the tdd-guard gate + hook wrappers
#   3. bootstrap-plugins.sh     the Workcell plugin, into every harness found
#
# Each step is idempotent; re-run at will. Uninstall reverses only step 3: the
# tools are shared with other work and stay.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ${1:-} == --uninstall ]]; then
  "$ROOT/scripts/bootstrap-plugins.sh" --uninstall
  echo "note: external tools from bootstrap-tools.sh are left in place (shared with other work)"
  exit 0
fi
[[ $# -eq 0 ]] || { echo "usage: scripts/bootstrap.sh [--uninstall]" >&2; exit 2; }

if ! command -v apm >/dev/null 2>&1; then
  echo "== apm not found — installing (https://aka.ms/apm-unix) =="
  curl -sSL https://aka.ms/apm-unix | sh || echo "apm install failed — continuing; global agent packages just stay unmanaged"
  hash -r
fi

# The agent-browser *skill* ships through apm's single global scope (~/.apm/apm.yml —
# the same manifest that holds anything you add yourself with `apm install -g`; apm
# has exactly one user scope, so Workcell's entries and yours share it and coexist).
# The matching CLI binary is installed by bootstrap-tools.sh.
if command -v apm >/dev/null 2>&1 && ! apm deps list -g 2>/dev/null | grep -q agent-browser; then
  apm install -g vercel-labs/agent-browser
fi

"$ROOT/scripts/bootstrap-tools.sh" --install
"$ROOT/scripts/bootstrap-plugins.sh"
