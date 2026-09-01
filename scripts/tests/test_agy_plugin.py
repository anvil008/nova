"""Acceptance tests for scripts/build-agy-plugin.py (issue #131).

Antigravity used to be served by live symlinks into this repository. It is now a
self-contained staged copy at the documented auto-scan path, so the staged tree
under dist/agy/ has to be real files — a symlink that survives staging is the
double-load / dangling-target surface the whole change exists to remove.

The build is run once, into a freshly cleared dist/agy/, and every assertion
below reads that tree; nothing is asserted about a pre-existing dist/.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts" / "build-agy-plugin.py"
DIST = ROOT / "dist" / "agy"
STAGED = DIST / "workcell"
WRAPPER = ROOT / "plugins" / "agy"
MANIFEST = WRAPPER / "plugin.json"
AGY_AGENTS = ROOT / "agents" / "agy"
SKILLS = ROOT / "skills"


def agent_owned_skills() -> set[str]:
    """Skill names owned by a single Antigravity agent (ADR 0003).

    Derived from the tree — agents/agy/<agent>/skills/<name> — never listed, so
    a new agent-owned skill cannot silently start shipping globally.
    """
    return {
        path.name
        for path in AGY_AGENTS.glob("*/skills/*")
        if path.is_dir() or path.is_symlink()
    }


def shared_skill_names() -> list[str]:
    return sorted(
        path.name
        for path in SKILLS.iterdir()
        if path.is_dir() and path.name not in agent_owned_skills()
    )


class AgyStagedTreeTests(unittest.TestCase):
    """One build, shared by every case: staging is expensive and deterministic."""

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

    # --- build-agy-plugin-stages-a-symlink-free-tree ---------------------------
    def test_build_stages_a_symlink_free_tree(self) -> None:
        self.assertEqual(
            self.result.returncode,
            0,
            f"python3 scripts/build-agy-plugin.py must exit 0\n{self.report()}",
        )
        self.assertTrue(
            DIST.is_dir(),
            f"scripts/build-agy-plugin.py wrote no dist/agy\n{self.report()}",
        )

        surviving = sorted(
            str(path.relative_to(ROOT)) for path in DIST.rglob("*") if path.is_symlink()
        )
        self.assertEqual(
            surviving,
            [],
            "dist/agy must contain no symlink at all (find dist/agy -type l prints "
            f"nothing); found: {surviving}",
        )

        agent_names = sorted(
            path.name for path in AGY_AGENTS.iterdir() if (path / "agent.md").is_file()
        )
        self.assertTrue(agent_names, "agents/agy holds no <agent>/agent.md to stage")

        required = [
            STAGED / "plugin.json",
            STAGED / "hooks.json",
            STAGED / "rules",
            STAGED / "agents" / agent_names[0] / "agent.md",
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
            (STAGED / "rules").is_dir(),
            "dist/agy/workcell/rules must be a real directory",
        )
        for path in required:
            if path.name != "rules":
                self.assertTrue(
                    path.is_file(),
                    f"{path.relative_to(ROOT)} must be a regular file",
                )

    # --- staged-skills-are-exactly-the-non-agent-owned-ones --------------------
    def test_staged_skills_are_exactly_the_non_agent_owned_ones(self) -> None:
        expected = shared_skill_names()
        self.assertTrue(expected, "skills/ holds no shared skill to stage")
        self.assertTrue(
            agent_owned_skills(),
            "no agent-owned skill under agents/agy/*/skills/ — the ADR 0003 "
            "exclusion this asserts would be vacuous",
        )

        staged_skills = STAGED / "skills"
        self.assertTrue(
            staged_skills.is_dir(),
            f"dist/agy/workcell/skills is missing\n{self.report()}",
        )
        actual = sorted(path.name for path in staged_skills.iterdir() if path.is_dir())
        self.assertEqual(
            actual,
            expected,
            "the staged skills must be exactly skills/*/ minus every "
            "agents/agy/*/skills/* (ADR 0003)",
        )
        for name in actual:
            with self.subTest(skill=name):
                self.assertTrue(
                    (staged_skills / name / "SKILL.md").is_file(),
                    f"dist/agy/workcell/skills/{name}/SKILL.md is not a real file",
                )

    # --- staged-tree-carries-a-stamp-matching-the-manifest ---------------------
    def test_staged_tree_carries_a_stamp_matching_the_manifest(self) -> None:
        stamp = STAGED / ".workcell-stamp.json"
        self.assertTrue(
            stamp.is_file(),
            f"dist/agy/workcell/.workcell-stamp.json is missing\n{self.report()}",
        )
        data = json.loads(stamp.read_text(encoding="utf-8"))
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(data.get("name"), "workcell", f"stamp: {data}")
        self.assertEqual(
            data.get("version"),
            manifest["version"],
            "the stamp's version must equal plugins/agy/plugin.json's version",
        )


if __name__ == "__main__":
    unittest.main()
