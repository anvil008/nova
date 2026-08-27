import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "docs_check.py"
EXAMPLES = ROOT / "examples"
GOOD_ADR = "## Status\nAccepted\n## Context\nx\n## Decision\ny\n## Consequences\nz\n"


def run(root, *args):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), str(root), *map(str, args)],
                          text=True, capture_output=True)


class DocsCheckTests(unittest.TestCase):
    def test_clean_sample_passes(self):
        r = run(EXAMPLES / "sample-repo")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertTrue(out["ok"])
        self.assertEqual(out["violations"], [])

    def test_oversized_instruction_file_flagged(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "CLAUDE.md").write_text("\n".join(f"line {i}" for i in range(200)), encoding="utf-8")
            r = run(t, "--max-instruction-lines", "120")
            self.assertNotEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertFalse(out["ok"])
            self.assertTrue(any("CLAUDE.md" in v and "budget" in v for v in out["violations"]))

    def test_malformed_adr_missing_section(self):
        with tempfile.TemporaryDirectory() as t:
            adr = Path(t, "docs", "adr"); adr.mkdir(parents=True)
            (adr / "0001-thing.md").write_text("# 1. Thing\n## Status\nA\n## Context\nx\n## Decision\ny\n", encoding="utf-8")
            r = run(t)
            self.assertNotEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertTrue(any("0001-thing.md" in v and "Consequences" in v for v in out["violations"]))

    def test_duplicate_adr_number(self):
        with tempfile.TemporaryDirectory() as t:
            adr = Path(t, "docs", "adr"); adr.mkdir(parents=True)
            (adr / "0001-a.md").write_text("# 1. A\n" + GOOD_ADR, encoding="utf-8")
            (adr / "0001-b.md").write_text("# 1. B\n" + GOOD_ADR, encoding="utf-8")
            r = run(t)
            self.assertNotEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertTrue(any("duplicate" in v.lower() and "1" in v for v in out["violations"]))

    def test_bad_adr_filename_flagged(self):
        with tempfile.TemporaryDirectory() as t:
            adr = Path(t, "docs", "adr"); adr.mkdir(parents=True)
            (adr / "my-decision.md").write_text(GOOD_ADR, encoding="utf-8")
            r = run(t)
            self.assertNotEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertTrue(any("my-decision.md" in v for v in out["violations"]))

    def test_docs_agent_and_skill_declare_the_standard(self):
        agent = (ROOT.parents[1] / "agents" / "docs" / "AGENT.md").read_text(encoding="utf-8")
        self.assertTrue(agent.startswith("---\nname: docs\n"))
        for phrase in ("Update, don't duplicate", "lean", "ADR", "docs_check"):
            self.assertIn(phrase, agent)
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\nname: docs\n"))
        self.assertIn("docs_check", skill)


if __name__ == "__main__":
    unittest.main()
