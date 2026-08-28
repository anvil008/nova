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
            "GitHub is the source of truth", "current wave", "isolated worktrees",
            "combined GREEN", "sole synthesis", "never force-push main",
        ):
            self.assertIn(phrase, skill)


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


if __name__ == "__main__":
    unittest.main()
