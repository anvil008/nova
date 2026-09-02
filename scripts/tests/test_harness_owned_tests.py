"""Harness-owned test directories under family roots are non-generated (#152).

Plan09 places per-harness acceptance tests at:
  harnesses/<h>/skills/tests/test_<h>_skills.py
  harnesses/<h>/agents/tests/test_<h>_agents.py
  harnesses/<h>/runtime/tests/test_<h>_runtime.py

These tests/ directories directly under family roots must:
- never be reported as drift or orphans by sync-* --check or check-contract-parity
- never be modified or removed by a non-check sync (left byte-identical)
- never be copied into dist/<h> by the plugin stagers
- leave stray non-test files under family roots flagged as orphans (check not blinded)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class HarnessOwnedTestsDirectories(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "workcell"
        shutil.copytree(
            ROOT,
            self.root,
            ignore=shutil.ignore_patterns(
                ".git", ".jj", ".workcell", "dist", "__pycache__", "*.pyc"
            ),
        )

    def run_cmd(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *args],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_harness_owned_tests_are_neither_drift_nor_orphan(self) -> None:
        """(a) harnesses/<h>/{agents,skills,runtime}/tests/ files are neither drift nor orphan."""
        test_file = self.root / "harnesses/claude/agents/tests/test_x.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# harness-owned agent test\n", encoding="utf-8")

        skill_test = self.root / "harnesses/claude/skills/tests/test_skills.py"
        skill_test.parent.mkdir(parents=True, exist_ok=True)
        skill_test.write_text("# harness-owned skill test\n", encoding="utf-8")

        runtime_test = self.root / "harnesses/claude/runtime/tests/test_runtime.py"
        runtime_test.parent.mkdir(parents=True, exist_ok=True)
        runtime_test.write_text("# harness-owned runtime test\n", encoding="utf-8")

        # sync-agents --check
        res_agents = self.run_cmd("scripts/sync-agents.py", "--check")
        self.assertEqual(
            res_agents.returncode,
            0,
            f"sync-agents --check failed with harness-owned tests present:\n{res_agents.stdout}\n{res_agents.stderr}",
        )
        self.assertNotIn("orphan", res_agents.stdout)
        self.assertNotIn("drift", res_agents.stdout)

        # sync-skills --check
        res_skills = self.run_cmd("scripts/sync-skills.py", "--check")
        self.assertEqual(
            res_skills.returncode,
            0,
            f"sync-skills --check failed with harness-owned tests present:\n{res_skills.stdout}\n{res_skills.stderr}",
        )
        self.assertNotIn("orphan", res_skills.stdout)
        self.assertNotIn("drift", res_skills.stdout)

        # check-contract-parity.py
        res_parity = self.run_cmd("scripts/check-contract-parity.py")
        self.assertEqual(
            res_parity.returncode,
            0,
            f"check-contract-parity failed with harness-owned tests present:\n{res_parity.stdout}\n{res_parity.stderr}",
        )

    def test_non_check_sync_leaves_test_files_byte_identical(self) -> None:
        """(b) a non-check sync leaves harness-owned test files byte-identical."""
        files = {
            self.root / "harnesses/claude/agents/tests/test_x.py": b"# custom agent test\ndef test_a(): pass\n",
            self.root / "harnesses/claude/skills/tests/test_skills.py": b"# custom skill test\ndef test_b(): pass\n",
            self.root / "harnesses/claude/runtime/tests/test_runtime.py": b"# custom runtime test\ndef test_c(): pass\n",
        }
        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        res_agents = self.run_cmd("scripts/sync-agents.py")
        self.assertEqual(res_agents.returncode, 0, res_agents.stdout + res_agents.stderr)

        res_skills = self.run_cmd("scripts/sync-skills.py")
        self.assertEqual(res_skills.returncode, 0, res_skills.stdout + res_skills.stderr)

        for path, expected_content in files.items():
            self.assertTrue(path.is_file(), f"{path} was removed by non-check sync")
            self.assertEqual(
                path.read_bytes(),
                expected_content,
                f"{path} content was altered by non-check sync",
            )

    def test_claude_stager_does_not_copy_tests_into_staged_tree(self) -> None:
        """(c) the claude stager does not copy harness-owned tests into the staged tree."""
        test_file = self.root / "harnesses/claude/agents/tests/test_x.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("# claude test\n", encoding="utf-8")

        skill_test = self.root / "harnesses/claude/skills/tests/test_skills.py"
        skill_test.parent.mkdir(parents=True, exist_ok=True)
        skill_test.write_text("# claude skill test\n", encoding="utf-8")

        runtime_test = self.root / "harnesses/claude/runtime/tests/test_runtime.py"
        runtime_test.parent.mkdir(parents=True, exist_ok=True)
        runtime_test.write_text("# claude runtime test\n", encoding="utf-8")

        res = self.run_cmd("scripts/build-claude-plugin.py")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

        staged_agents_tests = self.root / "dist/claude/workcell/agents/tests"
        self.assertFalse(
            staged_agents_tests.exists(),
            f"Claude stager copied {staged_agents_tests.relative_to(self.root)} into staged tree",
        )

        staged_skills_tests = self.root / "dist/claude/workcell/skills/tests"
        self.assertFalse(
            staged_skills_tests.exists(),
            f"Claude stager copied {staged_skills_tests.relative_to(self.root)} into staged tree",
        )

        staged_runtime_tests = self.root / "dist/claude/workcell/runtime/tests"
        self.assertFalse(
            staged_runtime_tests.exists(),
            f"Claude stager copied {staged_runtime_tests.relative_to(self.root)} into staged tree",
        )

        # Ensure skill-internal tests (e.g. skills/build/tests) are still preserved
        staged_build_tests = self.root / "dist/claude/workcell/skills/build/tests"
        self.assertTrue(
            staged_build_tests.is_dir(),
            "Claude stager should not remove skill-internal tests like skills/build/tests",
        )

    def test_all_stagers_omit_harness_owned_tests(self) -> None:
        """Verify codex, agy, and grok stagers also never stage harness-owned tests/."""
        harness_roots = {
            "codex": (self.root / "dist/codex/plugins/workcell", "build-codex-plugin.py"),
            "agy": (self.root / "dist/agy/workcell", "build-agy-plugin.py"),
            "grok": (self.root / "dist/grok/plugins/workcell", "build-grok-plugin.py"),
        }
        for harness, (staged_root, script) in harness_roots.items():
            for family in ("agents", "skills", "runtime"):
                test_file = self.root / f"harnesses/{harness}/{family}/tests/test_sample.py"
                test_file.parent.mkdir(parents=True, exist_ok=True)
                test_file.write_text("# sample test\n", encoding="utf-8")

            res = self.run_cmd(f"scripts/{script}")
            self.assertEqual(res.returncode, 0, f"{harness} stager failed:\n{res.stdout}\n{res.stderr}")

            for family in ("agents", "skills", "runtime"):
                staged_family_tests = staged_root / family / "tests"
                self.assertFalse(
                    staged_family_tests.exists(),
                    f"{harness} stager copied {family}/tests into staged tree: {staged_family_tests}",
                )

    def test_unrelated_stray_file_is_still_reported_as_orphan(self) -> None:
        """(d) an unrelated stray file is still reported as an orphan, so the check is not blinded."""
        stray_file = self.root / "harnesses/claude/agents/stray.md"
        stray_file.write_text("# stray agent\n", encoding="utf-8")

        res_agents = self.run_cmd("scripts/sync-agents.py", "--check")
        self.assertEqual(res_agents.returncode, 1)
        self.assertIn("harnesses/claude/agents/stray.md (orphan)", res_agents.stdout)

        stray_file.unlink()

        stray_skill = self.root / "harnesses/claude/skills/stray.md"
        stray_skill.write_text("# stray skill\n", encoding="utf-8")

        res_skills = self.run_cmd("scripts/sync-skills.py", "--check")
        self.assertEqual(res_skills.returncode, 1)
        self.assertIn("harnesses/claude/skills/stray.md (orphan)", res_skills.stdout)

        stray_skill.unlink()

        stray_dir = self.root / "harnesses/claude/agents/stray_dir"
        stray_dir.mkdir(parents=True, exist_ok=True)
        (stray_dir / "foo.txt").write_text("hello\n", encoding="utf-8")

        res_agents_dir = self.run_cmd("scripts/sync-agents.py", "--check")
        self.assertEqual(res_agents_dir.returncode, 1)
        self.assertIn("harnesses/claude/agents/stray_dir (orphan directory)", res_agents_dir.stdout)


if __name__ == "__main__":
    unittest.main()
