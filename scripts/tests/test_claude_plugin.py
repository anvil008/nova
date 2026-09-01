"""Unit tests for scripts/build-claude-plugin.py (#134).

Claude installs through a command-declared marketplace which runs stage-workcell
to materialize dist/claude/workcell/ as a self-contained, symlink-free tree.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts" / "build-claude-plugin.py"
DIST = ROOT / "dist" / "claude"
STAGED = DIST / "workcell"


class ClaudeStagedTreeTests(unittest.TestCase):
    """One build, shared by every case: staging is deterministic."""

    result: subprocess.CompletedProcess

    @classmethod
    def setUpClass(cls) -> None:
        shutil.rmtree(DIST, ignore_errors=True)
        cls.result = subprocess.run(
            ["python3", str(BUILDER)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def report(self) -> str:
        return (
            f"rc={self.result.returncode}\n"
            f"stdout: {self.result.stdout}\nstderr: {self.result.stderr}"
        )

    def test_build_claude_plugin_stages_a_symlink_free_tree(self) -> None:
        self.assertEqual(
            self.result.returncode,
            0,
            f"python3 scripts/build-claude-plugin.py must exit 0\n{self.report()}",
        )
        self.assertTrue(
            DIST.is_dir(),
            f"scripts/build-claude-plugin.py wrote no dist/claude\n{self.report()}",
        )

        surviving = sorted(
            str(path.relative_to(ROOT)) for path in DIST.rglob("*") if path.is_symlink()
        )
        self.assertEqual(
            surviving,
            [],
            "dist/claude must contain no symlink at all (find dist/claude -type l prints "
            f"nothing); found: {surviving}",
        )

        required = [
            STAGED / ".claude-plugin" / "plugin.json",
            STAGED / "hooks" / "hooks.json",
            STAGED / "scripts" / "build-hooks",
            STAGED / "agents" / "builder.md",
            STAGED / "skills" / "plan" / "SKILL.md",
        ]
        for path in required:
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertTrue(
                    path.exists(),
                    f"{path.relative_to(ROOT)} is missing from the staged tree\n"
                    f"{self.report()}",
                )
                self.assertFalse(
                    path.is_symlink(),
                    f"{path.relative_to(ROOT)} is a symlink, not a real staged entry",
                )
                self.assertTrue(
                    path.is_file(),
                    f"{path.relative_to(ROOT)} must be a regular file",
                )

        stamp = STAGED / ".workcell-stamp.json"
        self.assertTrue(
            stamp.is_file(),
            f"dist/claude/workcell/.workcell-stamp.json is missing\n{self.report()}",
        )


if __name__ == "__main__":
    unittest.main()
