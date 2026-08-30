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
RENDER = ROOT / "scripts" / "render_research.py"
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
        check=False,
    )


def topic_report(area, *findings):
    return {
        "area": area,
        "coverage": {"scope": f"{area} scope", "sourcesInspected": [f"{area} source"]},
        "findings": [
            {"source": f"{area}-src-{i}", "finding": f"{area} finding {i}", "evidence": f"{area} evidence {i}",
             "topic": "retry-default", **finding}
            for i, finding in enumerate(findings)
        ],
        "gaps": [],
        "openQuestions": [],
    }


def merge_docs_report(report):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "docs.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        return run_helper(path)


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
        stances = {
            item["position"]: item["stance"] for area in output["areas"] for item in area["findings"]
            if item["topic"] == "retry-default"
        }
        self.assertEqual(stances, {"three": "neutral", "unbounded": "contradicts"})
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
        keys = [line.split(":", 1)[0] for line in frontmatter]
        self.assertEqual(keys[:3], ["name", "description", "tools"])
        # model and effort come from agents/models.json; test_docs owns their values.
        self.assertEqual(set(keys) - {"name", "description", "tools"}, {"model", "effort"})
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
            "coverage", "gaps", "open questions", "orchestrator", "owns synthesis",
        ):
            self.assertIn(phrase, skill)

    def test_distinct_wording_without_contradicting_stance_is_not_a_conflict(self):
        report = topic_report("docs", {"position": "three attempts"}, {"position": "3 retries"})
        result = merge_docs_report(report)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["conflicts"], [])
        self.assertEqual([f["stance"] for f in output["areas"][0]["findings"]], ["neutral", "neutral"])

        report = topic_report("docs", {"position": "three", "stance": "supports"}, {"position": "unbounded"})
        output = json.loads(merge_docs_report(report).stdout)
        self.assertEqual(output["conflicts"], [], "supports plus neutral is agreement, not a conflict")

    def test_explicit_contradiction_is_exactly_one_conflict_listing_every_position(self):
        report = topic_report(
            "docs",
            {"position": "three", "stance": "supports"},
            {"position": "unbounded", "stance": "contradicts"},
            {"position": "three by default"},
        )
        result = merge_docs_report(report)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["conflicts"], [{"topic": "retry-default", "positions": ["three", "three by default", "unbounded"]}])
        self.assertEqual(output["findingCount"], 3)

    def test_rejects_unknown_stance_and_strips_string_fields(self):
        bad = topic_report("docs", {"position": "three", "stance": "disagrees"})
        result = merge_docs_report(bad)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stance", result.stderr)

        padded = topic_report("docs", {"position": " three "}, {"position": "three", "stance": " contradicts "})
        result = merge_docs_report(padded)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["conflicts"], [{"topic": "retry-default", "positions": ["three"]}])
        self.assertEqual([f["position"] for f in output["areas"][0]["findings"]], ["three", "three"])

    def test_skill_documents_stance_driven_conflicts(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for phrase in ("`stance`", "`contradicts`", "`supports`", "`neutral`", "byte-identical"):
            self.assertIn(phrase, skill)

    def test_renders_packet_and_synthesis_to_self_contained_html(self):
        packet = json.loads((EXAMPLES / "expected-packet.json").read_text(encoding="utf-8"))
        synthesis = {
            "verdict": "advisory",
            "summary": "Retry default is consistent; docs lag <b>code</b> {{FINDINGS}}.",
            "recommendations": [
                {"priority": "low", "title": "Update docs", "detail": "Mention attempts=3.", "refs": ["F1-01"]}
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            packet_path = Path(tmp) / "packet.json"
            synthesis_path = Path(tmp) / "synthesis.json"
            output = Path(tmp) / "out" / "research.html"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            synthesis_path.write_text(json.dumps(synthesis), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-B", str(RENDER), str(packet_path), str(output),
                 "--synthesis", str(synthesis_path), "--title", "Sample", "--generated-at", "2026-01-01T00:00:00Z"],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            html_text = output.read_text(encoding="utf-8")
            self.assertIn('id="F1-01"', html_text)
            self.assertIn('href="#F1-01"', html_text)
            self.assertIn("&lt;b&gt;code&lt;/b&gt;", html_text)
            self.assertIn("{{FINDINGS}}", html_text, "user text must not be re-substituted")
            self.assertNotRegex(html_text, r"\{\{[A-Z_]+\}\}(?!\.)")
            self.assertNotIn("<link", html_text)
            self.assertNotIn("<script src", html_text)

            bad = dict(synthesis, recommendations=[dict(synthesis["recommendations"][0], refs=["F9-99"])])
            synthesis_path.write_text(json.dumps(bad), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-B", str(RENDER), str(packet_path), str(output), "--synthesis", str(synthesis_path)],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("unknown finding F9-99", result.stderr)

            clean = dict(synthesis, verdict="clean")
            synthesis_path.write_text(json.dumps(clean), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-B", str(RENDER), str(packet_path), str(output), "--synthesis", str(synthesis_path)],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("clean verdict cannot carry recommendations", result.stderr)


if __name__ == "__main__":
    unittest.main()
