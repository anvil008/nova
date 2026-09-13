"""Unit tests for the si-global skill and si_global.py CLI."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
SI_PROJECT = REPO / "skills" / "si-project" / "scripts" / "si.py"
SI_GLOBAL = REPO / "skills" / "si-global" / "scripts" / "si_global.py"


def run_global(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SI_GLOBAL)] + args
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


def run_project(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SI_PROJECT)] + args
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


class RegistryHandlingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name).resolve()
        self.registry = self.base / "known_projects.json"
        self.env = {"NOVA_PROJECTS_REGISTRY": str(self.registry)}

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_projects_with_missing_registry(self):
        res = run_global(["projects"], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertEqual(data["totalProjects"], 0)
        self.assertEqual(data["projects"], [])

    def test_projects_with_registered_repos(self):
        repo1 = self.base / "repo1"
        repo1.mkdir()
        (repo1 / ".git").mkdir()
        run_project(["init", "--repo", str(repo1)], env=self.env)

        repo2 = self.base / "repo2"
        repo2.mkdir()
        (repo2 / ".git").mkdir()
        # Not initialized in si

        # Add both to registry
        self.registry.write_text(json.dumps({"projects": [str(repo1), str(repo2)]}), encoding="utf-8")

        res = run_global(["projects"], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertEqual(data["totalProjects"], 2)
        p1 = next(p for p in data["projects"] if p["path"] == str(repo1))
        self.assertTrue(p1["storeExists"])
        p2 = next(p for p in data["projects"] if p["path"] == str(repo2))
        self.assertFalse(p2["storeExists"])


class ScanAndClusterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name).resolve()
        self.registry = self.base / "known_projects.json"
        self.env = {"NOVA_PROJECTS_REGISTRY": str(self.registry)}

        # Setup Repo A
        self.repo_a = self.base / "repo-a"
        self.repo_a.mkdir()
        (self.repo_a / ".git").mkdir()
        run_project(["init", "--repo", str(self.repo_a)], env=self.env)

        ev_a = self.base / "ev_a.txt"
        ev_a.write_text("test lock timeout a\n", encoding="utf-8")
        run_project([
            "record", "--repo", str(self.repo_a),
            "--id", "trace-a-1", "--kind", "build", "--summary", "wave failure",
            "--file", str(ev_a),
        ], env=self.env)
        run_project([
            "pattern", "flaky-test-runner", "--repo", str(self.repo_a),
            "--evidence", "trace-a-1", "--note", "Runner froze on suite A.",
            "--title", "Flaky Test Runner",
        ], env=self.env)
        run_project([
            "pattern", "repo-a-only-issue", "--repo", str(self.repo_a),
            "--evidence", "trace-a-1", "--note", "Local configuration issue.",
        ], env=self.env)

        # Setup Repo B
        self.repo_b = self.base / "repo-b"
        self.repo_b.mkdir()
        (self.repo_b / ".git").mkdir()
        run_project(["init", "--repo", str(self.repo_b)], env=self.env)

        ev_b = self.base / "ev_b.txt"
        ev_b.write_text("test lock timeout b\n", encoding="utf-8")
        run_project([
            "record", "--repo", str(self.repo_b),
            "--id", "trace-b-1", "--kind", "build", "--summary", "wave failure",
            "--file", str(ev_b),
        ], env=self.env)
        run_project([
            "pattern", "flaky-test-runner", "--repo", str(self.repo_b),
            "--evidence", "trace-b-1", "--note", "Runner froze on suite B.",
            "--title", "Flaky Test Runner",
        ], env=self.env)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scan_aggregates_all_patterns(self):
        res = run_global(["scan"], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertEqual(data["totalProjects"], 2)
        self.assertEqual(data["totalPatterns"], 3)  # 2 in repo-a, 1 in repo-b

    def test_cluster_filters_by_min_projects(self):
        # min-projects 2 should only find flaky-test-runner
        res = run_global(["cluster", "--min-projects", "2"], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertEqual(data["clusterCount"], 1)
        cluster = data["clusters"][0]
        self.assertEqual(cluster["slug"], "flaky-test-runner")
        self.assertEqual(cluster["projectCount"], 2)
        self.assertEqual(cluster["totalOccurrences"], 2)
        self.assertIn(str(self.repo_a), cluster["projects"])
        self.assertIn(str(self.repo_b), cluster["projects"])

    def test_propose_generates_proposals_with_eval_notice(self):
        out_dir = self.base / "proposals-out"
        res = run_global(["propose", "--min-projects", "2", "--output", str(out_dir)], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertEqual(data["proposalsCount"], 1)
        prop = data["proposals"][0]
        self.assertEqual(prop["targetSkill"], "build")
        self.assertEqual(prop["evalGate"], "evals/run_evals.py")
        self.assertIn("evalGateNotice", data)

        # Check output file written
        prop_file = out_dir / "global-flaky-test-runner.json"
        self.assertTrue(prop_file.is_file())


if __name__ == "__main__":
    unittest.main()
