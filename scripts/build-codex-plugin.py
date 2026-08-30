#!/usr/bin/env python3
"""Stage the Codex plugin as a real directory tree.

Codex installs a plugin by *copying* it into
$CODEX_HOME/plugins/cache/<marketplace>/<plugin>/<version>/ — and it drops any
symlink that points outside the plugin root. The wrapper in plugins/codex/ links
back to ../../skills and ../../agents, so every one of those links was silently
discarded and the installed plugin contained nothing but a manifest. Claude Code
follows the same links, which is why only Codex was affected.

So Codex gets a staged copy instead of a link farm:

    dist/codex/
    ├── .agents/plugins/marketplace.json
    └── plugins/workcell/
        ├── .codex-plugin/plugin.json     name, version, description, author, skills, interface
        ├── hooks/hooks.json              the default location Codex discovers on its own
        └── skills/
            ├── <every skill in skills/>
            └── agent-<name>/             each agent, as a skill

Two further constraints, both verified against OpenAI's own `plugin-creator`
validator rather than assumed:

  * `author` and `interface` are REQUIRED; a manifest without them fails
    validation, which is why the previous three-field manifest was invalid.
  * `hooks` is NOT an accepted manifest key even though the published spec lists
    it. Codex discovers ./hooks/hooks.json by itself, so the file moves and the
    key stays out.

Codex has no plugin-level agent concept at all — no `agents` key in the manifest,
and a skill's agents/openai.yaml carries UI metadata only. Agents therefore ship
as skills named `agent-<name>`, which is the one surface that reaches the model.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "plugins" / "codex"
SKILLS = ROOT / "skills"
AGENTS = ROOT / "agents" / "codex"
OUT = ROOT / "dist" / "codex"

PLUGIN = "workcell"
MARKETPLACE = "workcell-local"

# Agent names collide with skill names (docs, research, planner, deploy), so they
# are namespaced. The prefix is also what tells a reader which are which.
AGENT_PREFIX = "agent-"

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


class BuildError(Exception):
    pass


def frontmatter_field(text: str, field: str, path: Path) -> str:
    match = FRONTMATTER.match(text)
    if not match:
        raise BuildError(f"{path}: no frontmatter")
    found = re.search(rf"(?m)^{field}: (.+)$", match.group(1))
    if not found:
        raise BuildError(f"{path}: no `{field}` in frontmatter")
    return found.group(1).strip()


def plugin_manifest(version: str) -> dict:
    return {
        "name": PLUGIN,
        "version": version,
        "description": "Multi-agent planning, building, review, and docs for Codex.",
        "author": {"name": "Foundry Zero"},
        "keywords": ["agents", "planning", "tdd", "code-review", "orchestration"],
        "skills": "./skills/",
        "interface": {
            "displayName": "Workcell",
            "shortDescription": "Plan, build, and review with isolated agents",
            "longDescription": (
                "Turns a goal into a reviewable plan, has one agent write each task's "
                "tests and a different one make them pass, and gates integration on "
                "mechanical evidence rather than an agent's claim of success."
            ),
            "developerName": "Foundry Zero",
            "category": "Developer Tools",
            "capabilities": ["Interactive", "Write"],
            "defaultPrompt": [
                "Use $new-feature to plan and build this change.",
                "Use $code-analysis to hunt defects in this package.",
                "Use $debug to reproduce and fix this stack trace.",
            ],
        },
    }


def agent_skill(name: str, text: str, path: Path) -> tuple[str, str]:
    """Wrap one agent definition as a Codex skill plus its openai.yaml."""
    description = frontmatter_field(text, "description", path)
    body = FRONTMATTER.sub("", text).lstrip("\n")
    skill = f"---\nname: {AGENT_PREFIX}{name}\ndescription: {description}\n---\n\n{body}"

    display = name.replace("-", " ").title()
    short = description.split(".")[0].strip()
    if len(short) > 64:
        short = short[:61].rstrip() + "..."
    agent_yaml = (
        "interface:\n"
        f'  display_name: "{display}"\n'
        f'  short_description: "{short}"\n'
        f'  default_prompt: "Use ${AGENT_PREFIX}{name} for exactly one assigned unit of work."\n'
        "policy:\n"
        "  allow_implicit_invocation: true\n"
    )
    return skill, agent_yaml


def validate_sources() -> tuple[str, list[Path], list[tuple[Path, str]]]:
    """Validate every source before replacing OUT, so failures leave no partial tree."""
    if not SOURCE.is_dir():
        raise BuildError(f"missing plugin source {SOURCE.relative_to(ROOT)}")
    manifest_path = SOURCE / ".codex-plugin" / "plugin.json"
    version = json.loads(manifest_path.read_text(encoding="utf-8")).get("version", "0.1.0")

    skill_dirs = sorted(path for path in SKILLS.iterdir() if path.is_dir())
    for skill_dir in skill_dirs:
        if not (skill_dir / "SKILL.md").is_file():
            raise BuildError(f"{skill_dir.relative_to(ROOT)}: no SKILL.md")

    agents = []
    for agent in sorted(AGENTS.glob("*.md")):
        text = agent.read_text(encoding="utf-8")
        frontmatter_field(text, "name", agent)
        frontmatter_field(text, "description", agent)
        agents.append((agent, text))
    return version, skill_dirs, agents


def build() -> Path:
    version, skill_dirs, agent_sources = validate_sources()

    if OUT.exists():
        shutil.rmtree(OUT)
    plugin_root = OUT / "plugins" / PLUGIN
    (plugin_root / ".codex-plugin").mkdir(parents=True)
    skills_out = plugin_root / "skills"
    skills_out.mkdir()

    (plugin_root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(plugin_manifest(version), indent=2) + "\n", encoding="utf-8"
    )

    hooks = SOURCE / "hooks" / "hooks.json"
    if hooks.is_file():
        (plugin_root / "hooks").mkdir()
        shutil.copy2(hooks, plugin_root / "hooks" / "hooks.json")

    # Real copies, never links: a symlink out of the plugin root does not survive
    # the install, and one that resolves inside it would be dereferenced anyway.
    skills = 0
    for skill_dir in skill_dirs:
        shutil.copytree(skill_dir, skills_out / skill_dir.name, symlinks=False)
        skills += 1

    agents = 0
    for agent, text in agent_sources:
        skill_text, agent_yaml = agent_skill(agent.stem, text, agent)
        target = skills_out / f"{AGENT_PREFIX}{agent.stem}"
        (target / "agents").mkdir(parents=True)
        (target / "SKILL.md").write_text(skill_text, encoding="utf-8")
        (target / "agents" / "openai.yaml").write_text(agent_yaml, encoding="utf-8")
        agents += 1

    (OUT / ".agents" / "plugins").mkdir(parents=True)
    (OUT / ".agents" / "plugins" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": MARKETPLACE,
                "interface": {"displayName": "Workcell (Local)"},
                "plugins": [
                    {
                        "name": PLUGIN,
                        "source": {"source": "local", "path": f"./plugins/{PLUGIN}"},
                        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                        "category": "Developer Tools",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    escaping = [p for p in plugin_root.rglob("*") if p.is_symlink()]
    if escaping:
        raise BuildError(
            "staged tree still contains symlinks, which Codex drops on install: "
            + ", ".join(str(p.relative_to(OUT)) for p in escaping)
        )

    print(f"staged {skills} skills and {agents} agent-skills into {OUT.relative_to(ROOT)}")
    return OUT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-root", action="store_true", help="print the marketplace root only")
    args = parser.parse_args()
    out = build()
    if args.print_root:
        print(out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BuildError as error:
        print(f"build-codex-plugin: {error}", file=sys.stderr)
        sys.exit(2)
