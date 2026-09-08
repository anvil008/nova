"""Acceptance tests for the Gemini 3.8 Flash prompting guide."""

from __future__ import annotations

import hashlib
import html
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODEL = "gemini-3.8-flash"
GUIDE = ROOT / "docs" / "models" / MODEL / "prompting.md"
CHECK_GUIDES = ROOT / "docs" / "models" / "check" / "check_guides.py"

LATEST_MODEL_URL = "https://ai.google.dev/gemini-api/docs/latest-model"
MODEL_PAGE_URL = "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash"
PROMPT_STRATEGIES_URL = "https://ai.google.dev/gemini-api/docs/prompting-strategies"
OFFICIAL_URLS = (LATEST_MODEL_URL, MODEL_PAGE_URL, PROMPT_STRATEGIES_URL)


def load_checker():
    """Load the merged guide checker so these tests exercise its real contract."""
    spec = importlib.util.spec_from_file_location("nova_check_guides", CHECK_GUIDES)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load guide checker at {CHECK_GUIDES}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load_checker()


def run_check(fixtures_dir: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-B",
        str(CHECK_GUIDES),
        "--check",
        "--model",
        MODEL,
        "--root",
        str(ROOT / "docs" / "models"),
    ]
    if fixtures_dir is not None:
        command.extend(("--fixtures-dir", str(fixtures_dir)))
    return subprocess.run(command, text=True, capture_output=True, check=False)


def markdown_sections(body: str) -> dict[str, str]:
    """Return second-level Markdown sections keyed by normalized heading."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in body.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            current = re.sub(r"[^a-z0-9]+", " ", match.group(1).lower()).strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {heading: "\n".join(lines).strip() for heading, lines in sections.items()}


def section_matching(sections: dict[str, str], *heading_terms: str) -> str | None:
    for heading, content in sections.items():
        if all(term in heading for term in heading_terms):
            return content
    return None


def fixture_html(article_text: str) -> str:
    """Wrap normalized live text without changing the checker's normalized digest."""
    return f"<html><body><main><p>{html.escape(article_text)}</p></main></body></html>"


class GeminiGuideAcceptanceTests(unittest.TestCase):
    def test_gemini_guide_provenance_and_strategy(self):
        """gemini-guide-provenance-and-strategy (unit)."""
        self.assertTrue(
            GUIDE.is_file(),
            f"Expected the Gemini prompting extract at {GUIDE.relative_to(ROOT)}",
        )

        fields, body = CHECKER.parse_frontmatter(GUIDE.read_text(encoding="utf-8"))
        self.assertEqual(fields.get("model"), MODEL)
        self.assertEqual(
            set(fields.get("official_source_urls", [])),
            set(OFFICIAL_URLS),
            "The extract must identify exactly the official Google sources.",
        )

        try:
            fetched_date = date.fromisoformat(fields.get("fetched_date", ""))
        except (TypeError, ValueError) as error:
            self.fail(f"fetched_date must be an ISO date: {error}")
        self.assertLessEqual(fetched_date, datetime.now(UTC).date())
        self.assertRegex(fields.get("extractor_version", ""), r"^\d+\.\d+\.\d+$")

        digests = fields.get("normalized_source_digests")
        self.assertIsInstance(digests, dict)
        self.assertEqual(
            set(digests),
            set(OFFICIAL_URLS),
            "Each and only each official source must have a normalized digest.",
        )
        for source_url, digest in digests.items():
            with self.subTest(source_url=source_url):
                self.assertRegex(digest, r"^[0-9a-f]{64}$")

        sections = markdown_sections(body)
        strategies = (
            (
                ("direct", "structured"),
                (PROMPT_STRATEGIES_URL,),
                (r"\bdirect\b", r"\bstructur(?:e|ed|ing)\b"),
            ),
            (
                ("critical", "instruction"),
                (PROMPT_STRATEGIES_URL,),
                (r"\bcritical|essential\b", r"\bbeginning\b|system instruction"),
            ),
            (
                ("explicit", "parameter"),
                (PROMPT_STRATEGIES_URL,),
                (r"\bexplicit(?:ly)?\b", r"\bparameters?\b"),
            ),
            (
                ("long", "context"),
                (PROMPT_STRATEGIES_URL,),
                (r"\bcontext\b", r"\bend\b|\bafter\b"),
            ),
            (
                ("verbosity",),
                (PROMPT_STRATEGIES_URL,),
                (r"\bverbosity\b", r"\bexplicit(?:ly)?\b|\brequest\b"),
            ),
            (
                ("thinking", "level"),
                (MODEL_PAGE_URL, LATEST_MODEL_URL),
                (r"\blow\b", r"\bmedium\b", r"\bhigh\b"),
            ),
            (
                ("grounding", "tool"),
                (PROMPT_STRATEGIES_URL,),
                (r"\bgrounding\b", r"\btools?\b"),
            ),
        )
        for heading_terms, expected_sources, claims in strategies:
            label = " ".join(heading_terms)
            with self.subTest(strategy=label):
                section = section_matching(sections, *heading_terms)
                self.assertIsNotNone(
                    section,
                    f"Expected an attributed '##' section for {label}.",
                )
                assert section is not None
                for src in expected_sources:
                    self.assertIn(
                        src,
                        section,
                        f"The {label} section must attribute its official Google source {src}.",
                    )
                self.assertRegex(
                    section,
                    r"(?m)^>\s+\S",
                    f"The {label} section must retain selected official content.",
                )
                for claim in claims:
                    self.assertRegex(section.lower(), claim)

        for sentence in re.split(r"(?<=[.!?])\s+|\n+", body):
            if "teamwork" not in sentence.lower():
                continue
            self.assertNotRegex(
                sentence.lower(),
                r"\bteamwork\b\s+(?:is|as)\s+(?:a\s+)?(?:gemini\s+)?(?:model\s+)?feature\b",
                "Teamwork is an Antigravity surface, not a Gemini model feature.",
            )

    def test_gemini_guide_is_live_fresh(self):
        """gemini-guide-is-live-fresh (integration)."""
        live = run_check()
        self.assertEqual(
            live.returncode,
            0,
            "The checker must refetch all official Google sources and report the "
            f"stored Gemini guide fresh.\nstdout: {live.stdout}\nstderr: {live.stderr}",
        )

        live_articles: dict[str, str] = {}
        clean_fixtures: dict[str, dict[str, object]] = {}
        for source_url in OFFICIAL_URLS:
            raw_html = CHECKER.fetch_upstream(source_url)
            article = CHECKER.extract(raw_html, vendor="google")
            wrapped = fixture_html(article)
            self.assertEqual(CHECKER.extract(wrapped, vendor="google"), article)
            live_articles[source_url] = article
            clean_fixtures[source_url] = {"status": 200, "content": wrapped}

        with tempfile.TemporaryDirectory() as tmp:
            fixtures_dir = Path(tmp)
            fixtures_file = fixtures_dir / "fixtures.json"
            fixtures_file.write_text(
                json.dumps(clean_fixtures),
                encoding="utf-8",
            )
            clean = run_check(fixtures_dir)
            self.assertEqual(
                clean.returncode,
                0,
                "Fixtures normalized from the live sources must be fresh.\n"
                f"stdout: {clean.stdout}\nstderr: {clean.stderr}",
            )

            for drifted_url in OFFICIAL_URLS:
                with self.subTest(drifted_url=drifted_url):
                    fixtures = {
                        url: dict(payload) for url, payload in clean_fixtures.items()
                    }
                    drift_marker = hashlib.sha256(drifted_url.encode()).hexdigest()[:12]
                    drifted_article = (
                        live_articles[drifted_url]
                        + f"\nInjected upstream drift {drift_marker}."
                    )
                    fixtures[drifted_url]["content"] = fixture_html(drifted_article)
                    fixtures_file.write_text(json.dumps(fixtures), encoding="utf-8")

                    result = run_check(fixtures_dir)
                    output = result.stdout + result.stderr
                    self.assertNotEqual(result.returncode, 0, output)
                    self.assertIn("drift", output.lower())
                    self.assertIn(MODEL, output)
                    self.assertIn(drifted_url, output)


if __name__ == "__main__":
    unittest.main()
