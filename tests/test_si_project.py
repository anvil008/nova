"""Unit tests for the si-project skill and si.py CLI."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
SI_SCRIPT = REPO / "skills" / "si-project" / "scripts" / "si.py"


def run_si(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SI_SCRIPT)] + args
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        cmd,
        cwd=cwd or REPO,
        env=full_env,
        capture_output=True,
        text=True,
        check=False,
    )


class PrimaryRootResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_resolve_root_from_primary_jj(self):
        repo_dir = self.base / "repo"
        repo_dir.mkdir(parents=True)
        jj_repo = repo_dir / ".jj" / "repo"
        jj_repo.mkdir(parents=True)

        res = run_si(["resolve-root", "--repo", str(repo_dir)])
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), str(repo_dir))

    def test_resolve_root_from_secondary_jj_workspace(self):
        primary_dir = self.base / "primary"
        primary_dir.mkdir(parents=True)
        primary_jj_repo = primary_dir / ".jj" / "repo"
        primary_jj_repo.mkdir(parents=True)

        # Secondary workspace points to primary
        secondary_dir = primary_dir / ".workspaces" / "feat-x"
        secondary_dir.mkdir(parents=True)
        (secondary_dir / ".jj").mkdir(parents=True)
        pointer_file = secondary_dir / ".jj" / "repo"
        pointer_file.write_text("../../../.jj/repo\n", encoding="utf-8")

        res = run_si(["resolve-root", "--repo", str(secondary_dir)])
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), str(primary_dir))

    def test_resolve_root_from_git_worktree(self):
        main_repo = self.base / "main-git"
        main_repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-b", "main"], cwd=main_repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=main_repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=main_repo, check=True)
        (main_repo / "README.md").write_text("initial\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=main_repo, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=main_repo, check=True)

        wt_dir = self.base / "wt-1"
        subprocess.run(["git", "worktree", "add", str(wt_dir), "-b", "branch1"], cwd=main_repo, check=True)

        res = run_si(["resolve-root", "--repo", str(wt_dir)])
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), str(main_repo))


class StoreInitAndStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name).resolve()
        self.repo = self.base / "project"
        self.repo.mkdir(parents=True)
        (self.repo / ".git").mkdir()  # simulate git repo
        self.registry = self.base / "known_projects.json"
        self.env = {
            "NOVA_PROJECTS_REGISTRY": str(self.registry),
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_status_when_not_initialized(self):
        res = run_si(["status", "--repo", str(self.repo)], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertFalse(data["present"])
        self.assertEqual(data["primaryRoot"], str(self.repo))
        self.assertEqual(data["storePath"], str(self.repo / ".nova" / "si"))

    def test_init_creates_store_and_registers(self):
        res = run_si(["init", "--repo", str(self.repo)], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertTrue(data["created"])
        store_path = Path(data["storePath"])

        self.assertTrue((store_path / "project.json").is_file())
        self.assertTrue((store_path / "index.md").is_file())
        self.assertTrue((store_path / "logs.md").is_file())
        self.assertTrue((store_path / "skill-impact.md").is_file())
        self.assertTrue((store_path / "raw").is_dir())
        self.assertTrue((store_path / "patterns").is_dir())
        self.assertTrue((store_path / "proposals").is_dir())

        # Check registry updated
        self.assertTrue(self.registry.is_file())
        reg_data = json.loads(self.registry.read_text(encoding="utf-8"))
        self.assertIn(str(self.repo), reg_data["projects"])

        # Check status after init
        s_res = run_si(["status", "--repo", str(self.repo)], env=self.env)
        self.assertEqual(s_res.returncode, 0, s_res.stderr)
        s_data = json.loads(s_res.stdout)
        self.assertTrue(s_data["present"])
        self.assertEqual(s_data["raw"], 0)
        self.assertEqual(s_data["patterns"], 0)
        self.assertEqual(s_data["proposals"], 0)

        # Idempotent init
        res2 = run_si(["init", "--repo", str(self.repo)], env=self.env)
        self.assertEqual(res2.returncode, 0, res2.stderr)
        data2 = json.loads(res2.stdout)
        self.assertFalse(data2["created"])


class RawAndPatternTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name).resolve()
        self.repo = self.base / "project"
        self.repo.mkdir(parents=True)
        (self.repo / ".git").mkdir()
        self.registry = self.base / "known_projects.json"
        self.env = {
            "NOVA_PROJECTS_REGISTRY": str(self.registry),
        }
        run_si(["init", "--repo", str(self.repo)], env=self.env)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_record_and_pattern_accumulation(self):
        ev1 = self.base / "log1.txt"
        ev1.write_text("Integrator timed out on lock\n", encoding="utf-8")

        rec_res = run_si([
            "record",
            "--repo", str(self.repo),
            "--id", "2026-09-13-build-1",
            "--kind", "build-wave",
            "--summary", "lock timeout on wave 1",
            "--file", str(ev1),
            "--model", "claude-sonnet-5",
            "--effort", "high",
        ], env=self.env)
        self.assertEqual(rec_res.returncode, 0, rec_res.stderr)
        self.assertEqual(rec_res.stdout.strip(), "2026-09-13-build-1")

        # Duplicate ID is refused (write-once)
        rec_dup = run_si([
            "record",
            "--repo", str(self.repo),
            "--id", "2026-09-13-build-1",
            "--kind", "build-wave",
            "--summary", "another summary",
            "--file", str(ev1),
        ], env=self.env)
        self.assertNotEqual(rec_dup.returncode, 0)

        # Pattern creation
        pat_res = run_si([
            "pattern", "flaky-lock",
            "--repo", str(self.repo),
            "--evidence", "2026-09-13-build-1",
            "--note", "Timed out waiting for sandbox lock.",
            "--title", "Flaky sandbox lock",
        ], env=self.env)
        self.assertEqual(pat_res.returncode, 0, pat_res.stderr)
        self.assertEqual(pat_res.stdout.strip(), "flaky-lock")

        pattern_file = self.repo / ".nova" / "si" / "patterns" / "flaky-lock.md"
        self.assertTrue(pattern_file.is_file())
        text = pattern_file.read_text(encoding="utf-8")
        self.assertIn("# Flaky sandbox lock", text)
        self.assertIn("`2026-09-13-build-1` [claude-sonnet-5·high]", text)
        self.assertIn("Timed out waiting for sandbox lock.", text)

        # Index updated
        index_file = self.repo / ".nova" / "si" / "index.md"
        idx_text = index_file.read_text(encoding="utf-8")
        self.assertIn("[flaky-lock](patterns/flaky-lock.md)", idx_text)
        self.assertIn("| 1 |", idx_text)

        # Nonexistent evidence ID is refused
        pat_bad = run_si([
            "pattern", "flaky-lock",
            "--repo", str(self.repo),
            "--evidence", "nonexistent-id",
            "--note", "Should fail.",
        ], env=self.env)
        self.assertNotEqual(pat_bad.returncode, 0)


class ProposeAndApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name).resolve()
        self.repo = self.base / "project"
        self.repo.mkdir(parents=True)
        (self.repo / ".git").mkdir()
        self.registry = self.base / "known_projects.json"
        self.env = {
            "NOVA_PROJECTS_REGISTRY": str(self.registry),
        }
        run_si(["init", "--repo", str(self.repo)], env=self.env)

        ev1 = self.base / "log1.txt"
        ev1.write_text("Lock contention observed\n", encoding="utf-8")
        run_si([
            "record",
            "--repo", str(self.repo),
            "--id", "2026-09-13-trace-1",
            "--kind", "test-trace",
            "--summary", "trace summary",
            "--file", str(ev1),
        ], env=self.env)
        run_si([
            "pattern", "sandbox-contention",
            "--repo", str(self.repo),
            "--evidence", "2026-09-13-trace-1",
            "--note", "Contention under parallel workers.",
        ], env=self.env)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_propose_and_apply_to_agents_md(self):
        res = run_si([
            "propose",
            "--repo", str(self.repo),
            "--id", "prop-lock-mitigation",
            "--pattern", "sandbox-contention",
            "--title", "Sandbox Lock Retry Rule",
            "--target", "agents-md",
            "--rule", "Retry sandbox lock acquisition up to 3 times with exponential backoff.",
        ], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        p_data = json.loads(res.stdout)
        self.assertFalse(p_data["applied"])

        p_file = self.repo / ".nova" / "si" / "proposals" / "prop-lock-mitigation.json"
        self.assertTrue(p_file.is_file())

        # Apply the proposal
        apply_res = run_si([
            "propose",
            "--repo", str(self.repo),
            "--id", "prop-lock-mitigation",
            "--apply",
        ], env=self.env)
        self.assertEqual(apply_res.returncode, 0, apply_res.stderr)
        app_data = json.loads(apply_res.stdout)
        self.assertTrue(app_data["applied"])

        agents_md = self.repo / "AGENTS.md"
        self.assertTrue(agents_md.is_file())
        content = agents_md.read_text(encoding="utf-8")
        self.assertIn("## Sandbox Lock Retry Rule", content)
        self.assertIn("Retry sandbox lock acquisition", content)

        # Audit trail written
        impact = (self.repo / ".nova" / "si" / "skill-impact.md").read_text(encoding="utf-8")
        self.assertIn("applied proposal prop-lock-mitigation to AGENTS.md", impact)

    def test_propose_and_apply_to_local_skill(self):
        res = run_si([
            "propose",
            "--repo", str(self.repo),
            "--id", "prop-custom-skill",
            "--pattern", "sandbox-contention",
            "--title", "Custom Lock Helper",
            "--target", "skill",
            "--skill-name", "sandbox-helper",
            "--rule", "#!/bin/bash\necho helper",
            "--apply",
        ], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)

        custom_skill_md = self.repo / ".nova" / "skills" / "sandbox-helper" / "SKILL.md"
        self.assertTrue(custom_skill_md.is_file())
        self.assertIn("echo helper", custom_skill_md.read_text(encoding="utf-8"))


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name).resolve()
        self.repo = self.base / "project"
        self.repo.mkdir(parents=True)
        (self.repo / ".git").mkdir()
        self.registry = self.base / "known_projects.json"
        self.env = {
            "NOVA_PROJECTS_REGISTRY": str(self.registry),
        }
        run_si(["init", "--repo", str(self.repo)], env=self.env)

        ev1 = self.base / "file1.txt"
        ev1.write_text("hello evidence\n", encoding="utf-8")
        run_si([
            "record",
            "--repo", str(self.repo),
            "--id", "trace-101",
            "--kind", "check-test",
            "--summary", "trace 101",
            "--file", str(ev1),
        ], env=self.env)
        run_si([
            "pattern", "sample-pattern",
            "--repo", str(self.repo),
            "--evidence", "trace-101",
            "--note", "Sample note.",
        ], env=self.env)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_check_passes_on_healthy_store(self):
        res = run_si(["check", "--repo", str(self.repo)], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertTrue(data["ok"])

    def test_check_fails_on_tampered_file(self):
        file_dest = self.repo / ".nova" / "si" / "raw" / "trace-101" / "files" / "file1.txt"
        file_dest.write_text("tampered content\n", encoding="utf-8")

        res = run_si(["check", "--repo", str(self.repo)], env=self.env)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("checksum mismatch", res.stderr)

    def test_check_fails_on_index_drift(self):
        index_file = self.repo / ".nova" / "si" / "index.md"
        # tamper with occurrences count
        index_file.write_text(index_file.read_text().replace("| 1 |", "| 99 |"), encoding="utf-8")

        res = run_si(["check", "--repo", str(self.repo)], env=self.env)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("count mismatch", res.stderr)


class EvalModeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name).resolve()
        self.repo = self.base / "project"
        self.repo.mkdir(parents=True)
        (self.repo / ".git").mkdir()
        (self.repo / ".nova").mkdir(parents=True)
        (self.repo / ".nova" / "eval-mode.json").write_text("{}", encoding="utf-8")
        self.registry = self.base / "known_projects.json"
        self.env = {
            "NOVA_PROJECTS_REGISTRY": str(self.registry),
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_eval_mode_refuses_operations(self):
        for cmd in (["status"], ["init"], ["check"]):
            res = run_si(cmd + ["--repo", str(self.repo)], env=self.env)
            self.assertNotEqual(res.returncode, 0, f"{cmd} should have failed in eval mode")
            self.assertIn("eval mode refused", res.stderr)


if __name__ == "__main__":
    unittest.main()
