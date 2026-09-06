"""Execute real sibling integrations and resumed dependency selection."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills/build/scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("build_run", SCRIPTS / "build_run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


@unittest.skipUnless(shutil.which("jj") and shutil.which("go"), "requires jj and Go")
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = tempfile.TemporaryDirectory(prefix="workcell-run-tools-")
        cls.guard = str(Path(cls.tools.name) / "tdd-guard")
        subprocess.run(["go", "build", "-o", cls.guard, "./cmd/tdd-guard"], cwd=ROOT, check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tools.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="workcell-run-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        # Read the actual constant so the fixture cannot accidentally use global state.
        import re
        self.guard_env = re.search(r'StateEnv\s*=\s*"([^"]+)"', (ROOT / "guard/guard.go").read_text())[1]
        config = self.root / "jj.toml"
        config.write_text('[user]\nname = "Workcell Test"\nemail = "test@workcell.invalid"\n[signing]\nbehavior = "drop"\n')
        environment = patch.dict(os.environ, {self.guard_env: str(self.root / "guard"), "JJ_CONFIG": str(config)})
        environment.start()
        self.addCleanup(environment.stop)
        run.command(["jj", "git", "init", str(self.repo)], self.root)
        (self.repo / "check.py").write_text("from pathlib import Path\nfor p in ('a', 'b'):\n if Path(p).exists(): assert Path(p).read_text() == p\n")
        run.jj(self.repo, "describe", "-m", "baseline")
        self.base = run.commit(self.repo, "@")
        self.plan = {"planId": "demo", "issues": [
            {"key": "A", "ownershipHint": "a", "wave": 1, "dependsOn": []},
            {"key": "B", "ownershipHint": "b", "wave": 1, "dependsOn": []},
            {"key": "C", "ownershipHint": "c", "wave": 2, "dependsOn": ["A", "B"]},
        ], "planName": "Demo"}
        self.state_dir = self.root / "state"
        self.state_dir.mkdir()
        self.path = self.state_dir / "run.json"
        self.state = {"schema": "workcell.build-run/v1", "planDigest": run.digest(self.plan),
                      "repo": str(self.repo), "repositoryId": run.identity(self.repo),
                      "bookmark": "demo-integration", "head": self.base, "integrated": {}, "rounds": {}}
        run.jj(self.repo, "bookmark", "create", "demo-integration", "-r", self.base)
        run.write(self.path, self.state)

    def source(self, key, *, test_path=None, seal_tests="check.py", implementation=True):
        workspace = self.root / key
        run.jj(self.repo, "workspace", "add", "--name", key, "--revision", self.base, str(workspace))
        check = [sys.executable, "check.py"]
        changed = []
        if test_path:
            test = workspace / test_path
            test.parent.mkdir(parents=True, exist_ok=True)
            test.write_text("assert 1 + 1 == 2\n")
            changed.append(test_path)
            check = [sys.executable, "-c",
                     "from pathlib import Path; exec(Path('check.py').read_text()); "
                     f"exec(Path({test_path!r}).read_text())"]
        run.command([self.guard, "seal", "--tests", seal_tests, "--green-baseline", *check], workspace)
        if implementation:
            (workspace / key.lower()).write_text(key.lower())
            changed.append(key.lower())
        run.jj(workspace, "describe", "-m", "Implement " + key)
        run.command([self.guard, "verify", "--green-command", *check], workspace)
        findings = self.root / (key + "-findings.txt")
        findings.write_text("Read the diff and checked the new behavior.\n")
        run.command([self.guard, "diff-review", "record", "--findings", str(findings)], workspace)
        status = json.loads(run.command([self.guard, "status", "--json"], workspace))
        handoff = self.root / (key + "-handoff.json")
        run.write(handoff, {"schema": "anvil.agent-handoff/v1", "agent": "builder", "disposition": "done",
                            "pr": None, "workspace": str(workspace), "commitId": run.commit(workspace, "@"),
                            "changeId": run.jj(workspace, "log", "--no-graph", "-r", "@", "-T", "change_id"),
                            "commands": [{"commandId": status["green"]["commandId"]}], "changedFiles": changed})
        return {"key": key, "handoff": str(handoff)}

    def prepare(self, sources, checks=None):
        return run.prepare(self.state, self.path, self.plan, sources,
                           checks or [[sys.executable, "-c", "from pathlib import Path; assert Path('a').read_text() == 'a'; assert Path('b').read_text() == 'b'"]],
                           self.root / ("candidate-" + str(len(self.state["rounds"]))), self.guard, 30)

    def test_siblings_are_combined_without_rewriting_sources_and_resume_unlocks_dependents(self):
        sources = [self.source("A"), self.source("B")]
        originals = {key: run.commit(self.root / key, "@") for key in ("A", "B")}
        receipt = self.prepare(sources)
        self.assertEqual(receipt["status"], "prepared", receipt.get("error"))
        self.assertEqual(run.commit(self.repo, "demo-integration"), self.base)
        self.assertEqual({key: run.commit(self.root / key, "@") for key in ("A", "B")}, originals)
        # Simulate an interruption in acceptance after moving the ref.
        run.jj(self.repo, "bookmark", "set", "demo-integration", "-r", receipt["commitId"])
        loaded = run.read(self.path)
        run.accept(loaded, self.path, self.plan, receipt["id"], self.guard)
        snapshot = {key: {"number": i, "state": "open", "labels": []} for i, key in enumerate(("A", "B", "C"), 1)}
        resumed = run.read(self.path)
        run.check_head(resumed)
        result = run.waves.derive(self.plan, snapshot, frozenset(resumed["integrated"]))
        self.assertEqual(result["done"], ["A", "B"])
        self.assertEqual([issue["key"] for issue in result["unblocked"]], ["C"])
        self.assertEqual(run.accept(resumed, self.path, self.plan, receipt["id"], self.guard)["status"], "accepted")

    def test_local_tasks_resume_from_receipts_without_github_issues(self):
        first = run.select(self.state, self.path, self.plan, local=True)
        self.assertEqual([item["key"] for item in first["unblocked"]], ["A", "B"])
        self.assertTrue(all(item["number"] is None for item in first["unblocked"]))
        self.assertEqual(run.read(self.path)["trackingMode"], "local")
        receipt = self.prepare([self.source("A"), self.source("B")])
        self.assertEqual(receipt["status"], "prepared", receipt.get("error"))
        run.accept(self.state, self.path, self.plan, receipt["id"], self.guard)
        resumed = run.select(run.read(self.path), self.path, self.plan, local=True)
        self.assertEqual(resumed["done"], ["A", "B"])
        self.assertEqual([item["key"] for item in resumed["unblocked"]], ["C"])
        self.assertIsNone(resumed["unblocked"][0]["number"])

    def test_failed_combined_check_keeps_trunk_and_sources(self):
        sources = [self.source("A"), self.source("B")]
        receipt = self.prepare(sources, [[sys.executable, "-c", "raise SystemExit(1)"]])
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(run.commit(self.repo, "demo-integration"), self.base)
        self.assertTrue((self.root / "A").exists())
        self.assertEqual(self.state["integrated"], {})
        with self.assertRaises(run.RunError):
            run.accept(self.state, self.path, self.plan, receipt["id"], self.guard)

    def test_changed_candidate_and_stale_builder_cannot_be_accepted(self):
        sources = [self.source("A"), self.source("B")]
        receipt = self.prepare(sources)
        self.assertEqual(receipt["status"], "prepared", receipt.get("error"))
        (Path(receipt["workspace"]) / "a").write_text("regression")
        with self.assertRaisesRegex(run.RunError, "candidate changed"):
            run.accept(self.state, self.path, self.plan, receipt["id"], self.guard)
        (self.root / "A" / "a").write_text("regression")
        with self.assertRaisesRegex(run.RunError, "immutable commitId"):
            run.source_evidence(self.repo, self.state, self.plan, sources[0], self.guard)

    def test_ownership_is_checked_against_real_files(self):
        source = self.source("A")
        self.plan["issues"][0]["ownershipHint"] = "elsewhere/**"
        with self.assertRaisesRegex(run.RunError, "outside ownership"):
            self.prepare([source])

    def test_sealing_an_unplanned_test_does_not_grant_ownership(self):
        self.plan["issues"][0].update({
            "ownershipHint": "src/a/**",
            "acceptanceTests": [{"testPath": "tests/approved.py"}],
        })
        source = self.source("A", test_path="tests/not-approved.py",
                             seal_tests="**/*.py", implementation=False)
        with self.assertRaisesRegex(run.RunError, "outside ownership.*tests/not-approved.py"):
            self.prepare([source], [[sys.executable, "tests/not-approved.py"]])
        self.assertEqual(self.state["rounds"], {})
        self.assertEqual(run.commit(self.repo, "demo-integration"), self.base)

    def test_planned_tests_outside_implementation_ownership_must_be_sealed(self):
        self.plan["issues"][0].update({
            "ownershipHint": "src/a/**",
            "acceptanceTests": [{"testPath": "tests/approved.py"}],
        })
        source = self.source("A", test_path="tests/approved.py", implementation=False)
        with self.assertRaisesRegex(run.RunError, "outside ownership.*tests/approved.py"):
            self.prepare([source], [[sys.executable, "tests/approved.py"]])
        self.assertEqual(self.state["rounds"], {})

    def test_planned_sealed_test_changes_can_be_integrated(self):
        self.plan["issues"][0].update({
            "ownershipHint": "src/a/**",
            "acceptanceTests": [{"testPath": "tests/approved.py"}],
        })
        source = self.source("A", test_path="tests/approved.py",
                             seal_tests="**/*.py", implementation=False)
        receipt = self.prepare([source], [[sys.executable, "tests/approved.py"]])
        self.assertEqual(receipt["status"], "prepared", receipt.get("error"))
        run.accept(self.state, self.path, self.plan, receipt["id"], self.guard)
        self.assertEqual(self.state["integrated"], {"A": receipt["id"]})


class OverlapRegressions(unittest.TestCase):
    def test_intersections_sampling_used_to_miss(self):
        for first, second in [("src/*/foo.py", "src/bar/*.py"), ("src/*a.py", "src/b*.py"),
                              ("src/[ab]*.py", "src/*[bc].py"), ("src/./*.py", "src/foo*.py")]:
            with self.subTest(first=first, second=second):
                self.assertTrue(run.waves.globs_overlap(first, second))
                self.assertTrue(run.waves.globs_overlap(second, first))


if __name__ == "__main__":
    unittest.main()
