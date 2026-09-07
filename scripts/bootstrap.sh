#!/usr/bin/env bash
set -euo pipefail
workcell_scripts="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$workcell_scripts/bootstrap.py" "$@"
