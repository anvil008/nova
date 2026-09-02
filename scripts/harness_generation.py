#!/usr/bin/env python3
"""Generate and verify harness-owned agents, skills, and runtime inputs."""

from __future__ import annotations

import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "contracts" / "harness-contracts.json"
HARNESSES = ("claude", "codex", "agy", "grok")
KINDS = ("skills", "agents")
EXPECTED_SKILLS = frozenset(
    {
        "build",
        "code-analysis",
        "code-refactor",
        "code-review",
        "debug",
        "deploy",
        "docs",
        "jj",
        "new-feature",
        "perf",
        "plan",
        "repo-setup",
        "research",
        "review-fix-loop",
        "use-other-harness",
        "wiki",
    }
)
EXPECTED_AGENTS = frozenset(
    {
        "planner",
        "specifier",
        "builder",
        "reviewer",
        "integrator",
        "researcher",
        "documenter",
        "deployer",
        "debugger",
        "profiler",
    }
)
ENTRY_KEYS = {
    "name",
    "invocation",
    "orderedGates",
    "handoffSchema",
    "acceptanceOracle",
    "requiredValues",
    "optionalSurfaces",
}
TOP_KEYS = {"schemaVersion", "harnesses", "skills", "agents"}
OPTIONAL_KEYS = {"harness", "name", "supported", "limitationNote"}
NAME = re.compile(r"^[a-z][a-z0-9-]*$")
LINK = re.compile(r"\]\(([^)\s]+?)(?:\s+\"[^\"]*\")?\)")
EXTERNAL = ("http://", "https://", "mailto:", "#", "<")
# Skills a harness ships inside one of its agents instead of the globally
# invocable family must say so in the registry, on every owning agent.
GLOBAL_SKILL_SURFACE = "global-skill-invocation"


class GenerationError(Exception):
    pass


@dataclass(frozen=True)
class GeneratedFile:
    content: bytes
    mode: int = 0o644


def fail(path: str, message: str) -> None:
    raise GenerationError(f"{path}: {message}")


def _unknown_keys(value: dict, allowed: set[str], path: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        fail(f"{path}.{min(unknown)}", "unknown key")


def load_registry(root: Path = ROOT) -> dict:
    path = root / "contracts" / "harness-contracts.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise GenerationError(f"{path.relative_to(root)}: missing registry") from error
    except json.JSONDecodeError as error:
        raise GenerationError(f"{path.relative_to(root)}: {error}") from error
    if not isinstance(data, dict):
        fail("$", "must be an object")
    _unknown_keys(data, TOP_KEYS, "$")
    if data.get("schemaVersion") != 1:
        fail("$.schemaVersion", "must be 1")
    if data.get("harnesses") != list(HARNESSES):
        fail("$.harnesses", f"must equal {list(HARNESSES)}")
    for kind in KINDS:
        entries = data.get(kind)
        if not isinstance(entries, list):
            fail(f"$.{kind}", "must be an array")
        seen: set[str] = set()
        for index, entry in enumerate(entries):
            entry_path = f"$.{kind}[{index}]"
            if not isinstance(entry, dict):
                fail(entry_path, "must be an object")
            _unknown_keys(entry, ENTRY_KEYS, entry_path)
            missing = ENTRY_KEYS - set(entry)
            if missing:
                fail(f"{entry_path}.{min(missing)}", "missing required key")
            name = entry["name"]
            if not isinstance(name, str) or not NAME.fullmatch(name):
                fail(f"{entry_path}.name", "must be a lowercase kebab-case name")
            if name in seen:
                fail(f"{entry_path}.name", f"duplicate {kind[:-1]} name {name!r}")
            seen.add(name)
            invocation = entry["invocation"]
            if not isinstance(invocation, str) or not invocation.strip():
                fail(f"{entry_path}.invocation", "must be a non-empty string")
            if kind == "skills" and invocation != f"/workcell:{name}":
                fail(f"{entry_path}.invocation", f"must be /workcell:{name}")
            gates = entry["orderedGates"]
            if (
                not isinstance(gates, list)
                or not gates
                or not all(isinstance(gate, str) and gate.strip() for gate in gates)
            ):
                fail(f"{entry_path}.orderedGates", "must be a non-empty string array")
            if entry["handoffSchema"] != "anvil.agent-handoff/v1":
                fail(f"{entry_path}.handoffSchema", "must be anvil.agent-handoff/v1")
            if (
                not isinstance(entry["acceptanceOracle"], str)
                or not entry["acceptanceOracle"].strip()
            ):
                fail(f"{entry_path}.acceptanceOracle", "must be a non-empty string")
            required = entry["requiredValues"]
            if not isinstance(required, dict) or set(required) != set(HARNESSES):
                fail(
                    f"{entry_path}.requiredValues",
                    f"must define exactly {', '.join(HARNESSES)}",
                )
            for harness, values in required.items():
                if (
                    not isinstance(values, list)
                    or not values
                    or not all(value in {"body", "model", "effort"} for value in values)
                ):
                    fail(
                        f"{entry_path}.requiredValues.{harness}",
                        "must be a non-empty array of body, model, or effort",
                    )
            optionals = entry["optionalSurfaces"]
            if not isinstance(optionals, list):
                fail(f"{entry_path}.optionalSurfaces", "must be an array")
            for optional_index, surface in enumerate(optionals):
                optional_path = f"{entry_path}.optionalSurfaces[{optional_index}]"
                if not isinstance(surface, dict):
                    fail(optional_path, "must be an object")
                _unknown_keys(surface, OPTIONAL_KEYS, optional_path)
                if set(surface) != OPTIONAL_KEYS:
                    fail(
                        optional_path,
                        "must define harness, name, supported, limitationNote",
                    )
                if surface["harness"] not in HARNESSES:
                    fail(f"{optional_path}.harness", "unknown harness")
                if not isinstance(surface["name"], str) or not surface["name"].strip():
                    fail(f"{optional_path}.name", "must be a non-empty string")
                if not isinstance(surface["supported"], bool):
                    fail(f"{optional_path}.supported", "must be a boolean")
                if (
                    not isinstance(surface["limitationNote"], str)
                    or not surface["limitationNote"].strip()
                ):
                    fail(
                        f"{optional_path}.limitationNote", "must be a non-empty string"
                    )
        expected = EXPECTED_SKILLS if kind == "skills" else EXPECTED_AGENTS
        if seen != expected:
            missing = sorted(expected - seen)
            unexpected = sorted(seen - expected)
            details = []
            if missing:
                details.append(f"missing {', '.join(missing)}")
            if unexpected:
                details.append(f"unexpected {', '.join(unexpected)}")
            fail(f"$.{kind}", "; ".join(details))
    return data


def _models(root: Path) -> dict:
    path = root / "agents" / "models.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GenerationError(f"agents/models.json: {error}") from error


def _resolved_model(models: dict, agent: str, harness: str) -> dict:
    values = dict(models.get("defaults", {}).get(harness, {}))
    spec = models.get("agents", {}).get(agent, {})
    if isinstance(spec, dict):
        override = spec.get(harness, {})
        if isinstance(override, dict):
            values.update(
                {
                    key: value
                    for key, value in override.items()
                    if not key.startswith("_")
                }
            )
    return values


def validate_required(root: Path, registry: dict, kind: str) -> None:
    models = _models(root) if kind == "agents" else {}
    for entry in registry[kind]:
        name = entry["name"]
        for harness in HARNESSES:
            resolved = _resolved_model(models, name, harness)
            for value in entry["requiredValues"][harness]:
                if value == "body":
                    if kind == "skills":
                        path = root / "skills" / name / "SKILL.md"
                    elif harness == "agy":
                        path = root / "agents" / "agy" / name / "agent.md"
                    else:
                        path = root / "agents" / harness / f"{name}.md"
                    if (
                        not path.is_file()
                        or not path.read_text(encoding="utf-8").strip()
                    ):
                        raise GenerationError(
                            f"missing required value: {harness}/{name}/{value} ({path.relative_to(root)})"
                        )
                elif (
                    not isinstance(resolved.get(value), str)
                    or not resolved[value].strip()
                ):
                    raise GenerationError(
                        f"missing required value: {harness}/{name}/{value}"
                    )
            if (
                kind == "agents"
                and harness == "grok"
                and resolved.get("model") != "grok-4.6"
            ):
                raise GenerationError(
                    f"agents/models.json: grok/{name}/model must resolve to grok-4.6"
                )


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _generated_notice(text: str, harness: str) -> str:
    label = {
        "claude": "Claude Code",
        "codex": "Codex",
        "agy": "Antigravity",
        "grok": "Grok Build",
    }[harness]
    marker = f"<!-- generated harness-owned procedure: {label} -->\n"
    if not text.startswith("---\n"):
        return marker + text
    end = text.find("\n---\n", 4)
    if end < 0:
        return marker + text
    split = end + len("\n---\n")
    return text[:split] + "\n" + marker + text[split:]


def _limitations(entry: dict, harness: str) -> str:
    notes = [
        surface["limitationNote"]
        for surface in entry["optionalSurfaces"]
        if surface["harness"] == harness and surface["supported"] is False
    ]
    if not notes:
        return ""
    return (
        "\n\n## Harness limitations (generated)\n\n"
        + "\n".join(f"- {note}" for note in notes)
        + "\n"
    )


def _other_harness_body(harness: str) -> str:
    commands = {
        "claude": 'claude -p "<task prompt>" --model <model> --effort <effort> --dangerously-skip-permissions',
        "codex": 'codex exec --cd <dir> -m <model> -c model_reasoning_effort="<effort>" --approve-for-me "<task prompt>"',
        "agy": 'agy -p "<task prompt>" --model <model> --effort <effort> --dangerously-skip-permissions',
        "grok": 'grok -p "<task prompt>" -m <model> --effort <effort> --always-approve',
    }
    names = {
        "claude": "Claude Code",
        "codex": "Codex",
        "agy": "Antigravity",
        "grok": "Grok Build",
    }
    return f"""---
name: use-other-harness
description: Run one explicitly requested foreign-harness leaf task in headless mode.
---

# Use another harness from {names[harness]}

Use this leaf capability only for an explicit user request for a different coding harness that
names the target harness, model, and effort. Never use it as an automatic router or for automatic
cross-harness routing. Ask for any missing value instead of guessing.

Run the target harness's native headless command in the requested workspace. For {names[harness]},
the compatible launch shape is:

```bash
{commands[harness]}
```

The foreign process performs one bounded job and returns its result. It must not orchestrate more
agents. Capture its exit status and output, then hand both back to the caller.
"""


def desired_skills(root: Path, registry: dict) -> dict[Path, GeneratedFile]:
    desired: dict[Path, GeneratedFile] = {}
    entries = {entry["name"]: entry for entry in registry["skills"]}
    for harness in HARNESSES:
        base = root / "harnesses" / harness / "skills"
        for name, entry in entries.items():
            if harness == "agy" and any(
                (root / "agents" / "agy" / agent / "skills" / name).exists()
                for agent in (item["name"] for item in registry["agents"])
            ):
                continue
            source = root / "skills" / name
            for path in source.rglob("*"):
                if (
                    not path.is_file()
                    or "__pycache__" in path.parts
                    or path.suffix == ".pyc"
                ):
                    continue
                relative = path.relative_to(source)
                content = path.read_bytes()
                try:
                    resource_text = content.decode("utf-8")
                except UnicodeDecodeError:
                    resource_text = ""
                if resource_text:
                    resource_text = resource_text.replace(
                        "](../../agents/handoff.md)",
                        "](../../runtime/handoff.md)",
                    ).replace("](../../docs/", "](../../runtime/docs/")
                    content = resource_text.encode("utf-8")
                if "agents/bodies/documenter.md" in resource_text:
                    replacement = {
                        "claude": "agents/documenter.md",
                        "codex": "skills/agent-documenter/SKILL.md",
                        "agy": "agents/documenter/agent.md",
                        "grok": "agents/documenter.md",
                    }[harness]
                    resource_text = resource_text.replace(
                        "agents/bodies/documenter.md", replacement
                    )
                    content = resource_text.encode("utf-8")
                if relative == Path("SKILL.md"):
                    text = (
                        _other_harness_body(harness)
                        if name == "use-other-harness"
                        else _generated_notice(content.decode("utf-8"), harness)
                    )
                    text = text.rstrip() + _limitations(entry, harness)
                    text = text.rstrip() + "\n"
                    content = text.encode("utf-8")
                desired[base / name / relative] = GeneratedFile(content, _mode(path))
    return desired


def desired_agents(root: Path, registry: dict) -> dict[Path, GeneratedFile]:
    desired: dict[Path, GeneratedFile] = {}
    for harness in HARNESSES:
        base = root / "harnesses" / harness / "agents"
        for entry in registry["agents"]:
            name = entry["name"]
            if harness == "agy":
                source = root / "agents" / "agy" / name / "agent.md"
                target = base / name / "agent.md"
                text = source.read_text(encoding="utf-8").replace(
                    "](../../../skills/", "](../../skills/"
                )
                text = text.replace(
                    "](../../handoff.md)", "](../../runtime/handoff.md)"
                )
            else:
                source = root / "agents" / harness / f"{name}.md"
                target = base / f"{name}.md"
                text = source.read_text(encoding="utf-8")
                if harness in {"claude", "grok"}:
                    text = text.replace("](../../skills/", "](../skills/")
                text = text.replace("](../handoff.md)", "](../runtime/handoff.md)")
            text = _generated_notice(text, harness).rstrip() + _limitations(
                entry, harness
            )
            desired[target] = GeneratedFile(text.encode("utf-8"), _mode(source))
            if harness == "agy":
                owned_root = root / "agents" / "agy" / name / "skills"
                if owned_root.is_dir():
                    for skill_link in owned_root.iterdir():
                        if not skill_link.exists():
                            continue
                        for resource in skill_link.resolve().rglob("*"):
                            if (
                                resource.is_file()
                                and "__pycache__" not in resource.parts
                            ):
                                relative = resource.relative_to(skill_link.resolve())
                                desired[
                                    base / name / "skills" / skill_link.name / relative
                                ] = GeneratedFile(
                                    resource.read_bytes(), _mode(resource)
                                )
    return desired


def _add_tree(desired: dict[Path, GeneratedFile], source: Path, target: Path) -> None:
    if not source.exists():
        raise GenerationError(f"{source.relative_to(ROOT)}: missing runtime source")
    if source.is_file():
        desired[target] = GeneratedFile(source.read_bytes(), _mode(source))
        return
    for path in source.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            desired[target / path.relative_to(source)] = GeneratedFile(
                path.read_bytes(), _mode(path)
            )


def desired_runtime(root: Path, registry: dict) -> dict[Path, GeneratedFile]:
    desired: dict[Path, GeneratedFile] = {}
    registry_bytes = (
        json.dumps({"contract": registry}, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    shared = {
        "claude": (
            (root / "plugins/claude/.claude-plugin", Path(".claude-plugin")),
            (root / "plugins/claude/hooks", Path("hooks")),
            (root / "scripts/hooks", Path("scripts")),
            (root / "agents/handoff.md", Path("handoff.md")),
        ),
        "codex": (
            (root / "plugins/codex/.codex-plugin", Path(".codex-plugin")),
            (root / "plugins/codex/hooks", Path("hooks")),
            (root / "agents/models.json", Path("models.json")),
            (root / "agents/handoff.md", Path("handoff.md")),
        ),
        "agy": (
            (root / "plugins/agy/plugin.json", Path("plugin.json")),
            (root / "plugins/agy/hooks.json", Path("hooks.json")),
            (root / "plugins/agy/rules", Path("rules")),
            (root / "agents/handoff.md", Path("handoff.md")),
        ),
        "grok": (
            (root / "plugins/grok/.claude-plugin", Path(".claude-plugin")),
            (root / "agents/handoff.md", Path("handoff.md")),
        ),
    }
    for harness in HARNESSES:
        base = root / "harnesses" / harness / "runtime"
        desired[base / "contracts.json"] = GeneratedFile(registry_bytes)
        for source, relative in shared[harness]:
            _add_tree(desired, source, base / relative)
        for source, relative in (
            (
                root / "docs/adr/0007-primary-agent-is-a-pure-orchestrator.md",
                Path("docs/adr/0007-primary-agent-is-a-pure-orchestrator.md"),
            ),
            (
                root / "docs/adr/0010-readme-diagrams-are-generated-svg.md",
                Path("docs/adr/0010-readme-diagrams-are-generated-svg.md"),
            ),
            (root / "docs/workspaces.md", Path("docs/workspaces.md")),
        ):
            _add_tree(desired, source, base / relative)
    return desired


def _unresolved_links(document: Path) -> list[tuple[int, str]]:
    """Relative Markdown links in one document whose target does not exist."""
    try:
        text = document.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    broken: list[tuple[int, str]] = []
    for match in LINK.finditer(text):
        target = match.group(1)
        if target.startswith(EXTERNAL):
            continue
        path = target.split("#", 1)[0]
        if not path:
            continue
        if not (document.parent / path).exists():
            broken.append((text.count("\n", 0, match.start()) + 1, target))
    return broken


def inherited_link_breaks(root: Path) -> set[tuple[str, str]]:
    """Link breaks the shared sources already carry, keyed by file name and target.

    Vendored upstream documents (`skills/jj/references/`) cite pages this
    repository does not vendor, and copying them cannot repair a link that was
    never whole. Everything else must resolve inside the harness family, so the
    generated trees are allowed exactly the breaks their sources already had and
    no others. The file name is the key because the same document is copied to a
    different depth in every family.
    """
    inherited: set[tuple[str, str]] = set()
    for base in (root / "skills", root / "agents", root / "docs", root / "plugins"):
        if not base.is_dir():
            continue
        for document in base.rglob("*.md"):
            # agents/bodies/ holds generator templates, never a shipped document:
            # their links are written for the position sync-agents.py expands them
            # into, so a break there is not one a staged tree may inherit.
            if "__pycache__" in document.parts or "bodies" in document.parts:
                continue
            for _, target in _unresolved_links(document):
                inherited.add((document.name, target))
    return inherited


def link_failures(tree: Path, inherited: set[tuple[str, str]]) -> list[str]:
    """Every link in `tree` that neither resolves nor was broken at the source.

    Run this against a *staged* tree. The generated family under `harnesses/<h>`
    is an intermediate: Codex ships each agent as a `skills/agent-<name>/` skill,
    one level deeper than `harnesses/codex/agents/`, so its agent links only reach
    their targets once the stager has placed them.
    """
    failures: list[str] = []
    for document in sorted(tree.rglob("*.md")):
        if "__pycache__" in document.parts:
            continue
        for line, target in _unresolved_links(document):
            if (document.name, target) in inherited:
                continue
            failures.append(f"{document}:{line}: unresolved link {target}")
    return failures


def _family_roots(root: Path, kind: str) -> list[Path]:
    roots = [root / "harnesses" / harness / kind for harness in HARNESSES]
    roots.extend(root / "harnesses" / harness / "runtime" for harness in HARNESSES)
    return roots


def sync(kind: str, check: bool = False, diff: bool = False, root: Path = ROOT) -> int:
    if kind not in KINDS:
        raise GenerationError(f"unknown artifact kind {kind!r}")
    registry = load_registry(root)
    validate_required(root, registry, kind)
    desired = (
        desired_agents(root, registry)
        if kind == "agents"
        else desired_skills(root, registry)
    )
    desired.update(desired_runtime(root, registry))
    family_roots = _family_roots(root, kind)
    existing = {
        path
        for family in family_roots
        if family.exists()
        for path in family.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    expected_dirs = set(family_roots)
    for path in desired:
        parent = path.parent
        while parent not in expected_dirs:
            expected_dirs.add(parent)
            parent = parent.parent
    existing_dirs = {
        path
        for family in family_roots
        if family.exists()
        for path in family.rglob("*")
        if path.is_dir()
    }
    drifted: list[Path] = []
    for path, generated in desired.items():
        if (
            not path.is_file()
            or path.is_symlink()
            or path.read_bytes() != generated.content
            or _mode(path) != generated.mode
        ):
            drifted.append(path)
    orphans = sorted(existing - set(desired))
    orphan_dirs = sorted(existing_dirs - expected_dirs)
    if check:
        if drifted or orphans or orphan_dirs:
            print(f"{kind} generation drift:")
            for path in sorted(drifted):
                print(f"- {path.relative_to(root)}")
            for path in orphans:
                print(f"- {path.relative_to(root)} (orphan)")
            for path in orphan_dirs:
                print(f"- {path.relative_to(root)} (orphan directory)")
            if diff:
                print("run the matching sync command to regenerate exact outputs")
            return 1
        print(f"{len(registry[kind])} {kind} in sync across {len(HARNESSES)} harnesses")
        return 0

    for path in orphans:
        path.unlink()
    for directory in sorted(
        orphan_dirs, key=lambda path: len(path.parts), reverse=True
    ):
        if directory.exists() and not any(directory.iterdir()):
            directory.rmdir()
    for path, generated in desired.items():
        if path in drifted:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_symlink():
                path.unlink()
            path.write_bytes(generated.content)
            path.chmod(generated.mode)
            print(f"wrote {path.relative_to(root)}")
    for family in family_roots:
        family.mkdir(parents=True, exist_ok=True)
    for family in family_roots:
        for directory in sorted(
            (path for path in family.rglob("*") if path.is_dir()), reverse=True
        ):
            if not any(directory.iterdir()):
                directory.rmdir()
    print(f"{len(drifted)} file(s) updated" if drifted else "already in sync")
    return 0


def _scoped_owners(root: Path, registry: dict, harness: str, skill: str) -> list[str]:
    """Agents of `harness` that carry `skill` inside themselves instead of globally."""
    return [
        entry["name"]
        for entry in registry["agents"]
        if (
            root
            / "harnesses"
            / harness
            / "agents"
            / entry["name"]
            / "skills"
            / skill
            / "SKILL.md"
        ).is_file()
    ]


def _declares_agent_scope(registry: dict, agent: str, harness: str) -> bool:
    entry = next(item for item in registry["agents"] if item["name"] == agent)
    return any(
        surface["harness"] == harness
        and surface["name"] == GLOBAL_SKILL_SURFACE
        and surface["supported"] is False
        for surface in entry["optionalSurfaces"]
    )


def check_parity(root: Path = ROOT) -> int:
    registry = load_registry(root)
    expected = (
        json.dumps({"contract": registry}, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    errors: list[str] = []
    counts: list[str] = []
    for harness in HARNESSES:
        carrier = root / "harnesses" / harness / "runtime" / "contracts.json"
        if not carrier.is_file() or carrier.read_bytes() != expected:
            errors.append(str(carrier.relative_to(root)))
        globally_invocable = 0
        scoped: list[str] = []
        for entry in registry["skills"]:
            name = entry["name"]
            owners = _scoped_owners(root, registry, harness, name)
            staged_globally = (
                root / "harnesses" / harness / "skills" / name / "SKILL.md"
            ).is_file()
            if staged_globally and owners:
                errors.append(
                    f"{harness}/skills/{name}: offered globally and owned by "
                    f"{', '.join(owners)}; a skill is one or the other"
                )
            elif staged_globally:
                globally_invocable += 1
            elif not owners:
                errors.append(f"{harness}/skills/{name}")
            else:
                # A skill counted but not staged is the lie this check exists to
                # prevent: every owning agent has to declare the missing global
                # surface in the registry, note and all.
                undeclared = [
                    owner
                    for owner in owners
                    if not _declares_agent_scope(registry, owner, harness)
                ]
                if undeclared:
                    errors.append(
                        f"{harness}/skills/{name}: owned by {', '.join(undeclared)} "
                        f"without an unsupported {GLOBAL_SKILL_SURFACE} surface in "
                        "the registry"
                    )
                scoped.append(f"{name} is agent-owned by {', '.join(sorted(owners))}")
        for entry in registry["agents"]:
            path = (
                root / "harnesses" / harness / "agents" / entry["name"] / "agent.md"
                if harness == "agy"
                else root / "harnesses" / harness / "agents" / f"{entry['name']}.md"
            )
            if not path.is_file():
                errors.append(str(path.relative_to(root)))
        summary = (
            f"- {harness}: {globally_invocable} globally invocable skills, "
            f"{len(registry['agents'])} agents"
        )
        counts.append(summary + (f"; {'; '.join(scoped)}" if scoped else ""))
    if errors:
        print("contract parity drift:")
        for error in sorted(errors):
            print(f"- {error}")
        return 1
    print(
        "contract parity holds for "
        f"{len(registry['skills'])} skills and {len(registry['agents'])} agents "
        f"across {len(HARNESSES)} harnesses"
    )
    for summary in counts:
        print(summary)
    return 0
