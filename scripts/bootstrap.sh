#!/usr/bin/env bash
set -euo pipefail
nova_scripts="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$nova_scripts/bootstrap.py" "$@"
