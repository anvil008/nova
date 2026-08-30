"""Tests for scripts/bootstrap-eval.sh — the switch that puts one task repo into eval mode.

Every case runs against a throwaway repository and a throwaway HOME under mktemp; `claude`
and `codex` are stubbed on PATH so `--with-hooks` exercises the real bootstrap-project.sh
delegation without touching a harness install.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "bootstrap-eval.sh"
BEGIN = "<!-- BEGIN workcell eval-mode -->"
END = "<!-- END workcell eval-mode -->"
MARKER = ".workcell/eval-mode.json"
HERMETIC = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
IDENTITY = [
    "-c",
    "user.email=t@example.invalid",
    "-c",
    "user.name=t",
    "-c",
    "commit.gpgsign=false",
]


def git(directory: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(directory),
        env={**os.environ, **HERMETIC},
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout


class EvalBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.tmp = Path(self.temporary.name)
        self.home = self.tmp / "home"
        (self.home / ".local" / "bin").mkdir(parents=True)
        self.stub = self.tmp / "stub-bin"
        self.stub.mkdir()
        for cli in ("claude", "codex"):
            path = self.stub / cli
            path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            path.chmod(0o755)

    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, **HERMETIC}
        env["HOME"] = str(self.home)
        env["PATH"] = f"{self.stub}:{env['PATH']}"
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=str(self.tmp),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def repo(self, name: str = "task", agents_md: str | None = "# Task repo\n") -> Path:
        directory = self.tmp / name
        directory.mkdir()
        git(directory, "-c", "init.defaultBranch=main", "init", "-q", ".")
        if agents_md is not None:
            (directory / "AGENTS.md").write_text(agents_md, encoding="utf-8")
            git(directory, "add", "-A")
            git(directory, *IDENTITY, "commit", "-qm", "init")
        return directory

    def exclude(self, directory: Path) -> list[str]:
        path = directory / ".git" / "info" / "exclude"
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    # --- refusals --------------------------------------------------------------------------
    def test_refuses_a_directory_that_is_not_a_git_repository(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        result = self.run_script(str(plain))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("not a git repository", result.stderr)
        self.assertFalse((plain / ".workcell").exists())

    def test_refuses_the_workcell_source_tree(self):
        fake = self.repo("workcell-like", agents_md=None)
        (fake / "cmd" / "tdd-guard").mkdir(parents=True)
        (fake / "agents" / "bodies").mkdir(parents=True)
        result = self.run_script(str(fake))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Workcell source tree", result.stderr)
        self.assertFalse((fake / MARKER).exists())
        self.assertFalse((fake / "CLAUDE.md").exists())

    def test_refuses_the_real_workcell_checkout(self):
        result = self.run_script(str(ROOT))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Workcell source tree", result.stderr)
        self.assertFalse((ROOT / MARKER).exists())

    def test_without_an_argument_it_prints_usage(self):
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("bootstrap-eval.sh <task-dir>", result.stderr)
        self.assertIn("task directory is required", result.stderr)

    # --- what one run writes ----------------------------------------------------------------
    def test_writes_the_marker_the_exclude_and_both_preambles(self):
        directory = self.repo()
        result = self.run_script(str(directory))
        self.assertEqual(result.returncode, 0, result.stderr)

        marker = json.loads((directory / MARKER).read_text(encoding="utf-8"))
        self.assertEqual(marker["mode"], "eval")
        self.assertEqual(marker["source"], "bootstrap-eval")
        started = datetime.strptime(marker["startedAt"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        self.assertLessEqual(started, datetime.now(timezone.utc))

        self.assertIn(".workcell/", self.exclude(directory))
        for name in ("AGENTS.md", "CLAUDE.md"):
            text = (directory / name).read_text(encoding="utf-8")
            self.assertTrue(text.startswith(BEGIN), name)
            self.assertIn(END, text, name)
        self.assertIn(
            "# Task repo", (directory / "AGENTS.md").read_text(encoding="utf-8")
        )

    def test_preamble_states_what_eval_mode_changes(self):
        directory = self.repo()
        self.run_script(str(directory))
        text = (directory / "CLAUDE.md").read_text(encoding="utf-8").lower()
        block = text[text.index(BEGIN.lower()) : text.index(END.lower())]
        phrases = (
            "`gh`",
            "without waiting",
            "no interview",
            "deploy skill must refuse",
            "verifier",
            "reference solutions",
            "local commits",
            "default branch",
            "committed working tree",
            "tdd-guard",
        )
        for phrase in phrases:
            self.assertIn(phrase, block, phrase)

    def test_an_untracked_instruction_file_is_local_ignored(self):
        directory = self.repo()
        self.run_script(str(directory))
        # AGENTS.md is tracked here, so info/exclude cannot hide it and the script says so;
        # CLAUDE.md is one this script created, so it never reaches the scored patch.
        self.assertIn("CLAUDE.md", self.exclude(directory))
        self.assertNotIn("AGENTS.md", self.exclude(directory))
        status = git(directory, "status", "--porcelain")
        self.assertNotIn("CLAUDE.md", status)
        self.assertNotIn(".workcell", status)

    def test_is_idempotent(self):
        directory = self.repo()
        self.run_script(str(directory))
        names = ("AGENTS.md", "CLAUDE.md", MARKER)
        before = {n: (directory / n).read_text(encoding="utf-8") for n in names}
        excluded = self.exclude(directory)
        result = self.run_script(str(directory))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("already present", result.stdout)
        after = {n: (directory / n).read_text(encoding="utf-8") for n in names}
        self.assertEqual(before, after)
        self.assertEqual(excluded, self.exclude(directory))

    # --- --force and --remove ----------------------------------------------------------------
    def test_an_edited_preamble_needs_force(self):
        directory = self.repo()
        self.run_script(str(directory))
        claude_md = directory / "CLAUDE.md"
        edited = claude_md.read_text(encoding="utf-8").replace(
            "## Eval mode", "## Whatever"
        )
        claude_md.write_text(edited, encoding="utf-8")

        refused = self.run_script(str(directory))
        self.assertNotEqual(refused.returncode, 0, refused.stdout)
        self.assertIn("--force", refused.stderr)
        self.assertIn("## Whatever", claude_md.read_text(encoding="utf-8"))

        forced = self.run_script("--force", str(directory))
        self.assertEqual(forced.returncode, 0, forced.stderr)
        restored = claude_md.read_text(encoding="utf-8")
        self.assertIn("## Eval mode", restored)
        self.assertNotIn("## Whatever", restored)

    def test_remove_restores_the_repository(self):
        original = "# Task repo\n\nProject rules the eval must not lose.\n"
        directory = self.repo(agents_md=original)
        self.run_script(str(directory))
        result = self.run_script("--remove", str(directory))
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertEqual(
            (directory / "AGENTS.md").read_text(encoding="utf-8"), original
        )
        self.assertFalse((directory / "CLAUDE.md").exists())
        self.assertFalse((directory / ".workcell").exists())
        self.assertNotIn(".workcell/", self.exclude(directory))
        self.assertNotIn("CLAUDE.md", self.exclude(directory))
        self.assertEqual(git(directory, "status", "--porcelain"), "")

    def test_remove_keeps_lines_the_repository_excluded_itself(self):
        directory = self.repo()
        with (directory / ".git" / "info" / "exclude").open(
            "a", encoding="utf-8"
        ) as handle:
            handle.write("build/\n")
        self.run_script(str(directory))
        self.run_script("--remove", str(directory))
        self.assertIn("build/", self.exclude(directory))

    # --- the pieces it reuses rather than reimplements -----------------------------------------
    def test_with_hooks_delegates_to_bootstrap_project(self):
        directory = self.repo()
        result = self.run_script("--with-hooks", str(directory))
        self.assertEqual(result.returncode, 0, result.stderr)
        settings_path = directory / ".claude" / "settings.local.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        groups = settings["hooks"]["PreToolUse"]
        commands = [hook["command"] for group in groups for hook in group["hooks"]]
        self.assertTrue(any("build-guard" in command for command in commands), commands)
        self.assertIn(".claude/settings.local.json", self.exclude(directory))

    def test_it_prints_a_headless_launch_line_per_harness(self):
        directory = self.repo()
        output = self.run_script(str(directory)).stdout
        self.assertIn(f"codex exec --cd {directory}", output)
        for fragment in ("claude -p", "agy -p"):
            self.assertIn(fragment, output)
        self.assertIn(str(directory), output)


if __name__ == "__main__":
    unittest.main()
