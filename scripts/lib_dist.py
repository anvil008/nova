"""Shared helpers for staging self-contained plugin trees and release manifests.

Stagers copy real files, rewrite local resource links, and stamp the resulting
content. Runtime-specific packaging remains in each build-*-plugin.py entrypoint.
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
