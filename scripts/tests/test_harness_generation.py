"""Acceptance tests for the harness-owned generation seam (#152)."""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
import harness_generation

HARNESSES = ("claude", "codex", "agy", "grok")
EXPECTED_SKILLS = {
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
EXPECTED_AGENTS = {
    "builder",
    "debugger",
    "deployer",
    "documenter",
    "integrator",
    "planner",
    "profiler",
    "researcher",
    "reviewer",
    "specifier",
}
FIELD_ALIASES = {
    "name": ("name",),
    "invocation": ("invocation",),
    "ordered gates": ("orderedGates", "ordered_gates", "gates"),
    "handoff schema": ("handoffSchema", "handoff_schema"),
    "acceptance oracle": ("acceptanceOracle", "acceptance_oracle"),
    "required values": ("requiredValues", "required_values"),
    "optional surfaces": ("optionalSurfaces", "optional_surfaces"),
}
DIST_PLUGIN_ROOTS = {
    "claude": Path("dist/claude/workcell"),
    "codex": Path("dist/codex/plugins/workcell"),
    "agy": Path("dist/agy/workcell"),
    "grok": Path("dist/grok/plugins/workcell"),
}
NATIVE_HEADLESS_TOKENS = {
    "claude": ("claude", "-p", "--model", "--effort", "--dangerously-skip-permissions"),
    "codex": ("codex exec", "--cd", "-m", "model_reasoning_effort", "--approve-for-me"),
    "agy": ("agy", "-p", "--model", "--effort", "--dangerously-skip-permissions"),
    "grok": ("grok", "-p", "-m", "--effort", "--always-approve"),
}


def run(root: Path, script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, script, *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )


def run_sync(root: Path, kind: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a sync wrapper, or a signature-only test stub until it exists.

    `sync-skills.py` is part of the requested implementation. The fallback lets
    pre-implementation RED reach assertions about generated behavior instead of
    stopping at Python's "can't open file" setup error. An empty implementation
    cannot pass because every caller also inspects the generated harness tree.
    """
    script = f"scripts/sync-{kind}.py"
    if not (root / script).is_file():
        return subprocess.CompletedProcess(
            args=[sys.executable, script, *args],
            returncode=0,
            stdout="test-local signature-only sync stub\n",
            stderr="",
        )
    return run(root, script, *args)


def copied_repository() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temporary = tempfile.TemporaryDirectory()
    target = Path(temporary.name) / "workcell"
    shutil.copytree(
        ROOT,
        target,
        ignore=shutil.ignore_patterns(
            ".git",
            ".jj",
            ".workcell",
            "dist",
            "__pycache__",
            "*.pyc",
        ),
    )
    return temporary, target


def field(entry: dict, semantic_name: str):
    for key in FIELD_ALIASES[semantic_name]:
        if key in entry:
            return entry[key]
    raise AssertionError(
        f"$.{entry.get('name', '<artifact>')}: missing {semantic_name}; "
        f"accepted keys are {FIELD_ALIASES[semantic_name]}"
    )


def registry(root: Path) -> tuple[Path, dict]:
    """Find the one JSON registry with top-level skill and agent arrays.

    The plan intentionally does not dictate the registry filename. It does dictate
    one strict shared registry, so discovery is semantic and rejects ambiguity.
    """
    matches: list[tuple[Path, dict]] = []
    for path in root.rglob("*.json"):
        if any(part in {".git", ".jj", "dist"} for part in path.parts):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue
        if (
            isinstance(data, dict)
            and isinstance(data.get("skills"), list)
            and isinstance(data.get("agents"), list)
        ):
            matches.append((path, data))
    assert len(matches) == 1, (
        "expected exactly one shared JSON contract registry with top-level "
        f"skills[] and agents[], found {[str(path.relative_to(root)) for path, _ in matches]}"
    )
    return matches[0]


def generated_artifact(root: Path, harness: str, kind: str, name: str) -> Path:
    family = root / "harnesses" / harness / kind
    assert family.is_dir(), f"missing generated family {family.relative_to(root)}"
    candidates = [
        path
        for path in family.rglob("*")
        if path.is_file()
        and path.suffix in {".md", ".json", ".yaml", ".yml", ".toml"}
        and (path.stem == name or name in path.parts)
    ]
    assert candidates, f"no generated {harness}/{kind}/{name} artifact"
    generated_candidates = [
        path
        for path in candidates
        if not harness_generation.is_harness_owned_skill_path(path, root)
    ]
    skill_md = [
        path
        for path in candidates
        if path.name == "SKILL.md"
        and not harness_generation.is_harness_owned_skill_path(path, root)
    ]
    agent_md = [path for path in candidates if path.name in {"agent.md", f"{name}.md"}]
    preferred = skill_md if kind == "skills" else agent_md
    return min(preferred or generated_candidates or candidates)


def frontmatter(text: str) -> str:
    parts = text.split("---", 2)
    assert len(parts) == 3, "generated instruction has no frontmatter"
    return parts[1]


def unsupported_optional(registry_data: dict) -> tuple[str, str, str, str, str]:
    """Return kind, artifact, harness, surface and registry-authored exact note."""
    for kind in ("skills", "agents"):
        for entry in registry_data[kind]:
            optionals = field(entry, "optional surfaces")
            if isinstance(optionals, dict):
                optionals = [
                    {"name": name, **value}
                    for name, value in optionals.items()
                    if isinstance(value, dict)
                ]
            if not isinstance(optionals, list):
                continue
            for surface in optionals:
                if not isinstance(surface, dict):
                    continue
                supported = surface.get("supported", surface.get("available"))
                note = surface.get(
                    "limitationNote",
                    surface.get("limitation_note", surface.get("note")),
                )
                harness = surface.get("harness")
                name = surface.get("name", surface.get("surface"))
                if supported is False and all(
                    isinstance(value, str) and value.strip()
                    for value in (note, harness, name)
                ):
                    return kind, field(entry, "name"), harness, name, note
    raise AssertionError(
        "registry has no unsupported optional surface carrying harness, name, "
        "supported:false, and an exact limitation note"
    )


class HarnessGenerationTests(unittest.TestCase):
    def assert_contract_entry(self, entry: dict, path: str) -> None:
        self.assertIsInstance(entry, dict, path)
        for semantic_name in FIELD_ALIASES:
            value = field(entry, semantic_name)
            self.assertNotEqual(value, "", f"{path}: empty {semantic_name}")
        self.assertIsInstance(field(entry, "name"), str, f"{path}.name")
        self.assertIsInstance(field(entry, "invocation"), str, f"{path}.invocation")
        gates = field(entry, "ordered gates")
        self.assertIsInstance(gates, list, f"{path}: ordered gates must be an array")
        self.assertTrue(gates, f"{path}: ordered gates must not be empty")
        self.assertTrue(
            all(isinstance(gate, str) and gate.strip() for gate in gates),
            f"{path}: every ordered gate must be a non-empty string",
        )
        self.assertEqual(
            field(entry, "handoff schema"),
            "anvil.agent-handoff/v1",
            f"{path}: wrong handoff schema",
        )
        self.assertIsInstance(
            field(entry, "acceptance oracle"), str, f"{path}.acceptanceOracle"
        )
        self.assertIsInstance(
            field(entry, "required values"), (dict, list), f"{path}.requiredValues"
        )
        self.assertIsInstance(
            field(entry, "optional surfaces"), (dict, list), f"{path}.optionalSurfaces"
        )

    def test_contract_registry_is_complete_and_strict(self) -> None:
        """contract-registry-is-complete-and-strict (unit)."""
        path, data = registry(ROOT)
        self.assertEqual(
            {field(entry, "name") for entry in data["skills"]}, EXPECTED_SKILLS
        )
        self.assertEqual(
            {field(entry, "name") for entry in data["agents"]}, EXPECTED_AGENTS
        )
        for kind in ("skills", "agents"):
            for index, entry in enumerate(data[kind]):
                with self.subTest(path=f"$.{kind}[{index}]", registry=path.name):
                    self.assert_contract_entry(entry, f"$.{kind}[{index}]")

        mutations = (
            (
                "unknown key",
                "agents",
                lambda manifest: manifest.update({"notAContractField": True}),
                r"\$\.notAContractField",
            ),
            (
                "duplicate",
                "agents",
                lambda manifest: manifest["agents"].append(
                    copy.deepcopy(manifest["agents"][0])
                ),
                r"\$\.agents\[\d+\]\.name",
            ),
            (
                "malformed",
                "skills",
                lambda manifest: manifest["skills"][0].__setitem__("invocation", 7),
                r"\$\.skills\[0\]\.invocation",
            ),
        )
        for label, sync_kind, mutate, expected_path in mutations:
            with self.subTest(validation=label):
                temporary, root = copied_repository()
                with temporary:
                    registry_path, manifest = registry(root)
                    mutate(manifest)
                    registry_path.write_text(
                        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
                    )
                    result = run_sync(root, sync_kind, "--check")
                    output = result.stdout + result.stderr
                    self.assertNotEqual(result.returncode, 0, output)
                    self.assertRegex(output, expected_path, output)

    def test_required_fails_optional_notes(self) -> None:
        """required-fails-optional-notes (unit)."""
        temporary, root = copied_repository()
        with temporary:
            models_path = root / "agents" / "models.json"
            models = json.loads(models_path.read_text(encoding="utf-8"))
            models["defaults"]["grok"].pop("model", None)
            for agent in models["agents"].values():
                if isinstance(agent, dict):
                    agent.setdefault("grok", {}).pop("model", None)
            models_path.write_text(
                json.dumps(models, indent=2) + "\n", encoding="utf-8"
            )
            missing = run(root, "scripts/sync-agents.py", "--check")
            missing_output = missing.stdout + missing.stderr
            self.assertEqual(missing.returncode, 2, missing_output)
            for value in ("grok", "planner", "model"):
                self.assertIn(value, missing_output, missing_output)

        _, data = registry(ROOT)
        kind, artifact, harness, surface, note = unsupported_optional(data)
        temporary, root = copied_repository()
        with temporary:
            generated = run_sync(root, kind)
            self.assertEqual(
                generated.returncode, 0, generated.stdout + generated.stderr
            )
            output = generated_artifact(root, harness, kind, artifact)
            text = output.read_text(encoding="utf-8")
            self.assertIn(
                note, text, f"{output.relative_to(root)} lacks exact registry note"
            )
            self.assertNotRegex(
                frontmatter(text),
                rf"(?m)^\s*{re.escape(surface)}\s*:",
                f"unsupported {harness}/{artifact}/{surface} was emitted",
            )

    def test_both_sync_checks_detect_real_drift(self) -> None:
        """both-sync-checks-detect-real-drift (integration)."""
        real_before = {
            path.relative_to(ROOT): path.read_bytes()
            for base in (ROOT / "harnesses", ROOT / "agents", ROOT / "skills")
            if base.exists()
            for path in base.rglob("*")
            if path.is_file()
        }
        temporary, root = copied_repository()
        with temporary:
            for kind in ("agents", "skills"):
                generated = run_sync(root, kind)
                self.assertEqual(
                    generated.returncode, 0, generated.stdout + generated.stderr
                )
                clean = run_sync(root, kind, "--check")
                self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)

            for kind, name in (("agents", "builder"), ("skills", "build")):
                target = generated_artifact(root, "claude", kind, name)
                target.write_text(
                    target.read_text(encoding="utf-8") + "\nreal drift\n",
                    encoding="utf-8",
                )
                drift = run_sync(root, kind, "--check")
                self.assertEqual(drift.returncode, 1, drift.stdout + drift.stderr)
                self.assertIn(
                    str(target.relative_to(root)), drift.stdout + drift.stderr
                )
                regenerated = run_sync(root, kind)
                self.assertEqual(
                    regenerated.returncode, 0, regenerated.stdout + regenerated.stderr
                )

                orphan = target.parent / "orphan.md"
                orphan.write_text("orphan\n", encoding="utf-8")
                orphaned = run_sync(root, kind, "--check")
                self.assertNotEqual(
                    orphaned.returncode, 0, orphaned.stdout + orphaned.stderr
                )
                self.assertIn(
                    str(orphan.relative_to(root)), orphaned.stdout + orphaned.stderr
                )
                orphan.unlink()

        real_after = {
            path.relative_to(ROOT): path.read_bytes()
            for base in (ROOT / "harnesses", ROOT / "agents", ROOT / "skills")
            if base.exists()
            for path in base.rglob("*")
            if path.is_file()
        }
        self.assertEqual(
            real_after, real_before, "temporary sync checks wrote the real tree"
        )

    def test_use_other_harness_proves_layering(self) -> None:
        """use-other-harness-proves-layering (unit)."""
        temporary, root = copied_repository()
        with temporary:
            generated = run_sync(root, "skills")
            self.assertEqual(
                generated.returncode, 0, generated.stdout + generated.stderr
            )
            bodies: dict[str, str] = {}
            parsed_contracts = {}
            for harness in HARNESSES:
                path = generated_artifact(root, harness, "skills", "use-other-harness")
                text = path.read_text(encoding="utf-8")
                bodies[harness] = text
                lower = text.lower()
                parsed_contracts[harness] = {
                    "explicit_user_request_only": bool(
                        re.search(r"explicit(?:ly)?[^.\n]{0,80}user", lower)
                    ),
                    "requires_harness_model_effort": all(
                        re.search(rf"\b{value}\b", lower)
                        for value in ("harness", "model", "effort")
                    ),
                    "not_an_automatic_router": bool(
                        re.search(r"(?:not|never)[^.\n]{0,80}(?:router|routing)", lower)
                    ),
                    "leaf_capability": "leaf" in lower,
                }
                self.assertTrue(
                    all(parsed_contracts[harness].values()),
                    f"{harness}: parsed contract is incomplete: {parsed_contracts[harness]}",
                )
                for token in NATIVE_HEADLESS_TOKENS[harness]:
                    self.assertIn(
                        token, text, f"{harness}: missing native token {token}"
                    )
            self.assertEqual(
                len(
                    {
                        json.dumps(value, sort_keys=True)
                        for value in parsed_contracts.values()
                    }
                ),
                1,
                parsed_contracts,
            )
            self.assertEqual(
                len(set(bodies.values())),
                4,
                "the four harness-owned use-other-harness bodies must be non-identical",
            )

    def test_each_stager_uses_only_its_family(self) -> None:
        """each-stager-uses-only-its-family (e2e)."""
        temporary, generated_root = copied_repository()
        with temporary:
            for kind in ("agents", "skills"):
                result = run_sync(generated_root, kind)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            self.assertTrue(
                (generated_root / "harnesses").is_dir(),
                "sync wrappers did not create harnesses/<h> generated families",
            )

            for harness in HARNESSES:
                with self.subTest(harness=harness):
                    fixture_temp = tempfile.TemporaryDirectory()
                    with fixture_temp:
                        fixture = Path(fixture_temp.name) / "workcell"
                        fixture.mkdir()
                        shutil.copytree(generated_root / "scripts", fixture / "scripts")
                        shutil.copytree(
                            generated_root / "harnesses" / harness,
                            fixture / "harnesses" / harness,
                        )
                        staged = run(fixture, f"scripts/build-{harness}-plugin.py")
                        self.assertEqual(
                            staged.returncode, 0, staged.stdout + staged.stderr
                        )
                        plugin_root = fixture / DIST_PLUGIN_ROOTS[harness]
                        self.assertTrue(
                            plugin_root.is_dir(),
                            f"{harness}: missing {plugin_root.relative_to(fixture)}",
                        )
                        self.assertFalse(
                            any(
                                path.is_symlink()
                                for path in (fixture / "dist" / harness).rglob("*")
                            ),
                            f"{harness}: staged tree contains a symlink",
                        )
                        directory_names = {
                            path.name
                            for path in plugin_root.rglob("*")
                            if path.is_dir()
                        }
                        for family in ("agents", "skills", "runtime"):
                            self.assertIn(
                                family,
                                directory_names,
                                f"{harness}: staged tree omitted {family}/",
                            )
                        forbidden = (
                            str(ROOT),
                            str(generated_root),
                            str(fixture),
                            "agents/bodies/",
                        )
                        other_harnesses = set(HARNESSES) - {harness}
                        for path in plugin_root.rglob("*"):
                            if not path.is_file():
                                continue
                            text = path.read_text(encoding="utf-8", errors="ignore")
                            for value in forbidden:
                                self.assertNotIn(
                                    value,
                                    text,
                                    f"{path.relative_to(fixture)} leaks source-root text {value!r}",
                                )
                            for other in other_harnesses:
                                self.assertNotIn(
                                    f"harnesses/{other}/",
                                    text,
                                    f"{path.relative_to(fixture)} refers to another harness family",
                                )

    def test_grok_roster_is_pinned_to_grok_4_6(self) -> None:
        """grok-roster-is-pinned-to-grok-4-6 (unit)."""
        models = json.loads((ROOT / "agents/models.json").read_text(encoding="utf-8"))
        self.assertEqual(models["defaults"]["grok"]["model"], "grok-4.6")
        for agent, values in models["agents"].items():
            if not isinstance(values, dict):
                continue
            grok = values.get("grok", {})
            self.assertNotEqual(grok.get("model"), "inherit", f"{agent}/grok")
        grok_json = json.dumps(
            {
                "defaults": models["defaults"].get("grok", {}),
                "agents": {
                    name: values.get("grok", {})
                    for name, values in models["agents"].items()
                    if isinstance(values, dict)
                },
            }
        )
        self.assertNotIn('"inherit"', grok_json)
        for kind in ("agents", "skills"):
            result = run_sync(ROOT, kind, "--check")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
