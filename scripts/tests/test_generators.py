"""Hermetic negative tests for the repository's agent/plugin generators."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(root: Path, script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", script, *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )


class GeneratorTests(unittest.TestCase):
    def copy_root(self, *paths: str) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        for relative in paths:
            source = ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
        return temporary, root

    def test_sync_agents_check_detects_real_drift(self):
        temporary, root = self.copy_root("agents", "scripts/sync-agents.py")
        with temporary:
            generated = run(root, "scripts/sync-agents.py")
            self.assertEqual(generated.returncode, 0, generated.stderr)
            path = root / "agents/claude/docs.md"
            original = path.read_text(encoding="utf-8")
            path.write_text(original + "\ndrift\n", encoding="utf-8")
            drift = run(root, "scripts/sync-agents.py", "--check")
            self.assertEqual(drift.returncode, 1, drift.stderr)
            self.assertIn("agents/claude/docs.md", drift.stdout)
            path.write_text(original, encoding="utf-8")
            clean = run(root, "scripts/sync-agents.py", "--check")
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)

    def test_sync_agents_rejects_malformed_inputs(self):
        mutations = {
            "nested only block": lambda root: (root / "agents/bodies/docs.md").write_text(
                (root / "agents/bodies/docs.md").read_text(encoding="utf-8")
                + "\n<!-- only:codex -->\n<!-- only:codex -->\n<!-- end -->\n<!-- end -->\n",
                encoding="utf-8",
            ),
            "unknown token": lambda root: (root / "agents/bodies/docs.md").write_text(
                (root / "agents/bodies/docs.md").read_text(encoding="utf-8") + "\n{{undefinedToken}}\n",
                encoding="utf-8",
            ),
            "missing gate": self._set_missing_gate,
            "empty agents": self._empty_agents,
        }
        for label, mutate in mutations.items():
            with self.subTest(case=label):
                temporary, root = self.copy_root("agents", "scripts/sync-agents.py")
                with temporary:
                    mutate(root)
                    result = run(root, "scripts/sync-agents.py", "--check")
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertRegex(result.stderr, r"docs|agents\.json")

    @staticmethod
    def _set_missing_gate(root: Path) -> None:
        path = root / "agents/agents.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["agents"]["docs"]["codex"]["gates"] = "does-not-exist"
        path.write_text(json.dumps(manifest), encoding="utf-8")

    @staticmethod
    def _empty_agents(root: Path) -> None:
        path = root / "agents/agents.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["agents"] = {}
        path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_sync_agent_models_rejects_invalid_manifest(self):
        mutations = {
            "claude effort": ("planner", "claude", "effort", "ultra"),
            "unknown harness": ("planner", "unknown-harness", "model", "x"),
            "agy model": ("planner", "agy", "model", "invalid"),
        }
        for label, (agent, harness, field, value) in mutations.items():
            with self.subTest(case=label):
                temporary, root = self.copy_root("agents", "scripts/sync-agent-models.py")
                with temporary:
                    path = root / "agents/models.json"
                    manifest = json.loads(path.read_text(encoding="utf-8"))
                    manifest["agents"][agent].setdefault(harness, {})[field] = value
                    path.write_text(json.dumps(manifest), encoding="utf-8")
                    result = run(root, "scripts/sync-agent-models.py", "--check")
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn(f"{agent}/{harness}", result.stderr)

        temporary, root = self.copy_root("agents", "scripts/sync-agent-models.py")
        with temporary:
            clean = run(root, "scripts/sync-agent-models.py", "--check")
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)

    def test_build_codex_plugin_rejects_malformed_sources_without_partial_output(self):
        for case in ("missing skill", "no frontmatter", "missing name"):
            with self.subTest(case=case):
                temporary, root = self.copy_root(
                    "agents/codex", "plugins/codex", "skills", "scripts/build-codex-plugin.py"
                )
                with temporary:
                    if case == "missing skill":
                        (root / "skills/broken").mkdir()
                        expected = "skills/broken"
                    else:
                        path = root / "agents/codex/builder.md"
                        text = path.read_text(encoding="utf-8")
                        if case == "no frontmatter":
                            path.write_text(text.split("---\n", 2)[-1], encoding="utf-8")
                            expected = "agents/codex/builder.md"
                        else:
                            path.write_text(text.replace("name: builder\n", "", 1), encoding="utf-8")
                            expected = "agents/codex/builder.md"
                    result = run(root, "scripts/build-codex-plugin.py")
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn(expected, result.stderr)
                    self.assertFalse((root / "dist/codex/plugins").exists())


if __name__ == "__main__":
    unittest.main()
