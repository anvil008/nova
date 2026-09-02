#!/usr/bin/env python3
"""Stage the Antigravity (agy) plugin as a real directory tree.

Antigravity is served from a self-contained, owned copy at the documented
auto-scan path ~/.gemini/config/plugins/workcell, rather than live symlinks
into this repository. The wrapper in plugins/agy/ carries symlinks to
../../agents/agy and per-skill links in skills/ (ADR 0003).

This script stages plugins/agy/ into dist/agy/workcell/ with symlinks=False,
dereferencing every agent and skill link into real files.

Ordering: sync_agy_skills() (in scripts/bootstrap-plugins.sh) runs before
staging to regenerate plugins/agy/skills/ minus any agent-owned skills.
The builder copies through that directory.

Output layout:
    dist/agy/
    └── workcell/
        ├── .workcell-stamp.json
        ├── plugin.json
        ├── hooks.json
        ├── rules/
        ├── agents/
        └── skills/
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import lib_dist

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "agy"
PLUGIN = DIST / "workcell"
WRAPPER = ROOT / "plugins" / "agy"
MANIFEST = WRAPPER / "plugin.json"
HARNESS = ROOT / "harnesses" / "agy"


def fail(message: str) -> int:
    print(f"build-agy-plugin: {message}", file=sys.stderr)
    return 1


def compute_tree_digest(root: Path) -> str:
    """Compute stable content digest matching _digest_path in scripts/lib.sh."""
    lines: list[str] = []
    entries: list[str] = []
    for p in root.rglob("*"):
        if p.name == ".workcell-stamp.json":
            continue
        rel = p.relative_to(root)
        entries.append(f"./{rel}")
    entries.sort(key=lambda s: s.encode("utf-8"))
    for entry in entries:
        rel = entry[2:]
        p = root / rel
        rel_sha = hashlib.sha256(rel.encode("utf-8")).hexdigest()
        if p.is_symlink():
            target_sha = hashlib.sha256(os.readlink(p).encode("utf-8")).hexdigest()
            lines.append(f"link {rel_sha} {target_sha}\n")
        elif p.is_dir():
            lines.append(f"dir {rel_sha}\n")
        elif p.is_file():
            file_sha = hashlib.sha256(p.read_bytes()).hexdigest()
            lines.append(f"file {rel_sha} {file_sha}\n")
        else:
            lines.append(f"other {rel_sha}\n")
    combined = "".join(lines).encode("utf-8")
    return hashlib.sha256(combined).hexdigest()


def main() -> int:
    # MIGRATION FALLBACK (remove with #167): until every harness family is authored
    # under harnesses/<h>, this stager still builds from the pre-layered
    # plugins/agy wrapper when that family is absent. #167's
    # no-fallback-survives gate rejects this branch; it must not outlive it.
    layered = HARNESS.is_dir()
    if not layered:
        print(
            f"build-agy-plugin.py: warning: {HARNESS.name} has no harness family; "
            f"building from the pre-layered plugins/agy wrapper (migration fallback, #167)",
            file=sys.stderr,
        )
    source = HARNESS if layered else WRAPPER
    runtime = source / "runtime" if layered else source
    manifest = runtime / "plugin.json"
    for required in (
        source,
        manifest,
        source / "agents",
        source / "skills",
        runtime / "rules",
        runtime / "hooks.json",
    ):
        if not required.exists():
            return fail(f"missing required source: {required.relative_to(ROOT)}")

    try:
        manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
        version = manifest_data["version"]
    except (json.JSONDecodeError, KeyError, OSError) as e:
        return fail(f"could not read manifest {manifest.relative_to(ROOT)}: {e}")

    lib_dist.reset_dist(DIST, PLUGIN)

    if layered:
        shutil.copytree(
            runtime,
            PLUGIN / "runtime",
            symlinks=False,
            ignore=lib_dist.ignore_root_tests(runtime),
        )
        shutil.copy2(manifest, PLUGIN / "plugin.json")
        shutil.copy2(runtime / "hooks.json", PLUGIN / "hooks.json")
        shutil.copytree(runtime / "rules", PLUGIN / "rules", symlinks=False)
        handoff = runtime / "handoff.md"
        if handoff.is_file():
            shutil.copy2(handoff, PLUGIN / "handoff.md")
        shutil.copytree(
            source / "agents",
            PLUGIN / "agents",
            symlinks=False,
            ignore=lib_dist.ignore_root_tests(source / "agents"),
        )
        for agent in (PLUGIN / "agents").glob("*/agent.md"):
            text = agent.read_text(encoding="utf-8").replace(
                "](../../runtime/handoff.md)", "](../../handoff.md)"
            )
            agent.write_text(text, encoding="utf-8")
        shutil.copytree(
            source / "skills",
            PLUGIN / "skills",
            symlinks=False,
            ignore=lib_dist.ignore_root_tests(source / "skills"),
        )
    else:
        shutil.copytree(
            source,
            PLUGIN,
            symlinks=False,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            dirs_exist_ok=True,
        )

    escaping = [p for p in DIST.rglob("*") if p.is_symlink()]
    if escaping:
        return fail(
            "staged tree still contains symlinks: "
            + ", ".join(str(p.relative_to(DIST)) for p in escaping)
        )

    digest = compute_tree_digest(PLUGIN)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = {
        "name": "workcell",
        "version": version,
        "builtAt": now,
        "sourceRoot": "harnesses/agy" if layered else "plugins/agy",
        "contentDigest": digest,
    }
    lib_dist.write_json(PLUGIN / ".workcell-stamp.json", stamp)

    agents = (
        len([p for p in (PLUGIN / "agents").iterdir() if (p / "agent.md").is_file()])
        if (PLUGIN / "agents").is_dir()
        else 0
    )
    skills = (
        len([p for p in (PLUGIN / "skills").iterdir() if p.is_dir()])
        if (PLUGIN / "skills").is_dir()
        else 0
    )
    print(f"staged {DIST.relative_to(ROOT)}: {agents} agents, {skills} skills")
    return 0


if __name__ == "__main__":
    sys.exit(main())
