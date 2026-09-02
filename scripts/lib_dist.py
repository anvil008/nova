"""The staging steps `build-codex-plugin.py` and `build-grok-plugin.py` share.

Both scripts exist for the same reason (Codex and Grok copy a plugin in and drop
every symlink that leaves its root, so each harness gets a real staged tree), and
both therefore start by clearing `dist/<harness>/` and end by writing manifests
as pretty-printed JSON. Everything between those two points is harness-specific —
Codex wraps agents as skills and validates its sources first, Grok rewrites the
relative links in agent bodies — so only the two ends live here.
"""

from __future__ import annotations

import hashlib
import json
import os
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


def compute_tree_digest(root: Path) -> str:
    """Compute the tree digest matching scripts/lib.sh `_digest_path`."""
    all_rel: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dp = Path(dirpath)
        for d in dirnames:
            rel = (dp / d).relative_to(root).as_posix()
            all_rel.append(rel)
        for f in filenames:
            if f == ".workcell-stamp.json" and dp == root:
                continue
            rel = (dp / f).relative_to(root).as_posix()
            all_rel.append(rel)
    all_rel.sort()

    lines: list[str] = []
    for rel in all_rel:
        p = root / rel
        rel_hash = hashlib.sha256(rel.encode("utf-8")).hexdigest()
        if p.is_symlink():
            target = os.readlink(p)
            target_hash = hashlib.sha256(target.encode("utf-8")).hexdigest()
            lines.append(f"link {rel_hash} {target_hash}\n")
        elif p.is_dir():
            lines.append(f"dir {rel_hash}\n")
        elif p.is_file():
            content_hash = hashlib.sha256(p.read_bytes()).hexdigest()
            lines.append(f"file {rel_hash} {content_hash}\n")
        else:
            lines.append(f"other {rel_hash}\n")

    stream = "".join(lines).encode("utf-8")
    return hashlib.sha256(stream).hexdigest()


def ignore_root_tests(root_dir: Path, *extra_patterns: str):
    """Ignore a `tests/` directory located directly under `root_dir` and python caches."""
    import fnmatch

    def _ignore(directory: str, files: list[str]) -> list[str]:
        ignored: list[str] = []
        if Path(directory).resolve() == root_dir.resolve() and "tests" in files:
            ignored.append("tests")
        for pattern in ("__pycache__", "*.pyc") + extra_patterns:
            for f in files:
                if fnmatch.fnmatch(f, pattern) and f not in ignored:
                    ignored.append(f)
        return ignored

    return _ignore
