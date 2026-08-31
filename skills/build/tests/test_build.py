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
# The pull-forward fixture set: one unfinished wave-1 straggler, a later-wave issue whose
# dependencies are already done, a deliberately coarse late hint that overlaps the straggler,
# and an issue still blocked behind it.
PULL_FORWARD = EXAMPLES / "pull-forward"
REPO_ROOT = ROOT.parents[1]
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
        # Authorship moved to the specifier: a builder that can seal can define its own
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
            "architecture": {
                "changeSummary": "Two issues that claim the same paths.",
                "components": [{"name": "Build", "purpose": "Overlapping ownership."}],
                "diagramsMermaid": {
                    "currentArchitecture": "flowchart LR\n  A --- B",
                    "targetArchitecture": "flowchart LR\n  A --- B",
                },
            },
            "issues": [issue("A"), issue("B")],
            "risks": [],
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

    def _run_overlap_plan(self, wave):
        """The shared overlap pair, run the way the orchestrator runs it: as a process."""
        sidecar, snapshot = self._overlap_plan(wave)
        with tempfile.TemporaryDirectory() as tmp:
            sidecar_path = Path(tmp) / "plan.sidecar.json"
            snapshot_path = Path(tmp) / "issue-state.json"
            sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            return run_helper(sidecar_path, snapshot_path)

    def test_wave_zero_overlap_serializes_instead_of_warning_only(self):
        """Wave 0 is the ungrouped bucket, so an overlap there is not a plan defect — but a
        warning the orchestrator has to act on by hand is not a safeguard. The pair is still
        warned about once, naming both keys, and now exactly one of them is dispatchable."""
        result = self._run_overlap_plan(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual([item["key"] for item in output["unblocked"]], ["A"])
        self.assertIn("deferred", output)
        self.assertEqual([item["key"] for item in output["deferred"]], ["B"])
        self.assertEqual(output["deferred"][0].get("overlapsWith"), "A")
        lines = [line for line in result.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, result.stderr)
        for key in ("'A'", "'B'"):
            self.assertIn(key, lines[0])
        self.assertIn("overlapping ownershiphint", lines[0].lower())
        self.assertIn("wave 0", lines[0].lower())

    def test_declared_grouped_wave_overlap_still_fails(self):
        """A grouped wave (1 and up) is the planner asserting parallelism; hints that cannot
        deliver it are a plan defect, not something to quietly serialize."""
        result = self._run_overlap_plan(1)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("overlapping ownershipHint", result.stderr)
        self.assertEqual(result.stdout.strip(), "", "a rejected plan must print no dispatchable output")

    def test_grouped_wave_overlap_raises_without_warning(self):
        sidecar, snapshot = self._overlap_plan(1)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(waves.BuildError):
            waves.derive(sidecar, waves.validate_snapshot(snapshot, sidecar))
        self.assertEqual(stderr.getvalue(), "")

    def test_every_harness_ships_a_specifier_that_owns_the_seal(self):
        """The specifier creates the workspace, proves honest RED, and seals. If any of
        that drifts back into the builder, the agent judged by the tests wrote them."""
        authors = [
            ROOT.parents[1] / "agents" / "claude" / "specifier.md",
            ROOT.parents[1] / "agents" / "codex" / "specifier.md",
            ROOT.parents[1] / "agents" / "agy" / "specifier" / "agent.md",
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
        for phrase in ("`specifier`", "Phase 1", "Phase 2", "integrator"):
            self.assertIn(phrase, skill)
        self.assertLess(skill.index("Phase 1"), skill.index("Phase 2"))
        self.assertIn("never dispatch a builder for an issue with no seal", skill)

    def test_skill_documents_redispatch_cap(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for phrase in ("`status:done`", "at most twice", "stalled", "escalate to the human"):
            self.assertIn(phrase, skill)

    # --- dependency-gated selection with ownership deferral ----------------
    def _pull_forward(self):
        """The pull-forward fixture, run as a process, with its declared expectation."""
        result = run_helper(PULL_FORWARD / "plan.sidecar.json", PULL_FORWARD / "issue-state.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        return result, json.loads(result.stdout)

    @staticmethod
    def _entry(entries, key):
        return next((item for item in entries if item["key"] == key), None)

    def test_pull_forward_selects_a_ready_later_wave_issue(self):
        """One straggler must not freeze an issue whose own dependencies are already merged.
        `Core` is an unfinished wave-1 issue; `Docs` is declared in wave 2 and depends only on
        the finished `Foundation`, so it is selected in the same round and flagged as pulled
        forward. `currentWave` keeps its old meaning — the earliest unfinished declared wave —
        as reporting, never as a filter."""
        result, output = self._pull_forward()
        keys = [item["key"] for item in output["unblocked"]]
        self.assertEqual(keys, ["Core", "Docs"])

        core = self._entry(output["unblocked"], "Core")
        docs = self._entry(output["unblocked"], "Docs")
        for entry in (core, docs):
            self.assertIn("pulledForward", entry, "unblocked entries must report pulledForward")
        self.assertIs(docs["pulledForward"], True, "a later declared wave was pulled forward")
        self.assertEqual(docs["wave"], 2)
        self.assertIs(core["pulledForward"], False, "an issue at the current wave is not pulled forward")
        self.assertEqual(core["wave"], 1)

        # currentWave is still the earliest declared wave holding an unfinished issue.
        sidecar = json.loads((PULL_FORWARD / "plan.sidecar.json").read_text(encoding="utf-8"))
        unfinished = [issue for issue in sidecar["issues"] if issue["key"] not in output["done"]]
        self.assertEqual(output["currentWave"], min(issue["wave"] for issue in unfinished))
        self.assertEqual(output["currentWave"], 1)
        self.assertEqual(output["done"], ["Foundation"])

        expected = json.loads((PULL_FORWARD / "expected-waves.json").read_text(encoding="utf-8"))
        self.assertEqual(output, expected)
        self.assertEqual(result.stdout, run_helper(
            PULL_FORWARD / "plan.sidecar.json", PULL_FORWARD / "issue-state.json"
        ).stdout)

    def test_blocked_issue_is_never_selected(self):
        """Pulling work forward must not pull it forward *past its dependencies*. `Followup`
        depends on the unfinished `Core`, so it is neither dispatchable nor merely deferred."""
        _, output = self._pull_forward()
        sidecar = json.loads((PULL_FORWARD / "plan.sidecar.json").read_text(encoding="utf-8"))
        followup = next(issue for issue in sidecar["issues"] if issue["key"] == "Followup")
        self.assertEqual(followup["dependsOn"], ["Core"])
        self.assertNotIn("Core", output["done"], "the fixture must keep Followup's dependency unfinished")
        self.assertNotIn("Followup", [item["key"] for item in output["unblocked"]])
        self.assertIn("deferred", output)
        self.assertNotIn("Followup", [item["key"] for item in output["deferred"]])

    def test_overlapping_candidate_is_deferred_not_dispatched(self):
        """`Sweep` is ready — it has no dependencies at all — but its deliberately coarse
        `src/**` hint collides with the already-selected `Core`. Selection order is by declared
        wave, so the coarse late hint defers itself instead of starving what it overlaps, and
        nothing overlapping is ever handed out concurrently."""
        result, output = self._pull_forward()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Sweep", [item["key"] for item in output["unblocked"]])
        self.assertIn("deferred", output, "the dry-run must report the candidates it held back")
        deferred = self._entry(output["deferred"], "Sweep")
        self.assertIsNotNone(deferred, "a ready but overlapping candidate must be reported as deferred")
        self.assertEqual(deferred["overlapsWith"], "Core")
        self.assertEqual(deferred["ownershipHint"], "src/**")
        self.assertEqual(deferred["wave"], 3)
        self.assertEqual(deferred["number"], 204)
        self.assertTrue(
            waves.globs_overlap(deferred["ownershipHint"], self._entry(output["unblocked"], "Core")["ownershipHint"]),
            "the fixture must actually collide, or this test proves nothing",
        )
        hints = [item["ownershipHint"] for item in output["unblocked"]]
        for index, first in enumerate(hints):
            for second in hints[index + 1:]:
                self.assertFalse(
                    waves.globs_overlap(first, second),
                    f"concurrently dispatchable hints must be disjoint: {first!r} and {second!r}",
                )

    def _documented_waves_command(self, fixture):
        """The `waves.py` invocation SKILL.md actually publishes for a given fixture."""
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        blocks = [
            block for block in re.findall(r"```(?:bash|sh)\n(.*?)```", skill, re.DOTALL)
            if "waves.py" in block and fixture in block
        ]
        self.assertEqual(
            len(blocks), 1,
            f"SKILL.md must document exactly one offline dry-run over {fixture}",
        )
        lines = [
            line for line in blocks[0].splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        return "\n".join(lines).strip()

    def test_shipped_demo_selection_is_unchanged_and_deterministic(self):
        """The new fields must not move the shipped demo's outcome: `API` and `UI` remain the
        two dispatchable issues, neither pulled forward, with nothing deferred. Run the command
        SKILL.md publishes, not a restatement of it."""
        command = self._documented_waves_command("examples/plan.sidecar.json")
        runs = [
            subprocess.run(
                ["bash", "-c", command], cwd=REPO_ROOT, text=True, capture_output=True, check=False,
            )
            for _ in range(2)
        ]
        for run in runs:
            self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(runs[0].stdout, runs[1].stdout, "the offline dry-run must be byte-identical")
        output = json.loads(runs[0].stdout)
        expected = json.loads((EXAMPLES / "expected-waves.json").read_text(encoding="utf-8"))
        self.assertEqual(output, expected)
        self.assertEqual([item["key"] for item in output["unblocked"]], ["API", "UI"])
        for item in output["unblocked"]:
            self.assertIs(item["pulledForward"], False, item)
        self.assertEqual(output["deferred"], [])
        self.assertEqual(output["currentWave"], 2)

    def test_skill_text_defines_dependency_gated_selection(self):
        """The prose the orchestrator reads has to describe the selection it will actually get:
        dependency-gated, checked for ownership across the whole in-flight set, with collisions
        deferred to a later round rather than serialized by hand."""
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        retired = (
            "The current wave is every unblocked, not-done issue in the earliest unfinished declared wave.",
            "must be serialized by hand",
        )
        for phrase in retired:
            # assertNotIn would dump the whole SKILL.md into the failure report.
            self.assertTrue(phrase not in skill, f"retired wave-selection prose survives: {phrase!r}")
        for phrase in (
            "regardless of declared wave",   # selection is gated on dependencies, not on the wave
            "earliest unfinished declared wave",  # currentWave keeps its meaning, as reporting
            "in-flight set",                 # the ownership check spans every candidate
            "deferred",
            "later round",
            "pulled forward",
        ):
            self.assertTrue(phrase in skill, f"SKILL.md must state: {phrase!r}")
        # Pins other tests depend on, restated here so this edit cannot quietly drop them.
        for phrase in (
            "current wave",
            "combined GREEN",
            "closed **and** (`status:done` or `state_reason == completed`)",
            "waves.py",
        ):
            self.assertTrue(phrase in skill, f"pinned prose lost: {phrase!r}")
        # The offline demonstration gains the pull-forward fixture, and exactly one capture
        # command may remain: test_documented_capture_command_produces_a_valid_snapshot
        # requires a single `gh ... | jq` block.
        self._documented_waves_command("examples/pull-forward/plan.sidecar.json")
        self._documented_capture_command()


# --- speculative next-round specifiers ---------------------------------------------
# Anchors for reading `skills/build/SKILL.md` as prose rather than as a bag of words.
SPECULATION = re.compile(r"specul", re.IGNORECASE)
# A numbered wave-loop step: a digit at the very start of a line. Continuation
# paragraphs inside a step are indented, so they never match.
WAVE_STEP = re.compile(r"^(\d+)\.\s", re.MULTILINE)
# Sentence boundaries, stepping over the markdown emphasis and code punctuation that
# trails a full stop (`... a speculative builder.** Phase 2 starts ...`).
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[*_`\"')\]]*\s+")


class SpeculativeSpecifierTests(unittest.TestCase):
    """SKILL.md must permit speculative next-round specifiers while the integrator runs,
    and must state what that permission costs.

    Every oracle reads the statement *in place* — inside the speculation subsection of
    wave loop step 5, the step that runs the integrator — because an allowance stated
    anywhere else is not the allowance the issue asks for, and words scattered across
    sections that mean other things would satisfy a plain file-wide substring search.
    """

    def skill(self):
        return (ROOT / "SKILL.md").read_text(encoding="utf-8")

    def wave_loop(self):
        parts = self.skill().split("\n## Wave loop\n", 1)
        self.assertEqual(len(parts), 2, "SKILL.md must keep its `## Wave loop` section")
        return parts[1].split("\n## ", 1)[0]

    def wave_loop_steps(self):
        """The wave loop's numbered steps, in document order, keyed by their number."""
        section = self.wave_loop()
        marks = [(match.group(1), match.start()) for match in WAVE_STEP.finditer(section)]
        self.assertTrue(marks, "the wave loop must keep its numbered steps")
        steps = {}
        for index, (number, start) in enumerate(marks):
            end = marks[index + 1][1] if index + 1 < len(marks) else len(section)
            steps[number] = section[start:end]
        return steps

    def speculation_subsection(self):
        """The contiguous run of paragraphs inside wave loop step 5 that discusses
        speculation — first such paragraph through last. Anchoring to step 5 is the point:
        the allowance exists only to fill the integrator run it overlaps."""
        step = self.wave_loop_steps().get("5")
        self.assertIsNotNone(step, "wave loop step 5 — the integrator step — must exist")
        paragraphs = [para.strip() for para in re.split(r"\n\s*\n", step) if para.strip()]
        hits = [index for index, para in enumerate(paragraphs) if SPECULATION.search(para)]
        self.assertTrue(
            hits,
            "wave loop step 5 must carry a speculative-specifier subsection: while the "
            "integrator runs the combined suite, the orchestrator may dispatch specifiers "
            "for issues that are not unblocked yet.\nStep 5 currently reads:\n" + step,
        )
        return "\n\n".join(paragraphs[hits[0]:hits[-1] + 1])

    @staticmethod
    def sentences(text):
        flat = re.sub(r"\s+", " ", text).strip()
        return [part for part in SENTENCE_SPLIT.split(flat) if part]

    def sentence(self, text, patterns, why):
        """The first sentence satisfying every pattern — returned so a caller can assert
        further about that same sentence rather than about the document at large."""
        matches = [
            candidate for candidate in self.sentences(text)
            if all(re.search(pattern, candidate, re.IGNORECASE) for pattern in patterns)
        ]
        self.assertTrue(
            matches,
            f"{why}\nNo single sentence matched all of {patterns!r}.\nSubsection:\n{text}",
        )
        return matches[0]

    def test_speculation_is_optional_not_default(self):
        """An allowance has to read as an allowance: `may`, next to the integrator run it
        overlaps, doing the unrelaxed Phase 1 — and, in the same subsection, the statement
        that a run which never speculates is not thereby a worse run."""
        subsection = self.speculation_subsection()
        permission = self.sentence(
            subsection,
            [r"\bmay\b", r"dispatch", r"specifier", r"integrator"],
            "the subsection must say that, while the integrator runs, the orchestrator MAY "
            "dispatch `specifier` agents for issues that are not unblocked yet",
        )
        self.assertNotRegex(
            permission,
            r"\b(must|shall|always|should)\b",
            "speculation is permitted, never required; this sentence reads as an "
            "instruction:\n" + permission,
        )
        self.sentence(
            subsection,
            [r"(acceptanceTests|acceptance tests|failing tests)", r"\bseal", r"\bRED\b"],
            "the subsection must say the speculative specifier runs the standard Phase 1 "
            "unrelaxed: acceptance tests written as failing tests, honest RED, then seal",
        )
        self.assertRegex(
            subsection,
            r"(?i)opportunistic",
            "the subsection must call speculation opportunistic:\n" + subsection,
        )
        self.sentence(
            subsection,
            [r"\bdefault\b", r"\b(never|not|no)\b"],
            "the subsection must say speculation is never the default",
        )
        self.sentence(
            subsection,
            [r"(skips?|skipping|without|forgo\w*|omits?)",
             r"(deficien\w*|correct|complete|fine|valid)"],
            "the subsection must say the plain sequence stays correct — a run that skips "
            "speculation is not deficient",
        )

    def test_speculation_disqualifier_is_stated(self):
        """The one case speculation cannot cover: acceptance tests that cannot express
        their failure until the dependency's code is merged. Sealing one of those buys a
        RED that proves nothing, so the subsection must name it and route it to `blocked`."""
        subsection = self.speculation_subsection()
        self.sentence(
            subsection,
            [r"\b(imports?|compiles?)\b",
             r"(dependenc\w*|merged)",
             r"(cannot|can't|can not|must not|never|ineligible|not eligible|disqualif\w*)",
             r"specul"],
            "the subsection must disqualify from speculation an issue whose acceptance "
            "tests need the dependency's merged code to import or compile",
        )
        self.assertRegex(
            subsection,
            r"(?i)(hollow|proves? nothing|meaningless|vacuous|false RED)",
            "the subsection must say why the disqualifier exists: a test that cannot "
            "express its failure on the current base produces a hollow RED.\nSubsection:\n"
            + subsection,
        )
        self.sentence(
            subsection,
            [r"blocked", r"\bseal", r"(rather than|instead of|\bnot\b)"],
            "the subsection must say the specifier returns `blocked` rather than sealing a "
            "test it cannot honestly prove red on the current base",
        )

    def test_bounce_cost_and_reseal_are_stated(self):
        """Speculation is cheap only while the wave lands. The subsection has to price the
        bounce, name the command that amends the seal, and say plainly that no mechanism
        will catch a stale speculative seal for you."""
        subsection = self.speculation_subsection()
        self.assertIn(
            "tdd-guard reseal --reason",
            subsection,
            "the subsection must name the exact command that amends a stale speculative "
            "seal: `tdd-guard reseal --reason <text>`.\nSubsection:\n" + subsection,
        )
        self.sentence(
            subsection,
            [r"(bounces?|offending PR|sent back|goes back|rejects?)",
             r"(re-?prov\w*|re-?seal\w*|redo\w*|redone|again)"],
            "the subsection must name the rework a bounced wave costs a speculative seal",
        )
        self.sentence(
            subsection,
            [r"re-?prov\w*", r"merged base"],
            "the subsection must say the speculative seal has to be re-proved on the "
            "merged base",
        )
        self.sentence(
            subsection,
            [r"re-?scope\w*", r"(throws?|thrown|discard\w*|wastes?|wasted|lost|away)"],
            "the subsection must say a re-scoped issue throws that specifier's work away "
            "entirely",
        )
        self.sentence(
            subsection,
            [r"\b(nothing|no|not)\b",
             r"(mechanical\w*|automatic\w*|automated)",
             r"(stale\w*)"],
            "the subsection must say nothing mechanical catches a stale speculative seal — "
            "the guard binds a seal to the sealed tests and the red command, not to the "
            "base it was proved on — so the discipline is textual",
        )

    def test_no_speculative_builder(self):
        """Speculation stops at the seal. A builder dispatched before its dependencies
        merge implements against a base that does not yet exist, so Phase 2 waits, and the
        builder re-proves the inherited seal on the merged base before writing anything."""
        subsection = self.speculation_subsection()
        self.sentence(
            subsection,
            [r"builder", r"\b(never|no|not)\b", r"specul"],
            "the subsection must rule out a speculative builder outright",
        )
        self.sentence(
            subsection,
            [r"(phase 2|builder)", r"(only after|not until|once)", r"(dependenc\w*|deps)",
             r"merged"],
            "the subsection must say Phase 2 for a speculated issue starts only after its "
            "dependencies are merged, in a workspace on the merged base",
        )
        self.sentence(
            subsection,
            [r"builder", r"re-?prov\w*", r"sealed tests", r"\bfail"],
            "the subsection must say the builder re-proves the sealed tests still fail on "
            "the merged base, for the right reason, before implementing",
        )
        self.sentence(
            subsection,
            [r"(passes?|no longer fails?|fails? differently)", r"specifier", r"re-?seal"],
            "the subsection must say a sealed test that now passes, or fails differently, "
            "goes back to a `specifier` to reseal",
        )

    def test_build_skill_invariants_survive(self):
        """The subsection is an addition, not a rewrite. With it in place, the wave loop
        still runs 1..6 unrenumbered, the two phases keep their order, the ADR-0007
        boundary keeps its position, one capture command survives, and no sentence about
        the seal, the phases, or merging on combined GREEN has been softened to make room."""
        self.speculation_subsection()  # the edit landed; now check nothing else moved
        skill = self.skill()

        self.assertEqual(
            list(self.wave_loop_steps()),
            ["1", "2", "3", "4", "5", "6"],
            "the wave loop keeps six numbered steps, in order and unrenumbered",
        )
        self.assertLess(
            skill.index("Phase 1"), skill.index("Phase 2"),
            "Phase 1 must still precede Phase 2",
        )
        for phrase in (
            "combined GREEN",
            "sole completion authority",
            "never dispatch a builder for an issue with no seal",
            "Never run the two phases concurrently",
            "Treat every PR as tested on its old base",
            "Merge only after combined green",
            "It cannot edit the sealed tests: the guard denies those edits outright.",
        ):
            # `assertIn` would dump the whole SKILL.md into the failure report.
            self.assertTrue(phrase in skill, f"pinned prose lost to the edit: {phrase!r}")

        # ADR 0007's boundary is still the second paragraph after the title.
        after_title = skill.split("\n# ", 1)[1].split("\n\n", 1)[1]
        boundary = after_title.split("\n\n")[1]
        self.assertTrue(
            boundary.startswith("You are the orchestrator ([ADR 0007]"),
            "the canonical ADR-0007 paragraph must stay the second paragraph after the "
            f"title; found instead:\n{boundary}",
        )
        self.assertIn("You never read or edit the target project's code", boundary)

        # Exactly one `gh ... | jq` capture block, as
        # test_documented_capture_command_produces_a_valid_snapshot requires.
        blocks = [
            block for block in re.findall(r"```(?:bash|sh)\n(.*?)```", skill, re.DOTALL)
            if "gh " in block and "jq" in block
        ]
        self.assertEqual(
            len(blocks), 1,
            "SKILL.md must keep exactly one copy-pasteable `gh ... | jq ...` capture command",
        )



if __name__ == "__main__":
    unittest.main()
