import contextlib

# Load waves
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = str(ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
import waves

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "waves.py"
EXAMPLES = ROOT / "examples"
SIDECAR = EXAMPLES / "plan.sidecar.json"
STATE = EXAMPLES / "issue-state.json"
# The unedited response of `gh api repos/{owner}/{repo}/issues` for the demo milestone:
# label objects, snake_case `state_reason`, and a pull request among the issues.
GH_RAW = EXAMPLES / "gh-issues-raw.json"
# The only inputs the documented capture command may assume.
CAPTURE_ENV = {"REPO": "foundry-zero/workcell", "MILESTONE": "Builder v3 wave demo"}
AGENT = ROOT.parents[1] / "agents" / "claude" / "builder.md"


def run_helper(sidecar, snapshot):
    return subprocess.run(
        ["python3", str(SCRIPT), str(sidecar), str(snapshot)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
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

    # --- snapshot helpers -------------------------------------------------
    def _snapshot(self):
        return json.loads(STATE.read_text(encoding="utf-8"))

    def _run_snapshot(self, snapshot):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            state.write_text(json.dumps(snapshot), encoding="utf-8")
            return run_helper(SIDECAR, state)

    def test_done_label_unblocks_dependency_and_order_is_sidecar_stable(self):
        """`status:done` marks a *closed* issue finished. Doneness is agreed with
        skills/planner/scripts/reconcile_github.py: closed AND (status:done OR completed)."""
        snapshot = self._snapshot()
        snapshot["issues"][0].update(state="closed", state_reason="not_planned", labels=["status:done"])
        result = self._run_snapshot(snapshot)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual([item["key"] for item in output["unblocked"]], ["API", "UI"])
        self.assertIn("Foundation", output["done"])

        # An open issue is never done, however it is labelled: GitHub state is the truth.
        snapshot["issues"][0].update(state="open", state_reason=None, labels=["status:done"])
        result = self._run_snapshot(snapshot)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["done"], [])
        self.assertEqual(output["currentWave"], 1)
        self.assertEqual([item["key"] for item in output["unblocked"]], ["Foundation"])

    def test_snapshot_accepts_ghs_object_labels(self):
        """Every capture route hands back label objects, never bare strings:
        `gh api repos/{repo}/issues` and `gh issue list --json labels` both yield
        {id, name, color, description}. Normalising them is what makes the first real
        (non-fixture) snapshot usable at all."""
        snapshot = self._snapshot()
        # not_planned + no string labels: only honouring the object label can mark it done.
        snapshot["issues"][0].update(
            state="closed",
            state_reason="not_planned",
            labels=[
                {"id": "1", "name": "build", "color": "ededed", "description": ""},
                {"id": "2", "name": "status:done", "color": "fff", "description": None},
            ],
        )
        result = self._run_snapshot(snapshot)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertIn("Foundation", output["done"])
        self.assertEqual(output["currentWave"], 2)
        self.assertEqual([item["key"] for item in output["unblocked"]], ["API", "UI"])

        # Strings and objects may be mixed, as label_names() in the reconciler allows.
        snapshot["issues"][0]["labels"] = ["build", {"id": "2", "name": "status:done", "color": "fff"}]
        result = self._run_snapshot(snapshot)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Foundation", json.loads(result.stdout)["done"])

    def test_snapshot_still_rejects_malformed_labels(self):
        """Accepting gh's objects must not turn the label check into a rubber stamp."""
        cases = (
            ([1], "labels"),
            ([{}], "labels"),
            ([{"name": ""}], "labels"),
            ("build", "labels"),
            ([{"name": "build"}, {"name": "build"}], "duplicates"),
        )
        for labels, expected in cases:
            with self.subTest(labels=labels):
                snapshot = self._snapshot()
                issue = snapshot["issues"][0]
                issue.pop("state_reason", None)  # isolate the label check
                issue["labels"] = labels
                result = self._run_snapshot(snapshot)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("snapshot.issues[0].labels", result.stderr)
                self.assertIn(expected, result.stderr)

    def test_not_planned_closure_is_not_done(self):
        """reconcile_github.py closes housekeeping issues with state_reason=not_planned
        exactly so they are never mistaken for finished work; waves.py must agree."""
        snapshot = self._snapshot()
        snapshot["issues"][0].update(state="closed", state_reason="not_planned", labels=["build"])
        result = self._run_snapshot(snapshot)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertNotIn("Foundation", output["done"])
        self.assertEqual(output["done"], [])
        self.assertEqual(output["currentWave"], 1)
        keys = [item["key"] for item in output["unblocked"]]
        self.assertEqual(keys, ["Foundation"])
        for dependent in ("API", "UI"):
            self.assertNotIn(dependent, keys)

    def test_completed_closure_and_status_done_label_are_done(self):
        cases = (
            (["build"], "completed"),
            (["build", "status:done"], "not_planned"),
            ([{"id": "2", "name": "status:done", "color": "fff"}], None),
        )
        for labels, state_reason in cases:
            with self.subTest(labels=labels, state_reason=state_reason):
                snapshot = self._snapshot()
                snapshot["issues"][0].update(state="closed", state_reason=state_reason, labels=labels)
                result = self._run_snapshot(snapshot)
                self.assertEqual(result.returncode, 0, result.stderr)
                output = json.loads(result.stdout)
                self.assertEqual(output["done"], ["Foundation"])
                self.assertEqual(output["currentWave"], 2)
                self.assertEqual([item["key"] for item in output["unblocked"]], ["API", "UI"])

    def test_snapshot_rejects_unknown_issue_fields_even_beside_state_reason(self):
        """state_reason becomes an optional field, not an open door."""
        snapshot = self._snapshot()
        snapshot["issues"][0]["stateReason"] = "completed"
        result = self._run_snapshot(snapshot)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("unknown field", result.stderr.lower())
        self.assertIn("stateReason", result.stderr)

        snapshot = self._snapshot()
        snapshot["issues"][0]["state_reason"] = "abandoned"
        result = self._run_snapshot(snapshot)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("snapshot.issues[0].state_reason", result.stderr)

    # --- the documented capture command -----------------------------------
    @staticmethod
    def _first_shell_pipe(command):
        """Index of the first shell `|`, ignoring the many pipes inside a jq filter."""
        quote = None
        for index, char in enumerate(command):
            if quote is not None:
                if char == quote:
                    quote = None
            elif char in "'\"":
                quote = char
            elif char == "|":
                return index
        return -1

    def _documented_capture_command(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        blocks = [
            block for block in re.findall(r"```(?:bash|sh)\n(.*?)```", skill, re.DOTALL)
            if "gh " in block and "jq" in block
        ]
        self.assertEqual(
            len(blocks), 1,
            "SKILL.md must document exactly one copy-pasteable `gh ... | jq ...` capture "
            "command that turns gh output into the waves.py snapshot",
        )
        lines = [
            line for line in blocks[0].splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        return "\n".join(lines).strip()

    def test_documented_capture_command_produces_a_valid_snapshot(self):
        """Run the command SKILL.md actually publishes over a real gh response, rather
        than a restatement of it: a documented transform nobody executes is a guess."""
        self.assertIsNotNone(shutil.which("jq"), "jq is required to run the documented capture command")
        command = self._documented_capture_command()
        self.assertRegex(
            command, r"^gh\s+api\b",
            "the capture command must read repos/{owner}/{repo}/issues via `gh api`; "
            f"{GH_RAW.name} is that response, and the test substitutes it for the gh call",
        )
        pipe = self._first_shell_pipe(command)
        self.assertGreater(pipe, 0, "the capture command must pipe gh's output into a jq transform")
        transform = "cat " + shlex.quote(str(GH_RAW)) + " " + command[pipe:]
        with tempfile.TemporaryDirectory() as tmp:
            # $REPO and $MILESTONE are the only inputs the command may assume.
            run = subprocess.run(
                ["bash", "-c", transform], cwd=tmp, text=True, capture_output=True,
                env={**os.environ, **CAPTURE_ENV}, check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            produced = run.stdout.strip()
            if not produced:
                written = sorted(Path(tmp).glob("*.json"))
                self.assertEqual(len(written), 1, "the capture command produced no snapshot")
                produced = written[0].read_text(encoding="utf-8")
            snapshot = json.loads(produced)
            self.assertEqual(set(snapshot), {"repo", "milestone", "issues"})
            self.assertEqual(snapshot["repo"], CAPTURE_ENV["REPO"])
            self.assertEqual(snapshot["milestone"], CAPTURE_ENV["MILESTONE"])
            self.assertEqual(
                sorted(issue["number"] for issue in snapshot["issues"]), [101, 102, 103, 104],
                "pull requests come back from the issues endpoint and carry no planner marker",
            )
            for issue in snapshot["issues"]:
                self.assertEqual(set(issue), {"number", "body", "labels", "state", "state_reason"})
            captured = Path(tmp) / "captured-snapshot.json"
            captured.write_text(json.dumps(snapshot), encoding="utf-8")
            result = run_helper(SIDECAR, captured)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            json.loads((EXAMPLES / "expected-waves.json").read_text(encoding="utf-8")),
        )

    def test_builder_agent_and_skill_publish_required_boundaries(self):
        agent = AGENT.read_text(encoding="utf-8")
        frontmatter = agent.split("---", 2)[1].strip().splitlines()
        keys = [line.split(":", 1)[0].strip() for line in frontmatter if ":" in line]
        for required in ("name", "description", "tools"):
            self.assertIn(required, keys)
        for phrase in (
            "exactly one assigned GitHub issue", "status:in-progress", "sealed tests",
            "tdd-guard reseal --reason", "tdd-guard verify", "git diff HEAD",
            "diff-review record", "Closes #", "anvil.agent-handoff/v1", "ownershipHint",
        ):
            self.assertIn(phrase, agent)
        # Authorship moved to the oracle: a builder that can seal can define its own
        # Definition of Done, which is the loophole the split exists to close.
        self.assertNotIn("tdd-guard seal", agent)

        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "GitHub is the source of truth", "current wave", "jj workspace",
            "combined GREEN", "sole completion authority", "force-push `main`",
        ):
            self.assertIn(phrase, skill)

    def test_every_harness_builder_publishes_the_jj_workspace_lifecycle(self):
        """jj setup, workspace isolation, runtime proof, bounded review, PR, teardown — in
        that order, identically across harnesses. A builder that skips teardown leaks a working
        copy; one that tears down before the PR exists strands the branch; one that reviews
        before running the change reviews something nobody has seen work."""
        builders = [
            ROOT.parents[1] / "agents" / "claude" / "builder.md",
            ROOT.parents[1] / "agents" / "codex" / "builder.md",
            ROOT.parents[1] / "agents" / "agy" / "builder" / "agent.md",
        ]
        ordered = [
            "jj workspace list",
            "tdd-guard verify",
            "Prove it runs, not just passes",
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
                self.assertIn("read-only `reviewer` agents", agent)
                self.assertIn("never spawn a builder", agent)

    def test_claude_builder_can_actually_reach_the_reviewer(self):
        """The review passes are unreachable unless the harness grants a spawn tool."""
        agent = (ROOT.parents[1] / "agents" / "claude" / "builder.md").read_text(encoding="utf-8")
        tools = next(
            line.split(":", 1)[1] for line in agent.split("---", 2)[1].splitlines()
            if line.startswith("tools:")
        )
        self.assertIn("Agent", [tool.strip() for tool in tools.split(",")])


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
                    "body": "Body A\n\n<!-- workcell-planner planId=overlap-test issue=A -->",
                    "labels": [],
                    "state": "open"
                },
                {
                    "number": 2,
                    "body": "Body B\n\n<!-- workcell-planner planId=overlap-test issue=B -->",
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
                {"number": n, "body": f"Body {k}\n\n<!-- workcell-planner planId=overlap-test issue={k} -->",
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

    def test_every_harness_ships_an_oracle_that_owns_the_seal(self):
        """The oracle creates the workspace, proves honest RED, and seals. If any of
        that drifts back into the builder, the agent judged by the tests wrote them."""
        authors = [
            ROOT.parents[1] / "agents" / "claude" / "oracle.md",
            ROOT.parents[1] / "agents" / "codex" / "oracle.md",
            ROOT.parents[1] / "agents" / "agy" / "oracle" / "agent.md",
        ]
        ordered = [
            "jj git init --colocate",
            "jj workspace add",
            "tdd-guard seal",
        ]
        for path in authors:
            with self.subTest(agent=path.parent.name if path.name == "agent.md" else path.name):
                self.assertTrue(path.exists(), path)
                agent = path.read_text(encoding="utf-8")
                positions = []
                for phrase in ordered:
                    self.assertIn(phrase, agent, f"{path}: missing {phrase!r}")
                    positions.append(agent.index(phrase))
                self.assertEqual(positions, sorted(positions), f"{path}: lifecycle out of order")
                # An import error is not RED; sealing one hands over a hollow gate.
                self.assertIn("ImportError", agent)
                self.assertIn("signature-only stub", agent)
                # It writes tests, never the implementation, and never merges.
                self.assertIn("never write an implementation", agent.lower())
                self.assertIn("anvil.agent-handoff/v1", agent)
                self.assertNotIn("tdd-guard verify", agent)

    def test_skill_dispatches_the_two_phases_in_order(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for phrase in ("`oracle`", "Phase 1", "Phase 2", "integrator"):
            self.assertIn(phrase, skill)
        self.assertLess(skill.index("Phase 1"), skill.index("Phase 2"))
        self.assertIn("never dispatch a builder for an issue with no seal", skill)

    def test_skill_documents_redispatch_cap(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for phrase in ("`status:done`", "at most twice", "stalled", "escalate to the human"):
            self.assertIn(phrase, skill)


if __name__ == "__main__":
    unittest.main()
