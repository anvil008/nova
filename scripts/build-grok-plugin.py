#!/usr/bin/env python3
"""Stage the Grok Build plugin as a real directory tree.

Grok installs a plugin by *copying* it into ~/.grok/installed-plugins/<id>/ —
and, exactly like Codex, it drops any symlink that points outside the plugin
root. The wrapper in plugins/grok/ links back to ../../agents/grok and
../../skills, so an install from the repository yields a plugin with a manifest
and nothing else (verified with `grok plugin details`: "0 skill dir(s),
0 agent dir(s)").

So Grok gets a staged copy instead of a link farm:

    dist/grok/
    ├── .grok-plugin/marketplace.json
    └── plugins/workcell/
        ├── .claude-plugin/plugin.json   Grok accepts the Claude manifest layout
        ├── .workcell-stamp.json         provenance and tree digest
        ├── handoff.md                   the contract agents/*.md link to as ../handoff.md
        ├── agents/                      real copies of agents/grok/*.md
        └── skills/                      real copies of skills/*, sans caches

Relative links are written for the repository layout (agents/grok/<n>.md sits
two levels under the root, so bodies say ../../skills/ and ../handoff.md). In
the staged tree agents/ sits directly beside skills/, so ../../skills/ is
rewritten to ../skills/; ../handoff.md already resolves to the copied file.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import lib_dist

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "grok"
PLUGIN = DIST / "plugins" / "workcell"
HARNESS = ROOT / "harnesses" / "grok"


def fail(message: str) -> int:
    print(f"build-grok-plugin: {message}", file=sys.stderr)
    return 1


def main() -> int:
    layered = HARNESS.is_dir()
    runtime = HARNESS / "runtime" if layered else ROOT / "plugins" / "grok"
    agents_dir = HARNESS / "agents" if layered else ROOT / "agents" / "grok"
    skills_dir = HARNESS / "skills" if layered else ROOT / "skills"
    manifest = runtime / ".claude-plugin" / "plugin.json"
    handoff = runtime / "handoff.md" if layered else ROOT / "agents" / "handoff.md"
    for required in (agents_dir, skills_dir, manifest, handoff):
        if not required.exists():
            return fail(
                f"missing {required.relative_to(ROOT)} — run scripts/sync-agents.py first"
            )

    lib_dist.reset_dist(DIST, PLUGIN)

    lib_dist.write_json(
        DIST / ".grok-plugin" / "marketplace.json",
        {
            "name": "workcell",
            "owner": {"name": "Anvil Palamattam", "url": "https://anvilpalamattam.com"},
            "metadata": {
                "description": "Staged marketplace for the Workcell Grok Build plugin."
            },
            "plugins": [
                {
                    "name": "workcell",
                    "source": "./plugins/workcell",
                    "description": "Workcell: multi-agent planning, building, review, and docs for Grok Build.",
                    "category": "Developer Tools",
                }
            ],
        },
    )

    (PLUGIN / ".claude-plugin").mkdir()
    shutil.copy2(manifest, PLUGIN / ".claude-plugin" / "plugin.json")
    shutil.copy2(handoff, PLUGIN / "handoff.md")

    if layered:
        shutil.copytree(runtime, PLUGIN / "runtime", symlinks=False)

    staged_agents = PLUGIN / "agents"
    staged_agents.mkdir()
    for source in sorted(agents_dir.glob("*.md")):
        text = source.read_text(encoding="utf-8")
        if layered:
            text = text.replace("](../runtime/handoff.md)", "](../handoff.md)")
        else:
            text = text.replace("](../../skills/", "](../skills/")
        (staged_agents / source.name).write_text(text, encoding="utf-8")

    shutil.copytree(
        skills_dir,
        PLUGIN / "skills",
        symlinks=False,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    version = manifest_data.get("version", "0.1.0")

    digest = lib_dist.compute_tree_digest(PLUGIN)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lib_dist.write_json(
        PLUGIN / ".workcell-stamp.json",
        {
            "name": "workcell",
            "version": version,
            "builtAt": now,
            "sourceRoot": "harnesses/grok" if layered else "plugins/grok",
            "contentDigest": digest,
        },
    )

    agents = len(list(staged_agents.glob("*.md")))
    skills = len([p for p in (PLUGIN / "skills").iterdir() if p.is_dir()])
    print(f"staged {DIST.relative_to(ROOT)}: {agents} agents, {skills} skills")
    return 0


if __name__ == "__main__":
    sys.exit(main())
