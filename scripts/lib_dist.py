"""The staging steps `build-codex-plugin.py` and `build-grok-plugin.py` share.

Both scripts exist for the same reason (Codex and Grok copy a plugin in and drop
every symlink that leaves its root, so each harness gets a real staged tree), and
both therefore start by clearing `dist/<harness>/` and end by writing manifests
as pretty-printed JSON. Everything between those two points is harness-specific —
Codex wraps agents as skills and validates its sources first, Grok rewrites the
relative links in agent bodies — so only the two ends live here.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path


def reset_dist(dist: Path, plugin_root: Path) -> Path:
    """Clear a staging tree and recreate its plugin root, ready to be filled."""
    shutil.rmtree(dist, ignore_errors=True)
    plugin_root.mkdir(parents=True)
    return plugin_root


def write_json(path: Path, data: dict) -> None:
    """Write one manifest the way both harnesses read them: indented, newline-terminated."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
