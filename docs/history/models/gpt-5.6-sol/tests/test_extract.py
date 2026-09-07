"""Acceptance tests for the official GPT-5.6 Sol prompting extract (#148)."""

from __future__ import annotations

import datetime
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
GUIDE = ROOT / "docs" / "models" / "gpt-5.6-sol" / "prompting.md"
CHECK_GUIDES = ROOT / "docs" / "models" / "check" / "check_guides.py"
MODEL = "gpt-5.6-sol"
OFFICIAL_URL = (
    "https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6"
)
LEVER_HEADINGS = (
    "Lean prompts",
    "Goals, constraints, and success criteria",
    "Intentional reasoning effort",
    "Relevant tools",
    "Autonomy and approval boundaries",
    "Multi-agent use",
    "Evidence-grounded progress",
    "Final completeness",
)


def load_checker():
    spec = importlib.util.spec_from_file_location("workcell_check_guides", CHECK_GUIDES)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load guide checker from {CHECK_GUIDES}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_check(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(CHECK_GUIDES), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


def markdown_sections(body: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    heading: str | None = None
    for line in body.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            heading = match.group(1)
            sections[heading] = []
        elif heading is not None:
            sections[heading].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


class GPT56SolExtractAcceptanceTests(unittest.TestCase):
    def test_gpt_guide_provenance_and_content(self):
        """gpt-guide-provenance-and-content (unit)."""
        self.assertTrue(
            GUIDE.is_file(),
            f"Expected the official {MODEL} extract at {GUIDE.relative_to(ROOT)}",
        )

        checker = load_checker()
        fields, body = checker.parse_frontmatter(GUIDE.read_text(encoding="utf-8"))

        self.assertEqual(fields.get("model"), MODEL)
        self.assertEqual(fields.get("official_source_urls"), [OFFICIAL_URL])

        fetched_date = fields.get("fetched_date", "")
        try:
            parsed_date = datetime.date.fromisoformat(fetched_date)
        except (TypeError, ValueError) as exc:
            self.fail(f"fetched_date must be an ISO date, got {fetched_date!r}: {exc}")
        self.assertLessEqual(parsed_date, datetime.date.today())

        extractor = fields.get("extractor_version", "")
        self.assertRegex(extractor, r"^\d+\.\d+\.\d+$")

        digests = fields.get("normalized_source_digests")
        self.assertIsInstance(digests, dict)
        self.assertEqual(set(digests), {OFFICIAL_URL})
        self.assertRegex(digests[OFFICIAL_URL], r"^[0-9a-f]{64}$")

        sections = markdown_sections(body)
        for heading in LEVER_HEADINGS:
            with self.subTest(lever=heading):
                self.assertIn(heading, sections)
                section = sections[heading]
                self.assertRegex(
                    section,
                    rf"(?m)^Source:\s*.*{re.escape(OFFICIAL_URL)}.*$",
                    f"{heading!r} must attribute its official source URL",
                )
                self.assertRegex(
                    section,
                    r"(?m)^>\s+\S",
                    f"{heading!r} must include a selected official-source passage",
                )

        self.assertRegex(
            body,
            r"(?is)(?:Codex[^\n]{0,160}API-only|API-only[^\n]{0,160}Codex)",
            "API-only guidance unavailable through Codex must be marked explicitly",
        )

    def test_gpt_guide_is_live_fresh(self):
        """gpt-guide-is-live-fresh (integration)."""
        live = run_check("--check", "--model", MODEL)
        self.assertEqual(
            live.returncode,
            0,
            f"Live official-source check failed:\nstdout: {live.stdout}\nstderr: {live.stderr}",
        )

        changed_html = (
            "<html><body><main>Injected upstream change that cannot match the "
            "recorded GPT-5.6 Sol digest or selected passages.</main></body></html>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            fixtures_dir = Path(tmp)
            fixtures = {OFFICIAL_URL: {"status": 200, "content": changed_html}}
            (fixtures_dir / "fixtures.json").write_text(
                json.dumps(fixtures), encoding="utf-8"
            )
            drift = run_check(
                "--check",
                "--model",
                MODEL,
                "--fixtures-dir",
                str(fixtures_dir),
            )

        output = drift.stdout + drift.stderr
        self.assertNotEqual(drift.returncode, 0, output)
        self.assertIn("drift", output.lower())
        self.assertIn(MODEL, output)
        self.assertIn(OFFICIAL_URL, output)


if __name__ == "__main__":
    unittest.main()
