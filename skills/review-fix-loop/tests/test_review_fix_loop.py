import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "loop_state.py"
REVIEW_EXAMPLES = ROOT.parents[0] / "code-review" / "examples"


def run(state, *args):
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--state", str(state), *map(str, args)],
        cwd=ROOT, env=environment, text=True, capture_output=True,
    )


def review(findings, verdict="block"):
    return {"verdict": verdict, "findings": findings}


def finding(claim, file="src/a.py", severity="high"):
    return {"file": file, "claim": claim, "severity": severity}


class ReviewFixLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "loop.json"

    def write_review(self, name, payload):
        path = Path(self.tmp.name) / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_init_defaults_to_loop_branch_and_ten_passes(self):
        result = run(self.state, "init")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["branch"], "loop-branch")
        self.assertEqual(output["maxIterations"], 10)
        self.assertEqual(output["iteration"], 0)
        self.assertTrue(output["continue"])

    def test_init_refuses_to_clobber_a_running_loop_without_force(self):
        self.assertEqual(run(self.state, "init").returncode, 0)
        clobber = run(self.state, "init")
        self.assertNotEqual(clobber.returncode, 0)
        self.assertIn("already exists", clobber.stderr.lower())
        self.assertEqual(run(self.state, "init", "--force").returncode, 0)

    def test_record_without_init_is_an_error(self):
        source = self.write_review("r.json", review([finding("x")]))
        result = run(self.state, "record", source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("run `init` first", result.stderr)

    def test_empty_findings_converge(self):
        run(self.state, "init")
        source = self.write_review("clean.json", review([], verdict="approve"))
        output = json.loads(run(self.state, "record", source).stdout)
        self.assertEqual(output["status"], "converged")
        self.assertFalse(output["continue"])

    def test_progress_keeps_the_loop_running(self):
        run(self.state, "init")
        first = self.write_review("a.json", review([finding("one"), finding("two")]))
        second = self.write_review("b.json", review([finding("two")]))
        self.assertTrue(json.loads(run(self.state, "record", first).stdout)["continue"])
        output = json.loads(run(self.state, "record", second).stdout)
        self.assertTrue(output["continue"])
        self.assertEqual(output["iteration"], 2)

    def test_an_identical_second_pass_stalls_the_loop(self):
        """The fixer changed nothing that mattered; another pass would waste a review."""
        run(self.state, "init")
        same = self.write_review("same.json", review([finding("one"), finding("two")]))
        self.assertTrue(json.loads(run(self.state, "record", same).stdout)["continue"])
        output = json.loads(run(self.state, "record", same).stdout)
        self.assertEqual(output["status"], "stalled")
        self.assertFalse(output["continue"])
        self.assertIn("identical finding set", output["reason"])

    def test_fingerprint_ignores_order_and_line_but_not_content(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import loop_state

        a, b = finding("one"), finding("two", file="src/b.py")
        self.assertEqual(loop_state.fingerprint([a, b]), loop_state.fingerprint([b, a]))
        moved = dict(a, line=999)
        self.assertEqual(loop_state.fingerprint([a]), loop_state.fingerprint([moved]))
        self.assertNotEqual(loop_state.fingerprint([a]), loop_state.fingerprint([a, b]))

    def test_loop_is_bounded_even_when_findings_keep_changing(self):
        """The bound is the safety property: a fixer that trades one finding for
        another must not loop forever."""
        run(self.state, "init", "--max-iterations", "3")
        statuses = []
        for n in range(3):
            source = self.write_review(f"r{n}.json", review([finding(f"claim-{n}")]))
            statuses.append(json.loads(run(self.state, "record", source).stdout)["status"])
        self.assertEqual(statuses, ["running", "running", "exhausted"])

        extra = self.write_review("extra.json", review([finding("another")]))
        refused = run(self.state, "record", extra)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("already finished", refused.stderr.lower())

    def test_status_reports_without_advancing(self):
        run(self.state, "init")
        source = self.write_review("r.json", review([finding("one")]))
        run(self.state, "record", source)
        first = json.loads(run(self.state, "status").stdout)
        second = json.loads(run(self.state, "status").stdout)
        self.assertEqual(first, second)
        self.assertEqual(first["iteration"], 1)

    def test_malformed_input_is_rejected(self):
        run(self.state, "init")
        cases = (
            ({"findings": []}, "verdict must be one of"),
            ({"verdict": "block", "findings": "nope"}, "must be an array"),
            ({"verdict": "block", "findings": [{"file": "a.py", "claim": ""}]}, "non-empty string"),
        )
        for payload, message in cases:
            with self.subTest(message=message):
                source = self.write_review("bad.json", payload)
                result = run(self.state, "record", source)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr.lower())

        bad_branch = run(Path(self.tmp.name) / "b.json", "init", "--branch", "bad branch")
        self.assertNotEqual(bad_branch.returncode, 0)
        self.assertIn("plain branch name", bad_branch.stderr)

    def test_accepts_a_real_merged_review_from_the_code_review_skill(self):
        run(self.state, "init")
        result = run(self.state, "record", REVIEW_EXAMPLES / "expected-review.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output["continue"])
        self.assertEqual(output["latest"]["findings"], 2)
        self.assertEqual(output["latest"]["blocking"], 1)

    def test_skill_publishes_its_branch_bound_and_stop_conditions(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "loop-branch", "--max-iterations 10", "code-review", "builder",
            "converged", "stalled", "exhausted",
            "Never run this loop on `main`", "never merge `loop-branch`",
            "loop_state.py record",
        ):
            self.assertIn(phrase, skill)

    def test_nit_only_review_converges_at_medium_threshold(self):
        """Findings below --min-severity are reported but never block convergence."""
        run(self.state, "init", "--min-severity", "medium")
        source = self.write_review("nits.json", review(
            [finding("trailing space", severity="nit"), finding("rename", severity="nit")],
            verdict="approve-with-nits",
        ))
        result = run(self.state, "record", source)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "converged")
        self.assertFalse(output["continue"])
        self.assertEqual(output["latest"]["findings"], 2)
        self.assertEqual(output["latest"]["blocking"], 0)
        self.assertEqual(output["minSeverity"], "medium")

    def test_findings_at_threshold_still_block(self):
        run(self.state, "init", "--min-severity", "medium")
        source = self.write_review("m.json", review(
            [finding("real", severity="medium"), finding("tidy", severity="low")],
        ))
        output = json.loads(run(self.state, "record", source).stdout)
        self.assertEqual(output["status"], "running")
        self.assertEqual(output["latest"]["blocking"], 1)

    def test_invalid_min_severity_is_rejected(self):
        result = run(self.state, "init", "--min-severity", "bogus")
        self.assertNotEqual(result.returncode, 0)
        for value in ("critical", "high", "medium", "low", "nit"):
            self.assertIn(value, result.stderr)
        self.assertFalse(self.state.exists())

    def test_skill_states_driver_requirement_and_uses_jj_branching(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("/loop", skill)
        self.assertIn("Claude Code", skill)
        self.assertRegex(skill, r"(?i)manual")
        self.assertNotIn("git switch -c", skill)
        self.assertNotIn("/tmp", skill)
        self.assertIn("--min-severity", skill)


if __name__ == "__main__":
    unittest.main()
