#!/usr/bin/env python3
"""Stage the Claude Code plugin as a real directory tree.

Claude Code installs through a durable command-source marketplace that runs
stage-workcell to materialize dist/claude/workcell/ as a self-contained,
symlink-free tree from the runtime, agents, and skills in harnesses/claude/.

    dist/claude/
    └── workcell/
        ├── .claude-plugin/plugin.json
        ├── hooks/hooks.json
        ├── scripts/                  real copies of runtime/scripts/*
        ├── agents/                   real copies of agents/*.md
        └── skills/                   real copies of skills/*, sans caches
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import lib_dist

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "claude"
STAGED = DIST / "workcell"
HARNESS = ROOT / "harnesses" / "claude"
PLUGIN_NAME = "workcell"


class BuildError(Exception):
    pass


def validate_sources() -> tuple[str, Path]:
    """Ensure all required sources exist and extract the plugin version."""
    if not HARNESS.is_dir():
        raise BuildError(f"missing plugin source {HARNESS.relative_to(ROOT)}")

    source = HARNESS
    runtime = source / "runtime"
    manifest_path = runtime / ".claude-plugin" / "plugin.json"
    if not manifest_path.is_file():
        raise BuildError(f"missing manifest {manifest_path.relative_to(ROOT)}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise BuildError(
            f"invalid JSON in {manifest_path.relative_to(ROOT)}: {err}"
        ) from err

    version = manifest.get("version", "0.6.0")

    hooks_path = runtime / "hooks" / "hooks.json"
    if not hooks_path.is_file():
        raise BuildError(f"missing hooks manifest {hooks_path.relative_to(ROOT)}")

    agents_dir = source / "agents"
    if not agents_dir.is_dir():
        raise BuildError(f"missing agents directory {agents_dir.relative_to(ROOT)}")

    skills_dir = source / "skills"
    if not skills_dir.is_dir():
        raise BuildError(f"missing skills directory {skills_dir.relative_to(ROOT)}")

    scripts_dir = runtime / "scripts"
    if not scripts_dir.is_dir():
        raise BuildError(f"missing scripts directory {scripts_dir.relative_to(ROOT)}")

    return version, source


def build() -> Path:
    version, source = validate_sources()
    runtime = source / "runtime"

    lib_dist.reset_dist(DIST, STAGED)

    # .claude-plugin
    (STAGED / ".claude-plugin").mkdir()
    shutil.copy2(
        runtime / ".claude-plugin" / "plugin.json",
        STAGED / ".claude-plugin" / "plugin.json",
    )

    # hooks
    shutil.copytree(runtime / "hooks", STAGED / "hooks", symlinks=False)

    # agents (dereferencing symlinks)
    shutil.copytree(
        source / "agents",
        STAGED / "agents",
        symlinks=False,
        ignore=lib_dist.ignore_root_tests(source / "agents"),
    )
    shutil.copy2(runtime / "handoff.md", STAGED / "handoff.md")
    for agent in (STAGED / "agents").glob("*.md"):
        text = agent.read_text(encoding="utf-8").replace(
            "](../runtime/handoff.md)", "](../handoff.md)"
        )
        agent.write_text(text, encoding="utf-8")

    # skills (dereferencing symlinks, ignoring python cache files)
    shutil.copytree(
        source / "skills",
        STAGED / "skills",
        symlinks=False,
        ignore=lib_dist.ignore_root_tests(source / "skills"),
    )

    # scripts (dereferencing symlinks, ignoring python cache files)
    shutil.copytree(
        runtime / "scripts",
        STAGED / "scripts",
        symlinks=False,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    # Only what the staged skills link to. The manifest, hooks and hook scripts
    # already sit at the plugin root, which is where Claude reads them and where
    # ${CLAUDE_PLUGIN_ROOT} resolves; copying them again under runtime/ would ship
    # a second, unread copy of every hook script.
    shutil.copytree(
        runtime,
        STAGED / "runtime",
        symlinks=False,
        ignore=lib_dist.ignore_root_tests(
            runtime, ".claude-plugin", "hooks", "scripts"
        ),
    )

    # .workcell-stamp.json
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lib_dist.write_json(
        STAGED / ".workcell-stamp.json",
        {
            "name": PLUGIN_NAME,
            "version": version,
            "builtAt": now,
            "sourceRoot": "harnesses/claude",
        },
    )

    # Validate no symlinks survived
    escaping = [p for p in DIST.rglob("*") if p.is_symlink()]
    if escaping:
        raise BuildError(
            "staged tree still contains symlinks: "
            + ", ".join(str(p.relative_to(DIST)) for p in escaping)
        )

    agents = len(list((STAGED / "agents").glob("*.md")))
    skills = len([p for p in (STAGED / "skills").iterdir() if p.is_dir()])
    print(f"staged {DIST.relative_to(ROOT)}: {agents} agents, {skills} skills")
    return DIST


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-root", action="store_true", help="print the staged plugin root only"
    )
    args = parser.parse_args()
    out = build()
    if args.print_root:
        print(out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BuildError as error:
        print(f"build-claude-plugin: {error}", file=sys.stderr)
        sys.exit(2)
