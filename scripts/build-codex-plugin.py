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
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import lib_dist

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "plugins" / "codex"
SKILLS = ROOT / "skills"
AGENTS = ROOT / "agents" / "codex"
MODELS = ROOT / "agents" / "models.json"
HARNESS = ROOT / "harnesses" / "codex"
OUT = ROOT / "dist" / "codex"

PLUGIN = "workcell"
MARKETPLACE = "workcell"

# Agent names collide with skill names (planner), so they
# are namespaced. The prefix is also what tells a reader which are which.
AGENT_PREFIX = "agent-"
CODEX_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


class BuildError(Exception):
    pass


def codex_routing(models_path: Path = MODELS) -> dict[str, dict[str, str]]:
    """Resolve the runtime model and effort for every Codex specialist."""
    data = json.loads(models_path.read_text(encoding="utf-8"))
    agents = data.get("agents", {})
    routing: dict[str, dict[str, str]] = {}
    for name, spec in sorted(agents.items()):
        if name.startswith("_"):
            continue
        if "codex" not in spec or not isinstance(spec.get("codex"), dict):
            raise BuildError(f"{models_path}: {name} has no codex profile")
        codex_spec = spec["codex"]
        model = codex_spec.get("model")
        effort = codex_spec.get("effort")
        if not isinstance(model, str) or not model.strip():
            raise BuildError(f"{models_path}: {name}/codex has no model")
        if not isinstance(effort, str) or not effort.strip():
            raise BuildError(f"{models_path}: {name}/codex has no effort")
        if effort not in CODEX_EFFORTS:
            raise BuildError(
                f"{models_path}: {name}/codex effort {effort!r} "
                f"must be one of {sorted(CODEX_EFFORTS)}"
            )
        routing[name] = {"model": model.strip(), "effort": effort}
    if not routing:
        raise BuildError(f"{models_path}: no Codex agent routes")
    return routing


def codex_dispatch_contract(routing: dict[str, dict[str, str]]) -> str:
    """Instructions that turn models.json into real spawn_agent overrides."""
    rows = "\n".join(
        f"- `{name}`: `model={values['model']}`, `reasoning_effort={values['effort']}`"
        for name, values in routing.items()
    )
    return f"""

## Codex specialist routing (generated)

This table is generated from `agents/models.json`; never infer or inherit a specialist's model.
Whenever this skill dispatches a Workcell specialist with `spawn_agent`, pass both the exact
`model` and `reasoning_effort` below. Model overrides cannot use a full-history fork: set
`fork_turns` to `none` or the smallest positive number that carries the required context, and put
the complete assignment and acceptance criteria in `message`. If the configured model or effort
is unavailable, stop and report the route that failed; do not silently fall back to the parent.

{rows}
"""


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


def agent_skill(
    name: str, text: str, path: Path, dispatch_contract: str
) -> tuple[str, str]:
    """Wrap one agent definition as a Codex skill plus its openai.yaml."""
    description = frontmatter_field(text, "description", path)
    body = FRONTMATTER.sub("", text).lstrip("\n")
    body = body.replace("](../runtime/handoff.md)", "](../../handoff.md)")
    body = body.replace("](../skills/", "](../../skills/")
    skill = (
        f"---\nname: {AGENT_PREFIX}{name}\ndescription: {description}\n---\n\n"
        f"{body.rstrip()}\n{dispatch_contract}"
    )

    display = name.replace("-", " ").title()
    short = description.split(".")[0].strip()
    if len(short) > 64:
        short = short[:61].rstrip() + "..."
    agent_yaml = (
        "interface:\n"
        f'  displayName: "{display}"\n'
        f'  shortDescription: "{short}"\n'
        f'  defaultPrompt: "Use ${AGENT_PREFIX}{name} for exactly one assigned unit of work."\n'
        "policy:\n"
        "  allow_implicit_invocation: true\n"
    )
    return skill, agent_yaml


def content_digest(tree: Path) -> str:
    """Compute a deterministic 12-hex-character content digest of a directory tree."""
    hasher = hashlib.sha256()
    for file_path in sorted(
        [p for p in tree.rglob("*") if p.is_file()],
        key=lambda p: p.relative_to(tree).as_posix(),
    ):
        rel_path = file_path.relative_to(tree).as_posix()
        file_sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
        hasher.update(f"{rel_path}:{file_sha}\n".encode())
    return hasher.hexdigest()[:12]


def validate_sources() -> tuple[
    str, list[Path], list[tuple[Path, str]], dict[str, dict[str, str]]
]:
    """Validate every source before replacing OUT, so failures leave no partial tree."""
    if not HARNESS.is_dir():
        raise BuildError(f"missing harness directory {HARNESS.relative_to(ROOT)}")
    source = HARNESS / "runtime"
    skills_root = HARNESS / "skills"
    agents_root = HARNESS / "agents"
    models_path = source / "models.json"
    if not source.is_dir():
        raise BuildError(f"missing plugin source {source.relative_to(ROOT)}")
    manifest_path = source / ".codex-plugin" / "plugin.json"
    version = json.loads(manifest_path.read_text(encoding="utf-8")).get(
        "version", "0.6.0"
    )

    skill_dirs = sorted(
        path for path in skills_root.iterdir() if path.is_dir() and path.name != "tests"
    )
    for skill_dir in skill_dirs:
        if not (skill_dir / "SKILL.md").is_file():
            raise BuildError(f"{skill_dir.relative_to(ROOT)}: no SKILL.md")

    agents = []
    for agent in sorted(agents_root.glob("*.md")):
        text = agent.read_text(encoding="utf-8")
        frontmatter_field(text, "name", agent)
        frontmatter_field(text, "description", agent)
        agents.append((agent, text))
    return version, skill_dirs, agents, codex_routing(models_path)


def build() -> Path:
    version, skill_dirs, agent_sources, routing = validate_sources()
    dispatch_contract = codex_dispatch_contract(routing)

    plugin_root = lib_dist.reset_dist(OUT, OUT / "plugins" / PLUGIN)
    skills_out = plugin_root / "skills"
    skills_out.mkdir()

    layered = True
    runtime = HARNESS / "runtime"
    hooks = runtime / "hooks" / "hooks.json"
    if hooks.is_file():
        (plugin_root / "hooks").mkdir()
        shutil.copy2(hooks, plugin_root / "hooks" / "hooks.json")

    if layered:
        shutil.copytree(
            runtime,
            plugin_root / "runtime",
            symlinks=False,
            ignore=lib_dist.ignore_root_tests(
                runtime, "tests", ".codex-plugin", "hooks"
            ),
        )
        handoff = runtime / "handoff.md"
        if handoff.is_file():
            shutil.copy2(handoff, plugin_root / "handoff.md")
        agents_out = plugin_root / "agents"
        agents_out.mkdir(parents=True, exist_ok=True)
        for agent, _ in agent_sources:
            shutil.copy2(agent, agents_out / agent.name)

    # Real copies, never links: a symlink out of the plugin root does not survive
    # the install, and one that resolves inside it would be dereferenced anyway.
    skills = 0
    for skill_dir in skill_dirs:
        shutil.copytree(
            skill_dir,
            skills_out / skill_dir.name,
            symlinks=False,
            ignore=lib_dist.ignore_root_tests(skill_dir),
        )
        skill_path = skills_out / skill_dir.name / "SKILL.md"
        skill_text = skill_path.read_text(encoding="utf-8")
        sep = "\n" if skill_text.endswith("\n") else "\n\n"
        skill_path.write_text(f"{skill_text}{sep}{dispatch_contract}", encoding="utf-8")
        skills += 1

    agents = 0
    for agent, text in agent_sources:
        skill_text, agent_yaml = agent_skill(agent.stem, text, agent, dispatch_contract)
        target = skills_out / f"{AGENT_PREFIX}{agent.stem}"
        (target / "agents").mkdir(parents=True)
        (target / "SKILL.md").write_text(skill_text, encoding="utf-8")
        (target / "agents" / "openai.yaml").write_text(agent_yaml, encoding="utf-8")
        agents += 1

    base_semver = version.split("+")[0]
    digest = content_digest(plugin_root)
    staged_version = f"{base_semver}+codex.{digest}"

    lib_dist.write_json(
        plugin_root / ".codex-plugin" / "plugin.json",
        plugin_manifest(staged_version),
    )

    lib_dist.write_json(
        OUT / ".agents" / "plugins" / "marketplace.json",
        {
            "name": MARKETPLACE,
            "interface": {"displayName": "Workcell (Local)"},
            "plugins": [
                {
                    "name": PLUGIN,
                    "source": {"source": "local", "path": f"./plugins/{PLUGIN}"},
                    "policy": {
                        "installation": "AVAILABLE",
                        "authentication": "ON_INSTALL",
                    },
                    "category": "Developer Tools",
                }
            ],
        },
    )

    escaping = [p for p in plugin_root.rglob("*") if p.is_symlink()]
    if escaping:
        raise BuildError(
            "staged tree still contains symlinks, which Codex drops on install: "
            + ", ".join(str(p.relative_to(OUT)) for p in escaping)
        )

    print(
        f"staged {skills} skills and {agents} agent-skills into {OUT.relative_to(ROOT)}"
    )
    return OUT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-root", action="store_true", help="print the marketplace root only"
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
        print(f"build-codex-plugin: {error}", file=sys.stderr)
        sys.exit(2)
