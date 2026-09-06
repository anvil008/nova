"""Acceptance tests for Codex runtime scripts, hooks, and staging metadata (#160).

Tests that:
1. codex-runtime-stages-only-codex (integration):
   A parseable plugin/marketplace stages hooks, 12 skills and ten agent
   skills/metadata with no symlink or other harness path.
2. content-hash-is-sensitive-only-to-codex (unit):
   Unchanged builds keep <semver>+codex.<12hex>; changing Codex content changes it;
   changing another harness does not.
3. unsupported-codex-surfaces-are-not-invented (unit):
   Unavailable fields are absent with one limitation note; missing required
   profile values fail.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TEST_FILE = Path(__file__).resolve()
RUNTIME_DIR = TEST_FILE.parents[1]
HARNESS_DIR = TEST_FILE.parents[2]
REPO_ROOT = TEST_FILE.parents[4]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# All 16 Workcell skills
EXPECTED_SKILLS = (
    "build",
    "debug",
    "deploy",
    "docs",
    "jj",
    "plan",
    "profile",
    "refactor",
    "repo-setup",
    "review",
    "use-other-harness",
    "wiki",
)

# All 10 Workcell agents
EXPECTED_AGENTS = (
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
)


class CodexRuntimeTests(unittest.TestCase):
    """Authoritative acceptance tests for GitHub issue #160 (CodexRuntime)."""

    def _create_isolated_fixture(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        """Create a temporary isolated fixture copying needed harness and generator paths."""
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        paths_to_copy = [
            "harnesses/codex",
            "harnesses/claude",
            "harnesses/agy",
            "agents",
            "skills",
            "plugins/codex",
            "plugins/claude",
            "contracts",
            "scripts/build-codex-plugin.py",
            "scripts/lib_dist.py",
        ]
        for rel in paths_to_copy:
            src = REPO_ROOT / rel
            if not src.exists():
                continue
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        return tmp, root

    def _run_codex_stager(self, root: Path) -> subprocess.CompletedProcess[str]:
        """Run the Codex plugin stager in the given root."""
        stager = root / "scripts" / "build-codex-plugin.py"
        return subprocess.run(
            [sys.executable, str(stager)],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_codex_runtime_stages_only_codex(self) -> None:
        """codex-runtime-stages-only-codex (integration):

        A parseable plugin/marketplace stages hooks, 12 skills and ten agent
        skills/metadata with no symlink or other harness path.
        """
        # 1. Plugin manifest resolves inside the family and is valid JSON
        manifest_path = RUNTIME_DIR / ".codex-plugin" / "plugin.json"
        self.assertTrue(
            manifest_path.is_file(),
            f"Missing plugin manifest at {manifest_path}",
        )
        self.assertFalse(
            manifest_path.is_symlink(),
            f"Manifest {manifest_path} must not be a symlink",
        )
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest_data.get("name"), "workcell")
        self.assertTrue(
            manifest_data.get("version"),
            "Manifest must declare non-empty version",
        )
        self.assertTrue(
            manifest_data.get("description"),
            "Manifest must declare non-empty description",
        )
        self.assertIn(
            "author", manifest_data, "Codex plugin manifest requires 'author'"
        )
        self.assertIn(
            "interface", manifest_data, "Codex plugin manifest requires 'interface'"
        )
        interface = manifest_data.get("interface", {})
        for required_key in (
            "displayName",
            "shortDescription",
            "longDescription",
            "developerName",
        ):
            self.assertTrue(
                interface.get(required_key),
                f"Codex plugin manifest interface missing {required_key}",
            )
        self.assertNotIn(
            "hooks", manifest_data, "Codex plugin manifest must not contain 'hooks' key"
        )
        self.assertNotIn(
            "agents",
            manifest_data,
            "Codex plugin manifest must not contain 'agents' key",
        )

        # 2. Hooks resolve inside the family and define PreToolUse, PostToolUse, and Stop
        hooks_path = RUNTIME_DIR / "hooks" / "hooks.json"
        self.assertTrue(
            hooks_path.is_file(),
            f"Missing hooks manifest at {hooks_path}",
        )
        self.assertFalse(
            hooks_path.is_symlink(),
            f"Hooks manifest {hooks_path} must not be a symlink",
        )
        hooks_data = json.loads(hooks_path.read_text(encoding="utf-8"))
        self.assertIn("hooks", hooks_data, "Hooks manifest must declare 'hooks' key")
        hooks_dict = hooks_data.get("hooks", {})
        self.assertIn("PreToolUse", hooks_dict, "Hooks manifest missing PreToolUse")
        self.assertIn("PostToolUse", hooks_dict, "Hooks manifest missing PostToolUse")
        self.assertIn("Stop", hooks_dict, "Hooks manifest missing Stop")

        # 3. Shared guard executables copied into runtime scripts directory
        scripts_dir = RUNTIME_DIR / "scripts"
        self.assertTrue(
            scripts_dir.is_dir(),
            f"Missing scripts directory at {scripts_dir}: runtime must copy shared guard executables (#160)",
        )
        for guard_name in ("build-guard", "build-hooks", "build-format", "build-lint"):
            guard_file = scripts_dir / guard_name
            self.assertTrue(
                guard_file.is_file(),
                f"Shared guard script {guard_file} is missing from runtime/scripts",
            )
            self.assertTrue(
                os.access(guard_file, os.X_OK),
                f"Shared guard script {guard_file} must be executable",
            )
            self.assertFalse(
                guard_file.is_symlink(),
                f"Shared guard script {guard_file} must not be a symlink",
            )

        # 4. Zero symlinks anywhere in RUNTIME_DIR
        runtime_symlinks = [
            str(p.relative_to(RUNTIME_DIR))
            for p in RUNTIME_DIR.rglob("*")
            if p.is_symlink()
        ]
        self.assertEqual(
            runtime_symlinks,
            [],
            f"harnesses/codex/runtime must contain zero symlinks; found: {runtime_symlinks}",
        )

        # 5. Ownership Seam: harnesses/codex/runtime owns its manifests/hooks;
        # scripts/harness_generation.py must not copy them from plugins/codex.
        from scripts import harness_generation

        source_code = inspect.getsource(harness_generation.desired_runtime)
        self.assertNotIn(
            'root / "plugins/codex/.codex-plugin"',
            source_code,
            "scripts/harness_generation.py: desired_runtime must not copy .codex-plugin from plugins/codex; "
            "harnesses/codex/runtime must own its manifest directly (#160)",
        )
        self.assertNotIn(
            'root / "plugins/codex/hooks"',
            source_code,
            "scripts/harness_generation.py: desired_runtime must not copy hooks from plugins/codex; "
            "harnesses/codex/runtime must own its hooks directly (#160)",
        )
        self.assertIn(
            "codex",
            harness_generation.HARNESS_OWNED_RUNTIME,
            "scripts/harness_generation.py: HARNESS_OWNED_RUNTIME must contain 'codex' (#160)",
        )
        codex_owned = harness_generation.HARNESS_OWNED_RUNTIME.get("codex", ())
        self.assertIn(
            Path(".codex-plugin"),
            codex_owned,
            "HARNESS_OWNED_RUNTIME['codex'] must include .codex-plugin",
        )
        self.assertIn(
            Path("hooks"),
            codex_owned,
            "HARNESS_OWNED_RUNTIME['codex'] must include hooks",
        )

        # 6. Staging validation: build-codex-plugin.py stages with no symlinks or other harness paths
        builder_script = REPO_ROOT / "scripts" / "build-codex-plugin.py"
        self.assertTrue(builder_script.is_file(), f"Missing {builder_script}")
        proc = subprocess.run(
            [sys.executable, str(builder_script)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"scripts/build-codex-plugin.py failed with exit code {proc.returncode}:\n{proc.stderr}",
        )

        staged_plugin = REPO_ROOT / "dist" / "codex" / "plugins" / "workcell"
        self.assertTrue(
            staged_plugin.is_dir(), f"Staged directory {staged_plugin} was not created"
        )

        staged_marketplace = (
            REPO_ROOT / "dist" / "codex" / ".agents" / "plugins" / "marketplace.json"
        )
        self.assertTrue(
            staged_marketplace.is_file(),
            f"Marketplace manifest {staged_marketplace} missing",
        )
        mkt_data = json.loads(staged_marketplace.read_text(encoding="utf-8"))
        self.assertEqual(mkt_data.get("name"), "workcell")
        plugins_list = mkt_data.get("plugins", [])
        self.assertTrue(
            any(p.get("name") == "workcell" for p in plugins_list),
            f"Marketplace missing 'workcell' plugin entry: {plugins_list}",
        )

        # Staged plugin manifest check
        staged_manifest_file = staged_plugin / ".codex-plugin" / "plugin.json"
        self.assertTrue(
            staged_manifest_file.is_file(),
            f"Missing staged manifest at {staged_manifest_file}",
        )
        staged_manifest = json.loads(staged_manifest_file.read_text(encoding="utf-8"))
        self.assertEqual(staged_manifest.get("name"), "workcell")
        self.assertRegex(
            staged_manifest.get("version", ""),
            r"^0\.6\.0\+codex\.[0-9a-f]{12}$",
            f"Staged version {staged_manifest.get('version')} does not match <semver>+codex.<12hex>",
        )

        # Staged hooks check
        staged_hooks_file = staged_plugin / "hooks" / "hooks.json"
        self.assertTrue(
            staged_hooks_file.is_file(), f"Missing staged hooks {staged_hooks_file}"
        )
        staged_hooks = json.loads(staged_hooks_file.read_text(encoding="utf-8"))
        self.assertIn("hooks", staged_hooks)

        # 12 skills staged under skills/<skill>/SKILL.md
        for skill in EXPECTED_SKILLS:
            skill_md = staged_plugin / "skills" / skill / "SKILL.md"
            self.assertTrue(
                skill_md.is_file(),
                f"Expected skill {skill} at {skill_md} is missing from staged plugin",
            )
            self.assertFalse(
                skill_md.is_symlink(),
                f"Staged skill {skill_md} must not be a symlink",
            )
            self.assertTrue(
                len(skill_md.read_text(encoding="utf-8").strip()) > 0,
                f"Staged skill {skill_md} is empty",
            )

        # 10 agent skills and metadata staged
        for agent in EXPECTED_AGENTS:
            agent_skill_md = staged_plugin / "skills" / f"agent-{agent}" / "SKILL.md"
            self.assertTrue(
                agent_skill_md.is_file(),
                f"Expected agent skill agent-{agent} at {agent_skill_md} is missing",
            )
            self.assertFalse(
                agent_skill_md.is_symlink(),
                f"Staged agent skill {agent_skill_md} must not be a symlink",
            )
            meta_yaml = (
                staged_plugin / "skills" / f"agent-{agent}" / "agents" / "openai.yaml"
            )
            self.assertTrue(
                meta_yaml.is_file(),
                f"Expected agent metadata {meta_yaml} is missing",
            )
            self.assertFalse(
                meta_yaml.is_symlink(),
                f"Staged agent metadata {meta_yaml} must not be a symlink",
            )
            yaml_text = meta_yaml.read_text(encoding="utf-8")
            self.assertIn("interface:", yaml_text)
            self.assertIn("displayName:", yaml_text)
            self.assertIn("shortDescription:", yaml_text)
            self.assertIn("defaultPrompt:", yaml_text)

        # Zero symlinks anywhere in dist/codex
        staged_symlinks = [
            str(p.relative_to(REPO_ROOT / "dist" / "codex"))
            for p in (REPO_ROOT / "dist" / "codex").rglob("*")
            if p.is_symlink()
        ]
        self.assertEqual(
            staged_symlinks,
            [],
            f"Staged dist/codex contains symlinks: {staged_symlinks}",
        )

        # No other harness path or repo leak in staged files
        foreign_terms = [
            "${CLAUDE_PLUGIN_ROOT}",
            "plugins/claude",
            "harnesses/claude",
            "plugins/agy",
            "harnesses/agy",
            "plugins/grok",
            "harnesses/grok",
            str(REPO_ROOT),
        ]
        for path in staged_plugin.rglob("*"):
            if path.is_file() and not path.name.endswith(".pyc"):
                try:
                    content = path.read_text(encoding="utf-8")
                    for term in foreign_terms:
                        self.assertNotIn(
                            term,
                            content,
                            f"Staged file {path.relative_to(staged_plugin)} contains foreign/repo reference: {term}",
                        )
                except UnicodeDecodeError:
                    pass

    def test_content_hash_is_sensitive_only_to_codex(self) -> None:
        """content-hash-is-sensitive-only-to-codex (unit):

        Unchanged builds keep <semver>+codex.<12hex>; changing Codex content
        changes it; changing another harness does not.
        """
        tmp, root = self._create_isolated_fixture()
        with tmp:
            # 1. Unchanged builds keep <semver>+codex.<12hex>
            proc1 = self._run_codex_stager(root)
            self.assertEqual(proc1.returncode, 0, proc1.stdout + proc1.stderr)
            manifest_file = (
                root
                / "dist"
                / "codex"
                / "plugins"
                / "workcell"
                / ".codex-plugin"
                / "plugin.json"
            )
            v1 = json.loads(manifest_file.read_text(encoding="utf-8"))["version"]
            self.assertRegex(
                v1,
                r"^0\.6\.0\+codex\.[0-9a-f]{12}$",
                f"Version {v1!r} does not match <semver>+codex.<12hex>",
            )

            # Re-run unchanged
            proc2 = self._run_codex_stager(root)
            self.assertEqual(proc2.returncode, 0, proc2.stdout + proc2.stderr)
            v2 = json.loads(manifest_file.read_text(encoding="utf-8"))["version"]
            self.assertEqual(
                v1,
                v2,
                f"Unchanged builds must produce identical versions; got {v1} vs {v2}",
            )

            # 2. Changing Codex content changes it
            codex_skill = root / "harnesses" / "codex" / "skills" / "build" / "SKILL.md"
            self.assertTrue(codex_skill.is_file(), f"Missing {codex_skill}")
            original_codex_text = codex_skill.read_text(encoding="utf-8")
            codex_skill.write_text(
                original_codex_text + "\n# Test change to Codex skill\n",
                encoding="utf-8",
            )

            proc_codex_mod = self._run_codex_stager(root)
            self.assertEqual(
                proc_codex_mod.returncode,
                0,
                proc_codex_mod.stdout + proc_codex_mod.stderr,
            )
            v_codex_changed = json.loads(manifest_file.read_text(encoding="utf-8"))[
                "version"
            ]
            self.assertRegex(v_codex_changed, r"^0\.6\.0\+codex\.[0-9a-f]{12}$")
            self.assertNotEqual(
                v1,
                v_codex_changed,
                f"Modifying Codex content must change the content hash; got unchanged {v1}",
            )

            # Revert Codex change and verify restoration
            codex_skill.write_text(original_codex_text, encoding="utf-8")
            proc_revert = self._run_codex_stager(root)
            self.assertEqual(
                proc_revert.returncode, 0, proc_revert.stdout + proc_revert.stderr
            )
            v_reverted = json.loads(manifest_file.read_text(encoding="utf-8"))[
                "version"
            ]
            self.assertEqual(
                v1,
                v_reverted,
                f"Reverting Codex change must restore original version; got {v_reverted} vs {v1}",
            )

            # 3. Changing another harness (Claude) does not change it
            claude_skill = (
                root / "harnesses" / "claude" / "skills" / "build" / "SKILL.md"
            )
            self.assertTrue(claude_skill.is_file(), f"Missing {claude_skill}")
            original_claude_text = claude_skill.read_text(encoding="utf-8")
            claude_skill.write_text(
                original_claude_text + "\n# Test change to Claude skill\n",
                encoding="utf-8",
            )

            proc_claude_mod = self._run_codex_stager(root)
            self.assertEqual(
                proc_claude_mod.returncode,
                0,
                proc_claude_mod.stdout + proc_claude_mod.stderr,
            )
            v_claude_changed = json.loads(manifest_file.read_text(encoding="utf-8"))[
                "version"
            ]
            self.assertEqual(
                v1,
                v_claude_changed,
                f"Modifying another harness (claude) must NOT change Codex content hash; got {v_claude_changed} != {v1}",
            )

    def test_unsupported_codex_surfaces_are_not_invented(self) -> None:
        """unsupported-codex-surfaces-are-not-invented (unit):

        Unavailable fields are absent with one limitation note; missing
        required profile values fail.
        """
        # 1. Unavailable fields are absent with one limitation note in contracts
        contracts_file = REPO_ROOT / "contracts" / "harness-contracts.json"
        self.assertTrue(
            contracts_file.is_file(), f"Missing contracts at {contracts_file}"
        )
        contracts_data = json.loads(contracts_file.read_text(encoding="utf-8"))

        # Optional surfaces for codex must be unsupported with a non-empty limitation note
        codex_optional_surfaces = [
            surf
            for ag in contracts_data.get("agents", [])
            for surf in ag.get("optionalSurfaces", [])
            if surf.get("harness") == "codex"
        ]
        self.assertTrue(
            len(codex_optional_surfaces) > 0,
            "Expected at least one Codex optionalSurface declared in contracts",
        )
        for surf in codex_optional_surfaces:
            self.assertFalse(
                surf.get("supported", True),
                f"Optional surface {surf.get('name')} for Codex must not be marked supported",
            )
            note = surf.get("limitationNote", "")
            self.assertTrue(
                len(note.strip()) > 0,
                f"Optional surface {surf.get('name')} for Codex must have a non-empty limitation note",
            )

        # Skills and agents must not declare unsupported required values for codex
        unsupported_values = {
            "mode",
            "forks",
            "worktrees",
            "workflow_surfaces",
            "subagent_stop",
            "programmatic_tool_calling",
        }
        for sk in contracts_data.get("skills", []):
            reqs = set(sk.get("requiredValues", {}).get("codex", []))
            invented = reqs.intersection(unsupported_values)
            self.assertFalse(
                invented,
                f"Skill {sk.get('name')} invents unsupported Codex surfaces: {invented}",
            )
        for ag in contracts_data.get("agents", []):
            reqs = set(ag.get("requiredValues", {}).get("codex", []))
            invented = reqs.intersection(unsupported_values)
            self.assertFalse(
                invented,
                f"Agent {ag.get('name')} invents unsupported Codex surfaces: {invented}",
            )

        # Agent frontmatter in harnesses/codex/agents/*.md must not invent 'mode'
        codex_agents_dir = HARNESS_DIR / "agents"
        self.assertTrue(codex_agents_dir.is_dir(), f"Missing {codex_agents_dir}")
        for agent_file in codex_agents_dir.glob("*.md"):
            content = agent_file.read_text(encoding="utf-8")
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = parts[1]
                    self.assertNotIn(
                        "\nmode:",
                        "\n" + frontmatter,
                        f"Codex agent {agent_file.name} must not declare 'mode' in frontmatter",
                    )

        # 2. Capability evaluation metadata must exist under harnesses/codex/runtime
        capabilities_path = RUNTIME_DIR / "capabilities.json"
        self.assertTrue(
            capabilities_path.is_file(),
            f"Missing runtime capabilities metadata at {capabilities_path}: "
            "must evaluate unsupported Codex surfaces against headless capability (#160)",
        )
        self.assertFalse(
            capabilities_path.is_symlink(),
            f"Capabilities file {capabilities_path} must not be a symlink",
        )
        caps = json.loads(capabilities_path.read_text(encoding="utf-8"))
        self.assertEqual(caps.get("harness"), "codex")
        features = caps.get("features", {})

        # Evaluated surfaces from GPT-5.6 Sol prompting guide and ADRs
        required_features = {
            "mode",
            "programmatic_tool_calling",
            "responses_api_multi_agent",
            "command_hooks",
        }
        for feat in required_features:
            self.assertIn(
                feat,
                features,
                f"Capabilities metadata {capabilities_path} missing evaluation for feature {feat!r}",
            )

        # Unsupported features must be marked unsupported and carry limitation notes
        for feat in ("mode", "programmatic_tool_calling", "responses_api_multi_agent"):
            info = features[feat]
            self.assertFalse(
                info.get("supported", True) and info.get("headless", True),
                f"Feature {feat!r} must not be declared as supported in Codex headless mode",
            )
            note = (
                info.get("limitation_note")
                or info.get("omission_note")
                or info.get("note")
                or ""
            )
            self.assertTrue(
                len(note.strip()) > 0,
                f"Feature {feat!r} is unsupported but lacks a non-empty limitation note",
            )

        # Supported headless capability
        self.assertTrue(
            features.get("command_hooks", {}).get("supported", False),
            "command_hooks must be marked supported in Codex capabilities",
        )

        # Headless command must specify codex
        headless_cmd = caps.get("headless_command", [])
        self.assertTrue(
            any("codex" in c for c in headless_cmd),
            f"Headless command in capabilities must specify codex; got {headless_cmd}",
        )

        # 3. Missing required profile values fail
        # Verify that missing codex profile, missing model, missing effort, or invalid effort fail closed
        for bad_case, modifier in (
            (
                "missing_codex_profile",
                lambda m: m["agents"]["builder"].pop("codex", None),
            ),
            (
                "missing_model",
                lambda m: (
                    m["agents"]["builder"].setdefault("codex", {}).pop("model", None)
                ),
            ),
            (
                "missing_effort",
                lambda m: (
                    m["agents"]["builder"].setdefault("codex", {}).pop("effort", None)
                ),
            ),
            (
                "invalid_effort",
                lambda m: (
                    m["agents"]["builder"]
                    .setdefault("codex", {})
                    .__setitem__("effort", "ultra")
                ),
            ),
            (
                "empty_model",
                lambda m: (
                    m["agents"]["builder"]
                    .setdefault("codex", {})
                    .__setitem__("model", "")
                ),
            ),
        ):
            with self.subTest(case=bad_case):
                tmp, root = self._create_isolated_fixture()
                with tmp:
                    models_json = (
                        root / "harnesses" / "codex" / "runtime" / "models.json"
                    )
                    if not models_json.is_file():
                        models_json = root / "agents" / "models.json"
                    manifest = json.loads(models_json.read_text(encoding="utf-8"))
                    modifier(manifest)
                    models_json.write_text(json.dumps(manifest), encoding="utf-8")

                    proc = self._run_codex_stager(root)
                    self.assertNotEqual(
                        proc.returncode,
                        0,
                        f"Expected stager failure for case {bad_case}, but succeeded with exit code 0",
                    )
                    self.assertFalse(
                        (root / "dist" / "codex" / "plugins").exists(),
                        f"Stager created partial output for invalid profile case {bad_case}",
                    )


if __name__ == "__main__":
    unittest.main()
