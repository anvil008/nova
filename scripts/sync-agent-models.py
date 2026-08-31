#!/usr/bin/env python3
"""Apply agents/models.json to every agent's frontmatter.

One place decides which model and thinking level each agent runs at, per harness.
This writes those values into the agent definitions; `--check` reports drift
without touching anything, which is what CI and the installer run.

  scripts/sync-agent-models.py            # write
  scripts/sync-agent-models.py --check    # exit 1 on drift, print what differs
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "agents" / "models.json"

CLAUDE_EFFORT = ("low", "medium", "high", "xhigh")
CODEX_EFFORT = ("low", "medium", "high", "xhigh", "max")
AGY_MODELS = ("pro", "flash", "inherit")
HARNESSES = frozenset({"claude", "codex", "agy", "grok"})

# Codex has no per-agent model surface in its plugin manifest. The staged plugin
# therefore generates an explicit spawn_agent routing contract from this manifest;
# profiles remain useful for launching one role manually from the CLI.
CODEX_PROFILE_PREFIX = "workcell-"
CODEX_PROFILE_MARKER = "# managed by workcell: scripts/sync-agent-models.py"
LEGACY_CODEX_PROFILE_PREFIX = "workcell-"
LEGACY_CODEX_PROFILE_MARKER = "# managed by workcell: scripts/sync-agent-models.py"

# Per harness: the frontmatter key each knob is written under, and the key an
# inserted block is placed after. Harnesses that lack a knob simply omit it.
HARNESS_KEYS = {
    "claude": {"model": "model", "effort": "effort"},
    "codex": {"model": "model", "effort": "model_reasoning_effort"},
    "agy": {"model": "model"},
    "grok": {"model": "model"},
}

# Where a missing key is inserted, most specific anchor first. The frontmatter
# stays readable instead of accumulating keys at the end.
ANCHORS = {
    "claude": ("tools", "description", "name"),
    "codex": ("description", "name"),
    "agy": ("commandExecutionPolicy", "subagent", "mainAgent", "description", "name"),
    "grok": ("description", "name"),
}


class SyncError(Exception):
    pass


def codex_profile_path(codex_home: Path, agent: str) -> Path:
    return codex_home / f"{CODEX_PROFILE_PREFIX}{agent}.config.toml"


def render_codex_profile(agent: str, values: dict) -> str:
    lines = [
        CODEX_PROFILE_MARKER,
        f"# Run this agent with: codex --profile {CODEX_PROFILE_PREFIX}{agent}",
        f'model = "{values["model"]}"',
    ]
    if "effort" in values:
        lines.append(f'model_reasoning_effort = "{values["effort"]}"')
    return "\n".join(lines) + "\n"


def write_codex_profiles(
    codex_home: Path, defaults: dict, agents: dict, check: bool
) -> list[str]:
    """Emit one profile per agent. Never clobbers a file we did not write."""
    drift: list[str] = []
    if not codex_home.is_dir():
        return drift
    if not check:
        for path in sorted(
            codex_home.glob(f"{LEGACY_CODEX_PROFILE_PREFIX}*.config.toml")
        ):
            if LEGACY_CODEX_PROFILE_MARKER in path.read_text(encoding="utf-8"):
                path.unlink()
                print(f"removed legacy profile {path}")
    for agent, spec in sorted(agents.items()):
        values = resolve(defaults, spec, "codex")
        validate(agent, "codex", values)
        path = codex_profile_path(codex_home, agent)
        desired = render_codex_profile(agent, values)
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            if CODEX_PROFILE_MARKER not in existing:
                raise SyncError(
                    f"{path} exists and is not ours; refusing to overwrite it"
                )
            if existing == desired:
                continue
        if check:
            drift.append(f"{path}: {values}")
        else:
            path.write_text(desired, encoding="utf-8")
            print(f"wrote {path}")
    return drift


def remove_codex_profiles(codex_home: Path) -> int:
    """Remove only the profiles we wrote; leave the user's own alone."""
    removed = 0
    if not codex_home.is_dir():
        return removed
    prefixes_and_markers = (
        (CODEX_PROFILE_PREFIX, CODEX_PROFILE_MARKER),
        (LEGACY_CODEX_PROFILE_PREFIX, LEGACY_CODEX_PROFILE_MARKER),
    )
    for prefix, marker in prefixes_and_markers:
        for path in sorted(codex_home.glob(f"{prefix}*.config.toml")):
            if marker in path.read_text(encoding="utf-8"):
                path.unlink()
                print(f"removed {path}")
                removed += 1
    return removed


def agent_path(agent: str, harness: str) -> Path:
    if harness == "agy":
        return ROOT / "agents" / "agy" / agent / "agent.md"
    return ROOT / "agents" / harness / f"{agent}.md"


def load_manifest() -> tuple[dict, dict]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    defaults = data.get("defaults", {})
    agents = {k: v for k, v in data.get("agents", {}).items() if not k.startswith("_")}
    unknown_defaults = set(defaults) - HARNESSES
    if unknown_defaults:
        raise SyncError(f"defaults: unknown harness {min(unknown_defaults)}")
    for agent, spec in agents.items():
        unknown = {key for key in spec if not key.startswith("_")} - HARNESSES
        if unknown:
            raise SyncError(f"{agent}/{min(unknown)}: unknown harness")
    return defaults, agents


def resolve(defaults: dict, spec: dict, harness: str) -> dict:
    """Merge an agent's per-harness overrides onto the harness defaults."""
    merged = dict(defaults.get(harness, {}))
    merged.update(
        {k: v for k, v in spec.get(harness, {}).items() if not k.startswith("_")}
    )
    return {key: merged[key] for key in ("model", "effort") if key in merged}


def validate(agent: str, harness: str, values: dict) -> None:
    model, effort = values.get("model"), values.get("effort")
    if harness == "agy" and model not in AGY_MODELS:
        raise SyncError(
            f"{agent}/{harness}: model {model!r} must be one of {AGY_MODELS}"
        )
    if harness == "claude" and effort is not None and effort not in CLAUDE_EFFORT:
        raise SyncError(
            f"{agent}/{harness}: effort {effort!r} must be one of {CLAUDE_EFFORT}"
        )
    if harness == "codex" and effort is not None and effort not in CODEX_EFFORT:
        raise SyncError(
            f"{agent}/{harness}: effort {effort!r} must be one of {CODEX_EFFORT}"
        )
    if not model:
        raise SyncError(f"{agent}/{harness}: no model resolved")


def split_frontmatter(text: str, path: Path) -> tuple[list[str], str]:
    if not text.startswith("---\n"):
        raise SyncError(f"{path}: no frontmatter")
    end = text.find("\n---\n", 3)
    if end == -1:
        raise SyncError(f"{path}: unterminated frontmatter")
    return text[4:end].split("\n"), text[end + 5 :]


def is_top_level_key(line: str, key: str) -> bool:
    """Top-level keys start at column 0; list items and nested keys are indented."""
    return line.startswith(f"{key}:") or line.rstrip() == f"{key}:"


def apply(lines: list[str], harness: str, values: dict) -> list[str]:
    keys = HARNESS_KEYS[harness]
    desired = {
        keys[knob]: values[knob]
        for knob in ("model", "effort")
        if knob in keys and knob in values
    }
    managed = set(keys.values())

    # Replace in place where the key already exists; drop the rest so a knob a
    # harness no longer supports cannot linger.
    result: list[str] = []
    seen: set[str] = set()
    for line in lines:
        matched = next((k for k in managed if is_top_level_key(line, k)), None)
        if matched is None:
            result.append(line)
            continue
        if matched in desired:
            result.append(f"{matched}: {desired[matched]}")
            seen.add(matched)
        # A managed key with no desired value is removed.

    missing = [k for k in desired if k not in seen]
    if not missing:
        return result

    # Insert after the most specific anchor present, preserving key order.
    index = None
    for anchor in ANCHORS[harness]:
        for position, line in enumerate(result):
            if is_top_level_key(line, anchor):
                # Skip the anchor's continuation lines (a YAML block or list).
                end = position + 1
                while end < len(result) and (
                    result[end].startswith((" ", "\t", "-"))
                    or result[end].strip() == ""
                ):
                    end += 1
                index = end
                break
        if index is not None:
            break
    if index is None:
        index = len(result)

    ordered = [k for k in (keys.get("model"), keys.get("effort")) if k in missing]
    return result[:index] + [f"{k}: {desired[k]}" for k in ordered] + result[index:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="report drift, write nothing"
    )
    parser.add_argument(
        "--codex-profiles",
        action="store_true",
        help="also emit $CODEX_HOME/workcell-<agent>.config.toml for manually launching a role",
    )
    parser.add_argument(
        "--remove-codex-profiles",
        action="store_true",
        help="remove the profiles this script wrote, and nothing else",
    )
    parser.add_argument(
        "--codex-home",
        default=None,
        help="override $CODEX_HOME (default: $CODEX_HOME or ~/.codex)",
    )
    args = parser.parse_args()

    codex_home = Path(
        args.codex_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex"
    ).expanduser()

    if args.remove_codex_profiles:
        removed = remove_codex_profiles(codex_home)
        print(
            f"{removed} codex profile(s) removed"
            if removed
            else "no codex profiles to remove"
        )
        return 0

    defaults, agents = load_manifest()
    drifted: list[str] = []
    written = 0

    for agent, spec in sorted(agents.items()):
        for harness in ("claude", "codex", "agy"):
            path = agent_path(agent, harness)
            if not path.exists():
                raise SyncError(f"{agent}: {path.relative_to(ROOT)} is missing")
            values = resolve(defaults, spec, harness)
            validate(agent, harness, values)

            original = path.read_text(encoding="utf-8")
            lines, body = split_frontmatter(original, path)
            updated = (
                "---\n" + "\n".join(apply(lines, harness, values)) + "\n---\n" + body
            )
            if updated == original:
                continue
            relative = path.relative_to(ROOT)
            if args.check:
                drifted.append(f"{relative}: {values}")
            else:
                path.write_text(updated, encoding="utf-8")
                print(f"synced {relative}: {values}")
                written += 1

    if args.codex_profiles:
        drifted.extend(write_codex_profiles(codex_home, defaults, agents, args.check))

    if args.check:
        if drifted:
            print("agent frontmatter has drifted from agents/models.json:")
            for entry in drifted:
                print(f"- {entry}")
            print("run scripts/sync-agent-models.py to fix")
            return 1
        print("agent models in sync")
        return 0

    print(f"{written} file(s) updated" if written else "already in sync")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SyncError as error:
        print(f"sync-agent-models: {error}", file=sys.stderr)
        sys.exit(2)
