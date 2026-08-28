import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

# Load waves
import importlib.util
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = str(ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
import waves


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "waves.py"
EXAMPLES = ROOT / "examples"
AGENT = ROOT.parents[1] / "agents" / "claude" / "builder.md"


def run_helper(sidecar, snapshot):
    return subprocess.run(
        ["python3", str(SCRIPT), str(sidecar), str(snapshot)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


class BuildSkillTests(unittest.TestCase):
    def test_example_dry_run_is_deterministic(self):
        expected = json.loads((EXAMPLES / "expected-waves.json").read_text(encoding="utf-8"))
        first = run_helper(EXAMPLES / "plan.sidecar.json", EXAMPLES / "issue-state.json")
        second = run_helper(EXAMPLES / "plan.sidecar.json", EXAMPLES / "issue-state.json")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(json.loads(first.stdout), expected)
        self.assertEqual(expected["currentWave"], 2)
        self.assertEqual([item["key"] for item in expected["unblocked"]], ["API", "UI"])

    def test_reuses_strict_planner_sidecar_validation(self):
        sidecar = json.loads((EXAMPLES / "plan.sidecar.json").read_text(encoding="utf-8"))
        sidecar["unexpected"] = True
        with tempfile.TemporaryDirectory() as tmp:
            invalid = Path(tmp) / "invalid.json"
            invalid.write_text(json.dumps(sidecar), encoding="utf-8")
            result = run_helper(invalid, EXAMPLES / "issue-state.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected", result.stderr.lower())

    def test_rejects_invalid_issue_snapshot_and_marker_mismatch(self):
        snapshot = json.loads((EXAMPLES / "issue-state.json").read_text(encoding="utf-8"))
        snapshot["issues"][0]["extra"] = "not allowed"
        with tempfile.TemporaryDirectory() as tmp:
            invalid = Path(tmp) / "invalid-state.json"
            invalid.write_text(json.dumps(snapshot), encoding="utf-8")
            result = run_helper(EXAMPLES / "plan.sidecar.json", invalid)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown field", result.stderr.lower())

        snapshot = json.loads((EXAMPLES / "issue-state.json").read_text(encoding="utf-8"))
        snapshot["issues"][0]["body"] = "marker removed"
        with tempfile.TemporaryDirectory() as tmp:
            invalid = Path(tmp) / "invalid-marker.json"
            invalid.write_text(json.dumps(snapshot), encoding="utf-8")
            result = run_helper(EXAMPLES / "plan.sidecar.json", invalid)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("durable planner marker", result.stderr.lower())

    def test_rejects_dependency_cycles(self):
        sidecar = json.loads((EXAMPLES / "plan.sidecar.json").read_text(encoding="utf-8"))
        sidecar["issues"][0]["dependsOn"] = ["Integration"]
        with tempfile.TemporaryDirectory() as tmp:
            invalid = Path(tmp) / "cycle.json"
            invalid.write_text(json.dumps(sidecar), encoding="utf-8")
            result = run_helper(invalid, EXAMPLES / "issue-state.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dependency cycle", result.stderr.lower())

    def test_done_label_unblocks_dependency_and_order_is_sidecar_stable(self):
        sidecar = json.loads((EXAMPLES / "plan.sidecar.json").read_text(encoding="utf-8"))
        snapshot = json.loads((EXAMPLES / "issue-state.json").read_text(encoding="utf-8"))
        snapshot["issues"][0]["state"] = "open"
        snapshot["issues"][0]["labels"] = ["status:done"]
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            state.write_text(json.dumps(snapshot), encoding="utf-8")
            result = run_helper(EXAMPLES / "plan.sidecar.json", state)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual([item["key"] for item in output["unblocked"]], ["API", "UI"])
        self.assertIn("Foundation", output["done"])

    def test_builder_agent_and_skill_publish_required_boundaries(self):
        agent = AGENT.read_text(encoding="utf-8")
        frontmatter = agent.split("---", 2)[1].strip().splitlines()
        keys = [line.split(":", 1)[0].strip() for line in frontmatter if ":" in line]
        for required in ("name", "description", "tools"):
            self.assertIn(required, keys)
        for phrase in (
            "exactly one assigned GitHub issue", "status:in-progress", "tdd-guard seal",
            "tdd-guard reseal --reason", "tdd-guard verify", "git diff HEAD",
            "diff-review record", "Closes #", "anvil.agent-handoff/v1", "ownershipHint",
        ):
            self.assertIn(phrase, agent)

        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "GitHub is the source of truth", "current wave", "jj workspace",
            "combined GREEN", "sole synthesis", "never force-push main",
        ):
            self.assertIn(phrase, skill)

    def test_every_harness_builder_publishes_the_jj_workspace_lifecycle(self):
        """jj setup, workspace isolation, bounded review, PR, teardown — in that order,
        identically across harnesses. A builder that skips teardown leaks a working copy;
        one that tears down before the PR exists strands the branch."""
        builders = [
            ROOT.parents[1] / "agents" / "claude" / "builder.md",
            ROOT.parents[1] / "agents" / "codex" / "builder.md",
            ROOT.parents[1] / "agents" / "agy" / "builder" / "agent.md",
        ]
        ordered = [
            "jj git init --colocate",
            "jj workspace add",
            "tdd-guard verify",
            "at most two passes",
            "jj git push",
            "jj workspace forget",
        ]
        for path in builders:
            with self.subTest(builder=path.name):
                self.assertTrue(path.exists(), path)
                agent = path.read_text(encoding="utf-8")
                positions = []
                for phrase in ordered:
                    self.assertIn(phrase, agent, f"{path}: missing {phrase!r}")
                    positions.append(agent.index(phrase))
                self.assertEqual(positions, sorted(positions), f"{path}: lifecycle out of order")
                # Teardown must be gated on the PR existing.
                self.assertIn("only after the PR exists", agent)
                self.assertIn("never `jj abandon` the bookmark", agent)
                # The single spawn exception, and its limit.
                self.assertIn("read-only `code-reviewer` agents", agent)
                self.assertIn("never spawn a builder", agent)

    def test_claude_builder_can_actually_reach_the_code_reviewer(self):
        """The review passes are unreachable unless the harness grants a spawn tool."""
        agent = (ROOT.parents[1] / "agents" / "claude" / "builder.md").read_text(encoding="utf-8")
        tools = next(
            line.split(":", 1)[1] for line in agent.split("---", 2)[1].splitlines()
            if line.startswith("tools:")
        )
        self.assertIn("Task", [tool.strip() for tool in tools.split(",")])


    def test_wave_ownership_overlap_detection(self):
        self.assertTrue(hasattr(waves, "globs_overlap"), "waves does not have globs_overlap function")
        self.assertTrue(waves.globs_overlap("skills/planner/**", "skills/**"))
        self.assertFalse(waves.globs_overlap("skills/planner/**", "skills/build/**"))

    def test_wave_ownership_overlap_validation(self):
        # Create a mock sidecar and snapshot with overlapping ownershipHints
        sidecar = {
            "planId": "overlap-test",
            "planName": "Overlap test",
            "repo": "owner/repo",
            "generatedAt": "2026-08-26T12:00:00Z",
            "summary": "Overlap testing",
            "architecture": {
                "components": [],
                "diagramsMermaid": {}
            },
            "issues": [
                {
                    "key": "A",
                    "title": "Issue A",
                    "body": "Body A",
                    "labels": ["build"],
                    "dependsOn": [],
                    "ownershipHint": "skills/planner/**",
                    "wave": 1,
                    "acceptanceTests": [{"name": "test", "kind": "unit", "oracle": "pass"}]
                },
                {
                    "key": "B",
                    "title": "Issue B",
                    "body": "Body B",
                    "labels": ["build"],
                    "dependsOn": [],
                    "ownershipHint": "skills/**",
                    "wave": 1,
                    "acceptanceTests": [{"name": "test", "kind": "unit", "oracle": "pass"}]
                }
            ]
        }
        snapshot = {
            "repo": "owner/repo",
            "milestone": "Overlap test",
            "issues": [
                {
                    "number": 1,
                    "body": "Body A\n\n<!-- swarm-planner planId=overlap-test issue=A -->",
                    "labels": [],
                    "state": "open"
                },
                {
                    "number": 2,
                    "body": "Body B\n\n<!-- swarm-planner planId=overlap-test issue=B -->",
                    "labels": [],
                    "state": "open"
                }
            ]
        }
        # Verify that waves.derive raises waves.BuildError due to overlap
        with self.assertRaises(Exception) as ctx:
            waves.derive(sidecar, waves.validate_snapshot(snapshot, sidecar))
        self.assertIn("overlapping ownershiphint", str(ctx.exception).lower())

    def test_recursive_glob_vs_deep_path_overlaps(self):
        self.assertTrue(waves.globs_overlap("src/**", "src/a/b/c.py"))
        self.assertTrue(waves.globs_overlap("src/a/b/c.py", "src/**"))
        self.assertFalse(waves.globs_overlap("src/*.py", "lib/x.py"))
        # A plain path is its own literal glob.
        self.assertTrue(waves.globs_overlap("src/a/b/c.py", "src/a/b/c.py"))
        self.assertFalse(waves.globs_overlap("src/a/b/c.py", "src/a/b/d.py"))

    def test_fallback_matcher_agrees_with_full_match(self):
        """Below 3.13 the fnmatch-style fallback carries the issue's canonical cases."""
        cases = [
            ("src/a/b/c.py", "src/**", True), ("src/a/b/c.py", "src/a/b/c.py", True),
            ("src/a/b/d.py", "src/a/b/c.py", False), ("lib/x.py", "src/*.py", False),
            ("src/a/b.py", "src/*.py", False), ("a/b/c", "a/**/c", True),
            ("abc/d", "a**", False), ("a/xz", "a/[!y]z", True), ("a/[!]", "a/[!]", True), ("a/x", "a/[\\x]", True),
        ]
        for path, pattern, expected in cases:
            with self.subTest(path=path, pattern=pattern):
                self.assertEqual(waves._glob_to_regex(pattern).match(path) is not None, expected)
                self.assertEqual(waves.path_matches(path, pattern), expected)
        self.assertFalse(waves.globs_overlap("src/[!a]/x.py", "src/a/x.py"))

    def _overlap_plan(self, wave):
        issue = lambda key: {
            "key": key, "title": f"Issue {key}", "body": f"Body {key}", "labels": ["build"],
            "dependsOn": [], "ownershipHint": "skills/build/**", "wave": wave,
            "acceptanceTests": [{"name": "test", "kind": "unit", "oracle": "pass"}],
        }
        sidecar = {
            "planId": "overlap-test", "planName": "Overlap test", "repo": "owner/repo",
            "generatedAt": "2026-08-26T12:00:00Z", "summary": "Overlap testing",
            "architecture": {"components": [], "diagramsMermaid": {}},
            "issues": [issue("A"), issue("B")],
        }
        snapshot = {
            "repo": "owner/repo", "milestone": "Overlap test",
            "issues": [
                {"number": n, "body": f"Body {k}\n\n<!-- swarm-planner planId=overlap-test issue={k} -->",
                 "labels": [], "state": "open"}
                for n, k in ((1, "A"), (2, "B"))
            ],
        }
        return sidecar, snapshot

    def test_wave_zero_not_hard_failed(self):
        sidecar, snapshot = self._overlap_plan(0)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            output = waves.derive(sidecar, waves.validate_snapshot(snapshot, sidecar))
        self.assertEqual([item["key"] for item in output["unblocked"]], ["A", "B"])
        lines = [line for line in stderr.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, stderr.getvalue())
        self.assertIn("overlapping ownershiphint", lines[0].lower())
        self.assertIn("wave 0", lines[0].lower())

    def test_grouped_wave_overlap_raises_without_warning(self):
        sidecar, snapshot = self._overlap_plan(1)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(waves.BuildError):
            waves.derive(sidecar, waves.validate_snapshot(snapshot, sidecar))
        self.assertEqual(stderr.getvalue(), "")

    def test_skill_documents_redispatch_cap(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for phrase in ("`status:done`", "at most twice", "stalled", "escalates to the human"):
            self.assertIn(phrase, skill)


if __name__ == "__main__":
    unittest.main()
