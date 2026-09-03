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
HARNESS_OWNED_SKILLS = frozenset({"claude", "codex", "agy"})
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
HARNESS_LABELS = {
    "claude": "Claude Code",
    "codex": "Codex",
    "agy": "Antigravity",
    "grok": "Grok Build",
}


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


def validate_required(root: Path, registry: dict, kind: str) -> None:
    models = _models(root) if kind == "agents" else {}
    for entry in registry[kind]:
        name = entry["name"]
        for harness in HARNESSES:
            resolved = _resolved_model(models, name, harness)
            for value in entry["requiredValues"][harness]:
                if value == "body":
                    if kind == "skills":
                        if harness in HARNESS_OWNED_SKILLS:
                            path = (
                                root
                                / "harnesses"
                                / harness
                                / "skills"
                                / name
                                / "SKILL.md"
                            )
                            if not path.is_file() and _scoped_owners(
                                root, registry, harness, name
                            ):
                                continue
                        else:
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


def _same_mode(actual: int, expected: int) -> bool:
    """Compare only what generation controls: whether the file is executable.

    A tracked file's read/write bits come from the umask of whoever checked the
    repository out — 664 under 0002, 644 under 0022 — so comparing full modes
    makes `--check` report drift on a clean checkout of half the machines it runs
    on. The executable bit is the only mode difference the generator means.
    """
    return bool(actual & 0o111) == bool(expected & 0o111)


def _generated_notice(text: str, harness: str) -> str:
    marker = f"<!-- generated harness-owned procedure: {HARNESS_LABELS[harness]} -->\n"
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


# How each harness launches a foreign one. The four generated bodies differ here
# and only here: the catalogue of target commands is the shared skill's, because
# this skill exists to reach *every* other harness, not the one that owns the copy.
LAUNCH_FRAMING = {
    "claude": (
        "Run the target harness's command below with the Bash tool. For a long job start it in "
        "the background and read the captured output when the process exits, rather than polling "
        "it while it runs."
    ),
    "codex": (
        "Run the target harness's command below in the shell. Point it at the working directory "
        "with its own directory flag instead of changing directory first, and capture the result "
        "to a file so the output survives the run."
    ),
    "agy": (
        "Run the target harness's command below as a terminal command. It starts a separate "
        "external process: it is not an Antigravity subagent and nothing in this session manages "
        "its lifetime, so wait for it and collect its output yourself."
    ),
    "grok": (
        "Run the target harness's command below in the shell. No hook reports a foreign process "
        "back to this session, so capture its exit status and its output explicitly before you "
        "report anything about it."
    ),
}


def _other_harness_body(harness: str, source: str) -> str:
    """One harness's copy of the shared skill: its framing, the shared catalogue.

    The frontmatter description is carried through verbatim because it is the
    explicit-only trigger a harness reads to decide whether to load the skill at
    all, and the body below it is the shared source's, so an edit to
    `skills/use-other-harness/SKILL.md` reaches all four copies.
    """
    if not source.startswith("---\n"):
        raise GenerationError("skills/use-other-harness/SKILL.md: no frontmatter")
    end = source.index("\n---\n", 4)
    front = source[4:end]
    body = source[end + len("\n---\n") :].lstrip("\n")
    # The shared title is replaced by the owning harness's; everything the source
    # says about the four targets stays as written.
    lines = body.splitlines(keepends=True)
    if lines and lines[0].startswith("# "):
        body = "".join(lines[1:]).lstrip("\n")
    return (
        f"---\n{front}\n---\n\n"
        f"# Use another harness from {HARNESS_LABELS[harness]}\n\n"
        f"{LAUNCH_FRAMING[harness]}\n\n"
        f"{body}"
    )


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
                    if harness in HARNESS_OWNED_SKILLS:
                        continue
                    decoded = content.decode("utf-8")
                    text = _generated_notice(
                        _other_harness_body(harness, decoded)
                        if name == "use-other-harness"
                        else decoded,
                        harness,
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
            if harness not in {"codex", "grok"}:
                text = _generated_notice(text, harness)
            text = text.rstrip() + _limitations(entry, harness)
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
            (root / "scripts/hooks", Path("scripts")),
            (root / "agents/handoff.md", Path("handoff.md")),
        ),
        "codex": (
            (root / "scripts/hooks", Path("scripts")),
            (root / "agents/models.json", Path("models.json")),
            (root / "agents/handoff.md", Path("handoff.md")),
        ),
        "agy": ((root / "agents/handoff.md", Path("handoff.md")),),
        "grok": (
            (root / "scripts/hooks", Path("scripts")),
            (root / "agents/handoff.md", Path("handoff.md")),
        ),
    }
    for harness in HARNESSES:
        base = root / "harnesses" / harness / "runtime"
        desired[base / "contracts.json"] = GeneratedFile(registry_bytes)
        for source, relative in shared[harness]:
            _add_tree(desired, source, base / relative)
        runtime_docs = [
            (
                root / "docs/adr/0007-primary-agent-is-a-pure-orchestrator.md",
                Path("docs/adr/0007-primary-agent-is-a-pure-orchestrator.md"),
            ),
            (
                root / "docs/adr/0010-readme-diagrams-are-generated-svg.md",
                Path("docs/adr/0010-readme-diagrams-are-generated-svg.md"),
            ),
            (root / "docs/workspaces.md", Path("docs/workspaces.md")),
        ]
        if harness == "claude":
            runtime_docs.extend(
                [
                    (
                        root / "docs/models/claude-fable-5-1/prompting.md",
                        Path("docs/models/claude-fable-5-1/prompting.md"),
                    ),
                    (
                        root / "docs/models/claude-opus-5/prompting.md",
                        Path("docs/models/claude-opus-5/prompting.md"),
                    ),
                    (
                        root / "docs/models/claude-sonnet-5/prompting.md",
                        Path("docs/models/claude-sonnet-5/prompting.md"),
                    ),
                ]
            )
        elif harness == "codex":
            runtime_docs.append(
                (
                    root / "docs/models/gpt-5.6-sol/prompting.md",
                    Path("docs/models/gpt-5.6-sol/prompting.md"),
                )
            )
        elif harness == "agy":
            runtime_docs.extend(
                [
                    (
                        root / "docs/models/gemini-3.7-flash/prompting.md",
                        Path("docs/models/gemini-3.7-flash/prompting.md"),
                    ),
                ]
            )
        elif harness == "grok":
            runtime_docs.append(
                (
                    root / "docs/models/grok-4.6/prompting.md",
                    Path("docs/models/grok-4.6/prompting.md"),
                )
            )
        for source, relative in runtime_docs:
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


def _link_key(document: Path, target: str) -> tuple[str, str]:
    """Identify a document by its path within its skill, so depth does not matter.

    The same file sits at `skills/jj/references/x.md` in the source, deeper again
    under a staged plugin root, and deeper still under an agent that owns the
    skill. Everything from the innermost `skills/` component down is identical in
    all three, which is a far tighter key than the bare file name.
    """
    parts = document.parts
    if "skills" in parts:
        start = len(parts) - 1 - parts[::-1].index("skills")
        return ("/".join(parts[start + 1 :]), target)
    return (document.name, target)


def inherited_link_breaks(root: Path) -> set[tuple[str, str]]:
    """Link breaks the shared sources already carry, keyed by skill-relative path.

    Vendored upstream documents (`skills/jj/references/`) cite pages this
    repository does not vendor, and copying them cannot repair a link that was
    never whole. Everything else must resolve inside the harness family, so the
    generated trees are allowed exactly the breaks their sources already had and
    no others.
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
                inherited.add(_link_key(document, target))
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
            if _link_key(document, target) in inherited:
                continue
            failures.append(f"{document}:{line}: unresolved link {target}")
    return failures


def is_harness_test_path(path: Path, root: Path = ROOT) -> bool:
    """Whether `path` sits inside a sanctioned harness-owned tests/ directory.

    Plan09 sanctions harnesses/<h>/{agents,skills,runtime}/tests/ (and everything
    beneath it) directly under each family root as harness-owned, non-generated
    content.
    """
    if path.is_absolute():
        try:
            rel = path.relative_to(root)
        except ValueError:
            try:
                rel = path.resolve().relative_to(root.resolve())
            except ValueError:
                return False
    else:
        if path.parts and path.parts[0] == "harnesses":
            rel = path
        else:
            try:
                rel = path.resolve().relative_to(root.resolve())
            except ValueError:
                return False

    return (
        len(rel.parts) >= 4
        and rel.parts[0] == "harnesses"
        and rel.parts[1] in HARNESSES
        and rel.parts[2] in ("agents", "skills", "runtime")
        and rel.parts[3] == "tests"
    )


HARNESS_OWNED_RUNTIME: dict[str, tuple[Path, ...]] = {
    "claude": (
        Path(".claude-plugin"),
        Path("hooks"),
        Path("capabilities.json"),
    ),
    "codex": (
        Path(".codex-plugin"),
        Path("hooks"),
        Path("capabilities.json"),
    ),
    "agy": (
        Path("plugin.json"),
        Path("hooks.json"),
        Path("rules"),
        Path("capabilities.json"),
    ),
    "grok": (
        Path(".claude-plugin"),
        Path("capabilities.json"),
    ),
}


def is_harness_owned_skill_path(path: Path, root: Path = ROOT) -> bool:
    """Whether `path` is a sanctioned harness-owned SKILL.md file (#154).

    Plan09 Wave 5 introduces Claude-owned skill bodies authored directly under
    harnesses/claude/skills/<name>/SKILL.md as harness-owned sources that
    generation and sync must never overwrite, prune, or complain about.
    """
    if path.is_absolute():
        try:
            rel = path.relative_to(root)
        except ValueError:
            try:
                rel = path.resolve().relative_to(root.resolve())
            except ValueError:
                return False
    else:
        if path.parts and path.parts[0] == "harnesses":
            rel = path
        else:
            try:
                rel = path.resolve().relative_to(root.resolve())
            except ValueError:
                return False

    return (
        len(rel.parts) == 5
        and rel.parts[0] == "harnesses"
        and rel.parts[1] in HARNESS_OWNED_SKILLS
        and rel.parts[2] == "skills"
        and rel.parts[4] == "SKILL.md"
    )


def is_harness_owned_path(path: Path, root: Path = ROOT) -> bool:
    """Whether `path` is a sanctioned harness-owned, non-generated file or directory.

    Plan09 sanctions:
    - harnesses/<h>/{agents,skills,runtime}/tests/ (and everything beneath it)
    - harness-owned runtime manifests, hooks, and capabilities (#156).
    - Claude-owned skill bodies authored under harnesses/claude/skills/<name>/SKILL.md (#154).
    """
    if is_harness_test_path(path, root):
        return True
    if is_harness_owned_skill_path(path, root):
        return True

    if path.is_absolute():
        try:
            rel = path.relative_to(root)
        except ValueError:
            try:
                rel = path.resolve().relative_to(root.resolve())
            except ValueError:
                return False
    else:
        if path.parts and path.parts[0] == "harnesses":
            rel = path
        else:
            try:
                rel = path.resolve().relative_to(root.resolve())
            except ValueError:
                return False

    if (
        len(rel.parts) >= 4
        and rel.parts[0] == "harnesses"
        and rel.parts[1] in HARNESSES
        and rel.parts[2] == "runtime"
    ):
        harness = rel.parts[1]
        runtime_rel = Path(*rel.parts[3:])
        for owned in HARNESS_OWNED_RUNTIME.get(harness, ()):
            if runtime_rel == owned or owned in runtime_rel.parents:
                return True

    return False


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
        if (path.is_file() or path.is_symlink())
        and not is_harness_owned_path(path, root)
        and not is_harness_owned_skill_path(path, root)
    }
    expected_dirs = set(family_roots)
    for path in desired:
        parent = path.parent
        while parent not in expected_dirs:
            expected_dirs.add(parent)
            parent = parent.parent
    if kind == "skills":
        for harness in HARNESS_OWNED_SKILLS:
            for entry in registry["skills"]:
                skill_dir = root / "harnesses" / harness / "skills" / entry["name"]
                parent = skill_dir
                while parent not in expected_dirs:
                    expected_dirs.add(parent)
                    parent = parent.parent
    existing_dirs = {
        path
        for family in family_roots
        if family.exists()
        for path in family.rglob("*")
        if path.is_dir() and not is_harness_owned_path(path, root)
    }
    drifted: list[Path] = []
    for path, generated in desired.items():
        if (
            not path.is_file()
            or path.is_symlink()
            or path.read_bytes() != generated.content
            or not _same_mode(_mode(path), generated.mode)
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
            (
                path
                for path in family.rglob("*")
                if path.is_dir() and not is_harness_owned_path(path, root)
            ),
            reverse=True,
        ):
            if not any(directory.iterdir()):
                directory.rmdir()
    print(f"{len(drifted)} file(s) updated" if drifted else "already in sync")
    return 0


def parse_invocation(content: str) -> str | None:
    """Extract invocation string from document content if present."""
    match = re.search(r"Invocation:\s*`?([^`\n\r]+)`?", content)
    return match.group(1).strip() if match else None


def parse_ordered_gates(content: str) -> list[str] | None:
    """Extract ordered gate list from document content if section is present."""
    if "## Ordered Gates" not in content:
        return None
    section = content.split("## Ordered Gates", 1)[1].split("\n## ", 1)[0]
    return [
        gate.strip()
        for gate in re.findall(r"^\s*\d+\.\s*\*\*([^*]+)\*\*", section, re.MULTILINE)
    ]


def parse_handoff_schema(content: str) -> str | None:
    """Extract anvil.agent-handoff schema identifier from document content if present."""
    match = re.search(r"anvil\.agent-handoff/[a-zA-Z0-9_.-]+", content)
    return match.group(0) if match else None


def check_use_other_harness_invariants(content: str) -> list[str]:
    """Verify invariants for use-other-harness document."""
    errors: list[str] = []
    normalized = re.sub(r"\s+", " ", content)
    prohibition = "Do not guess a model or effort, and do not pick a harness on the user's behalf."
    if prohibition not in normalized:
        errors.append(
            "expected mandatory prohibition against guessing model/effort, got 'missing'"
        )
    if "silently fall back" in normalized.lower():
        errors.append("silent fallback is strictly prohibited")
    return errors


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
                skill_path = root / "harnesses" / harness / "skills" / name / "SKILL.md"
                content = skill_path.read_text(encoding="utf-8")
                if harness in HARNESS_OWNED_SKILLS:
                    act_inv = parse_invocation(content)
                    exp_inv = entry.get("invocation")
                    if act_inv is None or act_inv != (exp_inv or "").strip():
                        errors.append(f"{harness}/skills/{name}: invocation drift")
                    exp_gates = entry.get("orderedGates", [])
                    doc_gates = parse_ordered_gates(content)
                    if (
                        doc_gates is None
                        or len(doc_gates) < len(exp_gates)
                        or doc_gates[: len(exp_gates)] != exp_gates
                    ):
                        errors.append(f"{harness}/skills/{name}: gate order drift")
                    if name != "jj":
                        act_handoff = parse_handoff_schema(content)
                        if act_handoff is None or act_handoff != entry.get(
                            "handoffSchema"
                        ):
                            errors.append(f"{harness}/skills/{name}: handoff drift")
                if name == "use-other-harness":
                    for err in check_use_other_harness_invariants(content):
                        errors.append(f"{harness}/skills/{name}: {err}")
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
            else:
                content = path.read_text(encoding="utf-8")
                act_handoff = parse_handoff_schema(content)
                if act_handoff is None or act_handoff != entry.get("handoffSchema"):
                    errors.append(f"{path.relative_to(root)}: handoff drift")
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
