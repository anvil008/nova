#!/usr/bin/env python3
"""Generate every agent definition from one body per agent.

An agent exists three times — agents/claude/<n>.md, agents/codex/<n>.md, and
agents/agy/<n>/agent.md — with an identical body and per-harness frontmatter.
Writing those by hand is how the three copies drift apart. This makes the body
the single source and derives the rest:

  agents/bodies/<n>.md          the shared body, canonical
  agents/agents.json            per-harness structure: description and tools
  agents/gates/codex-<n>.md     a Codex-only section, spliced in before `## Skills`
  agents/models.json            model and thinking level (owned by sync-agent-models.py)

  scripts/sync-agents.py            # write
  scripts/sync-agents.py --check    # exit 1 on drift, print what differs

To add an agent: write agents/bodies/<n>.md, add an entry to agents/agents.json
and agents/models.json, and run this. Editing a generated file directly is the
one thing that does not work — the next run overwrites it.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "agents"
MANIFEST = AGENTS / "agents.json"
MODELS = AGENTS / "models.json"
BODIES = AGENTS / "bodies"
GATES = AGENTS / "gates"

HARNESSES = ("claude", "codex", "agy", "grok")

# A body is shared, but harnesses genuinely differ: Codex spawns with
# `spawn_agent`, Antigravity with `invoke_subagent`, and only Claude wires
# formatting hooks. Two escapes keep one body honest about that.
#
#   {{token}}                    replaced from `vars` (global, overridable per agent)
#   <!-- only:codex -->...<!-- end -->   whole lines kept for one harness only
TOKEN = re.compile(r"\{\{([a-zA-Z][a-zA-Z0-9_]*)\}\}")
ONLY_OPEN = re.compile(r"^<!-- only:([a-z,]+) -->$")
ONLY_CLOSE = "<!-- end -->"


def apply_conditionals(text: str, harness: str, where: str) -> str:
    kept, skipping, depth = [], False, 0
    for line in text.split("\n"):
        stripped = line.strip()
        opened = ONLY_OPEN.match(stripped)
        if opened:
            if depth:
                raise SyncError(f"{where}: nested `only:` block")
            depth, skipping = 1, harness not in opened.group(1).split(",")
            continue
        if stripped == ONLY_CLOSE:
            if not depth:
                raise SyncError(f"{where}: `<!-- end -->` with no `only:` block")
            depth, skipping = 0, False
            continue
        if not skipping:
            kept.append(line)
    if depth:
        raise SyncError(f"{where}: unterminated `only:` block")
    return "\n".join(kept)


def apply_vars(text: str, harness: str, variables: dict, where: str) -> str:
    def replace(match: re.Match) -> str:
        key = match.group(1)
        if key not in variables:
            raise SyncError(f"{where}: unknown token {{{{{key}}}}}")
        value = variables[key]
        if harness not in value:
            raise SyncError(f"{where}: token {{{{{key}}}}} has no value for {harness}")
        return value[harness]

    return TOKEN.sub(replace, text)


def variables_for(manifest: dict, entry: dict) -> dict:
    merged = dict(manifest.get("vars", {}))
    merged.update(entry.get("vars", {}))
    return merged


class SyncError(Exception):
    pass


try:
    from harness_generation import GenerationError as LayeredGenerationError
except ImportError:
    # Compatibility for the long-standing hermetic unit fixture that copies
    # only this wrapper and agents/. Production repositories always carry the
    # shared generator beside the wrapper.
    LayeredGenerationError = SyncError


def agent_path(agent: str, harness: str) -> Path:
    if harness == "agy":
        return AGENTS / "agy" / agent / "agent.md"
    return AGENTS / harness / f"{agent}.md"


def resolve_models(models: dict, agent: str, harness: str) -> dict:
    """Model and thinking level stay owned by agents/models.json, so the two
    scripts agree by construction instead of overwriting each other."""
    merged = dict(models.get("defaults", {}).get(harness, {}))
    spec = models.get("agents", {}).get(agent, {})
    merged.update(
        {k: v for k, v in spec.get(harness, {}).items() if not k.startswith("_")}
    )
    return merged


def frontmatter(
    agent: str, harness: str, entry: dict, models: dict, variables: dict
) -> list[str]:
    """Key order is fixed per harness so a regeneration is byte-stable."""
    tuned = resolve_models(models, agent, harness)
    description = apply_vars(
        entry["description"], harness, variables, f"{agent}/{harness} description"
    )
    lines = [f"name: {agent}", f"description: {description}"]

    if harness == "claude":
        lines.append(f"tools: {entry['claude']['tools']}")
        if "disallowedTools" in entry["claude"]:
            lines.append(f"disallowedTools: {entry['claude']['disallowedTools']}")
        if "maxTurns" in entry["claude"]:
            lines.append(f"maxTurns: {entry['claude']['maxTurns']}")
        if "model" in tuned:
            lines.append(f"model: {tuned['model']}")
        if "effort" in tuned:
            lines.append(f"effort: {tuned['effort']}")
        if "mode" in tuned:
            lines.append(f"mode: {tuned['mode']}")
        return lines

    if harness == "codex":
        if "model" in tuned:
            lines.append(f"model: {tuned['model']}")
        if "effort" in tuned:
            lines.append(f"model_reasoning_effort: {tuned['effort']}")
        if entry["codex"].get("gates"):
            lines.append(
                '# Plugin hooks require trust via /hooks — see "Gates on Codex" in the body.'
            )
        return lines

    if harness == "grok":
        # Grok Build consumes the Claude plugin agent format. The pinned model comes
        # from agents/models.json, and read-only
        # agents are held to it via permission_mode rather than a tool list —
        # grok's per-agent tool vocabulary is not yet verified, a tool list we
        # cannot verify would be a lie, and permission_mode: plan is documented.
        if "model" in tuned:
            lines.append(f"model: {tuned['model']}")
        if entry["grok"].get("permission_mode"):
            lines.append(f"permission_mode: {entry['grok']['permission_mode']}")
        if entry["grok"].get("capability_mode"):
            lines.append(f"capability_mode: {entry['grok']['capability_mode']}")
        if entry["grok"].get("inputs"):
            lines.append("inputs:")
            for item in entry["grok"]["inputs"]:
                lines.append(f"  - name: {item['name']}")
                lines.append(f"    io_type: {item['io_type']}")
                lines.append(f"    required: {'true' if item['required'] else 'false'}")
                lines.append(f"    description: {item['description']}")
        if entry["grok"].get("outputs"):
            lines.append("outputs:")
            for item in entry["grok"]["outputs"]:
                lines.append(f"  - name: {item['name']}")
                lines.append(f"    io_type: {item['io_type']}")
                lines.append(f"    required: {'true' if item['required'] else 'false'}")
                lines.append(f"    description: {item['description']}")
        return lines

    lines.append("tools:")
    lines.extend(f"  - {tool}" for tool in entry["agy"]["tools"])
    lines.append("mainAgent: true")
    lines.append("subagent: true")
    if "model" in tuned:
        lines.append(f"model: {tuned['model']}")
    lines.append(f"commandExecutionPolicy: {entry['agy']['commandExecutionPolicy']}")
    return lines


def body_for(agent: str, harness: str, entry: dict, variables: dict) -> str:
    path = BODIES / f"{agent}.md"
    if not path.is_file():
        raise SyncError(f"{agent}: missing body {path.relative_to(ROOT)}")
    where = f"agents/bodies/{agent}.md ({harness})"
    body = apply_conditionals(path.read_text(encoding="utf-8"), harness, where)
    body = apply_vars(body, harness, variables, where)

    gates = entry["codex"].get("gates")
    if harness == "codex" and gates:
        snippet = GATES / f"{gates}.md"
        if not snippet.is_file():
            raise SyncError(
                f"{agent}: missing gates snippet {snippet.relative_to(ROOT)}"
            )
        block = snippet.read_text(encoding="utf-8").rstrip("\n") + "\n"
        marker = "## Skills\n"
        if marker in body:
            body = body.replace(marker, block + "\n" + marker, 1)
        else:
            body = body.rstrip("\n") + "\n\n" + block

    if harness == "agy":
        # agents/agy/<n>/agent.md sits one level deeper than the flat harness files.
        body = body.replace("](../../skills/", "](../../../skills/")
    return body


def render(agent: str, harness: str, entry: dict, models: dict, variables: dict) -> str:
    front = "\n".join(frontmatter(agent, harness, entry, models, variables))
    return f"---\n{front}\n---\n\n{body_for(agent, harness, entry, variables)}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="report drift, write nothing"
    )
    parser.add_argument(
        "--diff", action="store_true", help="with --check, show the differences"
    )
    args = parser.parse_args()

    # The shared engine owns strict contracts and harness-rooted tracked outputs.
    # Historical hermetic tests copy only this script plus agents/; retaining the
    # legacy root generation below keeps those fixtures meaningful without making
    # production stagers depend on the legacy tree.
    layered_sync = None
    try:
        from harness_generation import sync

        layered_sync = sync
        # Validate before legacy drift reporting so missing required values are
        # named as harness/artifact/value contract failures.
        from harness_generation import load_registry, validate_required

        validate_required(ROOT, load_registry(ROOT), "agents")
    except ImportError:
        pass

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    models = json.loads(MODELS.read_text(encoding="utf-8"))
    agents = {
        k: v for k, v in manifest.get("agents", {}).items() if not k.startswith("_")
    }
    if not agents:
        raise SyncError("agents.json declares no agents")

    drifted: list[str] = []
    written = 0
    for agent, entry in sorted(agents.items()):
        for harness in HARNESSES:
            path = agent_path(agent, harness)
            desired = render(
                agent, harness, entry, models, variables_for(manifest, entry)
            )
            current = path.read_text(encoding="utf-8") if path.exists() else None
            if current == desired:
                continue
            relative = path.relative_to(ROOT)
            if args.check:
                drifted.append(str(relative))
                if args.diff:
                    print(
                        "".join(
                            difflib.unified_diff(
                                (current or "").splitlines(keepends=True),
                                desired.splitlines(keepends=True),
                                fromfile=f"{relative} (on disk)",
                                tofile=f"{relative} (generated)",
                            )
                        )
                    )
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(desired, encoding="utf-8")
                print(f"wrote {relative}")
                written += 1

    # A definition with no entry is a file nothing generates: usually a rename
    # that left the old copy behind, which would then ship as a real agent.
    orphans = []
    for harness in HARNESSES:
        found = (
            {p.parent.name for p in (AGENTS / "agy").glob("*/agent.md")}
            if harness == "agy"
            else {p.stem for p in (AGENTS / harness).glob("*.md")}
        )
        orphans += [f"{harness}/{name}" for name in sorted(found - set(agents))]
    if orphans:
        raise SyncError(
            "agent definitions with no agents.json entry: " + ", ".join(orphans)
        )

    if args.check:
        if drifted:
            print("agent definitions have drifted from their bodies and agents.json:")
            for entry in drifted:
                print(f"- {entry}")
            print(
                "run scripts/sync-agents.py to regenerate (edit agents/bodies/, not the output)"
            )
            return 1
        if layered_sync is not None:
            layered_result = layered_sync("agents", check=True, diff=args.diff)
            if layered_result:
                return layered_result
        print(f"{len(agents)} agents in sync across {len(HARNESSES)} harnesses")
        return 0

    if layered_sync is not None:
        layered_result = layered_sync("agents", check=False, diff=args.diff)
        if layered_result:
            return layered_result
    print(
        f"{written} legacy file(s) updated"
        if written
        else "legacy outputs already in sync"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (SyncError, LayeredGenerationError) as error:
        print(f"sync-agents: {error}", file=sys.stderr)
        sys.exit(2)
