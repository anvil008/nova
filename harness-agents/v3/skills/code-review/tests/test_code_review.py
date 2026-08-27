import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "merge_findings.py"
EXAMPLES = ROOT / "examples"
AGENT = ROOT.parents[1] / "agents" / "code-reviewer" / "AGENT.md"


def run_helper(*args):
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *map(str, args)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
    )


class CodeReviewSkillTests(unittest.TestCase):
    def test_agent_requires_exact_no_prose_envelope_and_empty_findings_form(self):
        agent = AGENT.read_text(encoding="utf-8")
        self.assertIn("Return exactly one JSON object and no prose", agent)
        examples = re.findall(r"```json\n(.*?)\n```", agent, flags=re.DOTALL)
        envelope = json.loads(examples[0])
        empty = json.loads(examples[1])
        self.assertEqual(set(envelope), {"lens", "findings"})
        self.assertEqual(envelope["lens"], envelope["findings"][0]["lens"])
        self.assertEqual(empty, {"lens": "tests", "findings": []})

    def test_equal_strength_duplicate_selection_is_permutation_invariant(self):
        correctness = {
            "lens": "correctness",
            "findings": [{
                "file": "src/tie.py", "line": 8, "severity": "medium", "lens": "correctness",
                "claim": "Shared claim", "failureScenario": "Correctness scenario.", "confidence": 0.8,
            }],
        }
        tests = {
            "lens": "tests",
            "findings": [{
                "file": "src/tie.py", "line": 8, "severity": "medium", "lens": "tests",
                "claim": "Shared claim", "failureScenario": "Tests scenario.", "confidence": 0.8,
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "correctness.json"
            second = Path(tmp) / "tests.json"
            first.write_text(json.dumps(correctness), encoding="utf-8")
            second.write_text(json.dumps(tests), encoding="utf-8")
            forward = run_helper("--dedupe-only", first, second)
            reverse = run_helper("--dedupe-only", second, first)
        self.assertEqual(forward.returncode, 0, forward.stderr)
        self.assertEqual(reverse.returncode, 0, reverse.stderr)
        self.assertEqual(forward.stdout, reverse.stdout)
        candidate = json.loads(forward.stdout)["candidates"][0]
        self.assertEqual(candidate["lens"], "correctness")
        self.assertEqual(candidate["failureScenario"], "Correctness scenario.")

    def test_example_dry_run_is_deterministic_and_matches_expected_report(self):
        arguments = [
            "--verification", EXAMPLES / "verification.json",
            EXAMPLES / "correctness.json", EXAMPLES / "tests.json",
            EXAMPLES / "security.json",
        ]
        expected = json.loads((EXAMPLES / "expected-review.json").read_text(encoding="utf-8"))
        first = run_helper(*arguments)
        second = run_helper(*arguments)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(json.loads(first.stdout), expected)
        self.assertEqual(expected["verdict"], "block")
        self.assertEqual(expected["candidateCount"], 3)
        self.assertEqual(expected["droppedCount"], 1)
        self.assertEqual([finding["severity"] for finding in expected["findings"]], ["high", "low"])

    def test_dedupe_only_uses_tuple_key_and_strongest_representative(self):
        result = run_helper(
            "--dedupe-only",
            EXAMPLES / "correctness.json", EXAMPLES / "tests.json", EXAMPLES / "security.json",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["candidateCount"], 3)
        duplicate = next(
            finding for finding in output["candidates"]
            if finding["claim"] == "Empty tokens bypass authentication"
        )
        self.assertEqual(duplicate["lens"], "security")
        self.assertEqual(duplicate["severity"], "high")
        self.assertEqual(duplicate["confidence"], 0.97)

    def test_requires_exactly_one_adversarial_verification_per_candidate(self):
        verification = json.loads((EXAMPLES / "verification.json").read_text(encoding="utf-8"))
        verification["verifications"].pop()
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"
            missing.write_text(json.dumps(verification), encoding="utf-8")
            result = run_helper(
                "--verification", missing,
                EXAMPLES / "correctness.json", EXAMPLES / "tests.json", EXAMPLES / "security.json",
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing adversarial verification", result.stderr.lower())

        verification = json.loads((EXAMPLES / "verification.json").read_text(encoding="utf-8"))
        verification["verifications"].append(dict(verification["verifications"][0]))
        with tempfile.TemporaryDirectory() as tmp:
            duplicate = Path(tmp) / "duplicate.json"
            duplicate.write_text(json.dumps(verification), encoding="utf-8")
            result = run_helper(
                "--verification", duplicate,
                EXAMPLES / "correctness.json", EXAMPLES / "tests.json", EXAMPLES / "security.json",
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate adversarial verification", result.stderr.lower())

    def test_rejects_unknown_fields_lens_mismatch_and_unsafe_paths(self):
        source = json.loads((EXAMPLES / "correctness.json").read_text(encoding="utf-8"))
        cases = (
            (lambda value: value.update({"unexpected": True}), "unknown field"),
            (lambda value: value["findings"][0].update({"lens": "tests"}), "must match envelope lens"),
            (lambda value: value["findings"][0].update({"file": "../escape.py"}), "relative repository path"),
        )
        for mutate, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                invalid_source = json.loads(json.dumps(source))
                mutate(invalid_source)
                invalid = Path(tmp) / "invalid.json"
                invalid.write_text(json.dumps(invalid_source), encoding="utf-8")
                result = run_helper("--dedupe-only", invalid)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(message, result.stderr.lower())

    def test_verdict_thresholds_and_severity_order_are_deterministic(self):
        findings = {
            "lens": "correctness",
            "findings": [
                {
                    "file": "src/a.py", "line": 4, "severity": "nit", "lens": "correctness",
                    "claim": "Name is misleading", "failureScenario": "A maintainer reads the inverse meaning.",
                    "confidence": 0.8,
                },
                {
                    "file": "src/a.py", "line": 2, "severity": "medium", "lens": "correctness",
                    "claim": "Retry is skipped", "failureScenario": "A timeout returns immediately instead of retrying.",
                    "confidence": 0.9,
                },
            ],
        }
        verification = {
            "verifications": [
                {
                    "file": item["file"], "line": item["line"], "claim": item["claim"],
                    "substantiated": True, "refutationAttempt": "Tried the opposite control-flow branch.",
                    "evidence": "The branch remains reachable with the stated input.",
                }
                for item in findings["findings"]
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "findings.json"
            verified = Path(tmp) / "verification.json"
            source.write_text(json.dumps(findings), encoding="utf-8")
            verified.write_text(json.dumps(verification), encoding="utf-8")
            result = run_helper("--verification", verified, source)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["verdict"], "approve-with-nits")
        self.assertEqual([finding["severity"] for finding in output["findings"]], ["medium", "nit"])

    def test_empty_verified_report_is_approved(self):
        source = {"lens": "tests", "findings": []}
        verification = {"verifications": []}
        with tempfile.TemporaryDirectory() as tmp:
            findings_path = Path(tmp) / "findings.json"
            verification_path = Path(tmp) / "verification.json"
            findings_path.write_text(json.dumps(source), encoding="utf-8")
            verification_path.write_text(json.dumps(verification), encoding="utf-8")
            result = run_helper("--verification", verification_path, findings_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["verdict"], "approve")

    def test_agent_and_skill_publish_required_role_and_orchestration_boundaries(self):
        agent = AGENT.read_text(encoding="utf-8")
        frontmatter = agent.split("---", 2)[1].strip().splitlines()
        self.assertEqual([line.split(":", 1)[0] for line in frontmatter], ["name", "description", "tools"])
        self.assertEqual(frontmatter[0], "name: code-reviewer")
        self.assertEqual(frontmatter[2], "tools: Read, Grep, Glob, Bash, Skill")
        for phrase in (
            "ONE review lens", "correctness | security | performance | tests | api-contract",
            "actively try to break or refute", "failureScenario", "confidence",
            "No edits, ever", "do not spawn", "overall completion",
        ):
            self.assertIn(phrase, agent)

        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\nname: code-review\n"))
        for phrase in (
            "correctness and tests are always selected", "trust boundaries", "hot paths",
            "public surface", "applicable lenses, never a fixed N", "in parallel",
            "(file, line, claim)", "independent adversarial", "tries to refute",
            "DROP", "block", "approve-with-nits", "approve", "sole synthesis",
        ):
            self.assertIn(phrase, skill)


if __name__ == "__main__":
    unittest.main()
