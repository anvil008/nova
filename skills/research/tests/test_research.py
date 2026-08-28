import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "merge_research.py"
EXAMPLES = ROOT / "examples"
AGENT = ROOT.parents[1] / "agents" / "claude" / "research.md"


def run_helper(*reports):
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(EXAMPLES / "areas.json"), *map(str, reports)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
    )


class ResearchSkillTests(unittest.TestCase):
    def test_example_merge_is_deterministic_and_matches_expected_packet(self):
        reports = [EXAMPLES / "runtime.json", EXAMPLES / "code.json", EXAMPLES / "docs.json"]
        expected = json.loads((EXAMPLES / "expected-packet.json").read_text(encoding="utf-8"))
        first = run_helper(*reports)
        second = run_helper(*reversed(reports))
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(json.loads(first.stdout), expected)

    def test_deduplicates_exactly_by_area_source_finding(self):
        output = json.loads(run_helper(
            EXAMPLES / "runtime.json", EXAMPLES / "code.json", EXAMPLES / "docs.json"
        ).stdout)
        self.assertEqual(output["inputFindingCount"], 5)
        self.assertEqual(output["findingCount"], 4)
        code_findings = output["areas"][0]["findings"]
        duplicate = [item for item in code_findings if item["finding"] == "Retry defaults to three attempts."]
        self.assertEqual(len(duplicate), 1)
        self.assertEqual(duplicate[0]["evidence"], "config.py:18 sets attempts=3")

    def test_surfaces_conflicts_without_dropping_the_findings(self):
        output = json.loads(run_helper(
            EXAMPLES / "runtime.json", EXAMPLES / "code.json", EXAMPLES / "docs.json"
        ).stdout)
        self.assertEqual(len(output["conflicts"]), 1)
        conflict = output["conflicts"][0]
        self.assertEqual(conflict["topic"], "retry-default")
        self.assertEqual(conflict["positions"], ["three", "unbounded"])
        conflict_findings = [
            item for area in output["areas"] for item in area["findings"]
            if item["topic"] == "retry-default"
        ]
        self.assertEqual(len(conflict_findings), 2)

    def test_reports_missing_area_coverage_gaps_and_open_questions(self):
        result = run_helper(EXAMPLES / "code.json", EXAMPLES / "docs.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["coverage"]["missingAreas"], ["runtime"])
        self.assertIn("runtime: no research report was supplied", output["gaps"])
        self.assertIn("docs: Version applicability is unresolved.", output["gaps"])
        self.assertIn("docs: Which release changed retry semantics?", output["openQuestions"])
        self.assertFalse(output["coverage"]["complete"])

    def test_rejects_duplicate_area_reports_unknown_areas_and_invalid_shapes(self):
        cases = []
        cases.append(([EXAMPLES / "code.json", EXAMPLES / "code.json"], "duplicate report for area"))
        unknown = json.loads((EXAMPLES / "code.json").read_text(encoding="utf-8"))
        unknown["area"] = "unknown"
        unknown_field = json.loads((EXAMPLES / "code.json").read_text(encoding="utf-8"))
        unknown_field["extra"] = True
        with tempfile.TemporaryDirectory() as tmp:
            unknown_path = Path(tmp) / "unknown.json"
            invalid_path = Path(tmp) / "invalid.json"
            unknown_path.write_text(json.dumps(unknown), encoding="utf-8")
            invalid_path.write_text(json.dumps(unknown_field), encoding="utf-8")
            cases.extend((([unknown_path], "not declared"), ([invalid_path], "unknown field")))
            for reports, message in cases:
                with self.subTest(message=message):
                    result = run_helper(*reports)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(message, result.stderr.lower())

    def test_agent_is_portable_blind_read_only_and_returns_strict_envelope(self):
        agent = AGENT.read_text(encoding="utf-8")
        frontmatter = agent.split("---", 2)[1].strip().splitlines()
        self.assertEqual([line.split(":", 1)[0] for line in frontmatter], ["name", "description", "tools"])
        self.assertEqual(frontmatter[0], "name: research")
        self.assertEqual(frontmatter[2], "tools: Read, Grep, Glob, Bash, Skill")
        for phrase in (
            "exactly one assigned research area", "blind", "read-only", "Never edit",
            "Do not spawn", "Return exactly one JSON object and no prose",
            "coverage", "findings", "gaps", "openQuestions",
        ):
            self.assertIn(phrase, agent)
        examples = re.findall(r"```json\n(.*?)\n```", agent, flags=re.DOTALL)
        envelope = json.loads(examples[0])
        self.assertEqual(set(envelope), {"area", "coverage", "findings", "gaps", "openQuestions"})

    def test_skill_requires_real_area_split_parallel_blind_agents_and_primary_synthesis(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\nname: research\n"))
        for phrase in (
            "real research areas", "never a fixed N", "one read-only `research` agent per area",
            "in parallel", "blind", "(area, source, finding)", "without dropping",
            "coverage", "gaps", "open questions", "primary agent", "owns synthesis",
        ):
            self.assertIn(phrase, skill)


if __name__ == "__main__":
    unittest.main()
