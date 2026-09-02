"""Acceptance tests for the three Claude model-guide extracts (#149)."""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MODELS_ROOT = ROOT / "docs" / "models"
CHECK_GUIDES = MODELS_ROOT / "check" / "check_guides.py"

MODEL_URLS = {
    "claude-fable-5-1": (
        "https://platform.claude.com/docs/en/build-with-claude/"
        "prompt-engineering/prompting-claude-fable-5-1"
    ),
    "claude-opus-5": (
        "https://platform.claude.com/docs/en/build-with-claude/"
        "prompt-engineering/prompting-claude-opus-5"
    ),
    "claude-sonnet-5": (
        "https://platform.claude.com/docs/en/build-with-claude/"
        "prompt-engineering/prompting-claude-sonnet-5"
    ),
}

FABLE_FINDINGS = (
    "de-scaffolding",
    "goals and boundaries",
    "evidence-backed progress",
    "autonomy",
    "asynchronous delegation",
    "wiki-only memory",
    "final re-grounding",
    "fresh-context verification",
    "refusal sensitivity",
)

# These labels are specific to the Fable findings supplied by the issue. The
# other guides can discuss their own delegation or verification behavior, but
# must not present these Fable-specific conclusions as Opus/Sonnet guidance.
FABLE_ONLY_LABELS = (
    "de-scaffolding",
    "evidence-backed progress",
    "wiki-only memory",
    "final re-grounding",
    "fresh-context verification",
    "refusal sensitivity",
)


def load_checker():
    spec = importlib.util.spec_from_file_location("workcell_check_guides", CHECK_GUIDES)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load checker from {CHECK_GUIDES}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load_checker()


def run_check(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(CHECK_GUIDES), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def normalized_markdown(text: str) -> str:
    """Make Markdown prose stable enough for explicit finding-label checks."""
    text = text.casefold().replace("/", " and ")
    text = re.sub(r"[`*_#]", "", text)
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    return " ".join(text.split())


def read_guide(model: str) -> tuple[dict, str]:
    path = MODELS_ROOT / model / "prompting.md"
    if not path.is_file():
        raise AssertionError(f"Required Claude guide is missing: {path}")
    return CHECKER.parse_frontmatter(path.read_text(encoding="utf-8"))


class ClaudeGuideAcceptanceTests(unittest.TestCase):
    def test_three_claude_guides_have_provenance(self):
        """Exactly the three requested guides carry exact official provenance."""
        expected_paths = {
            MODELS_ROOT / model / "prompting.md" for model in MODEL_URLS
        }
        actual_paths = set(MODELS_ROOT.glob("claude-*/prompting.md"))
        self.assertEqual(
            actual_paths,
            expected_paths,
            "Expected exactly one prompting.md for Fable 5.1, Opus 5, and "
            "Sonnet 5, with no missing or extra Claude model extract.",
        )

        for model, exact_url in MODEL_URLS.items():
            with self.subTest(model=model):
                fields, _ = read_guide(model)
                self.assertEqual(fields.get("model"), model)
                self.assertEqual(fields.get("official_source_urls"), [exact_url])

                fetched_date = fields.get("fetched_date", "")
                self.assertRegex(fetched_date, r"^\d{4}-\d{2}-\d{2}$")
                parsed_date = dt.date.fromisoformat(fetched_date)
                self.assertLessEqual(
                    parsed_date,
                    dt.datetime.now(dt.timezone.utc).date(),
                    "The provenance date cannot be in the future.",
                )
                self.assertEqual(fields.get("extractor_version"), "1.1.0")

                digests = fields.get("normalized_source_digests")
                self.assertIsInstance(digests, dict)
                self.assertEqual(set(digests), {exact_url})
                self.assertRegex(digests[exact_url], r"^[0-9a-f]{64}$")

    def test_fable_findings_do_not_leak(self):
        """Fable findings are attributed to Fable and model-native topics stay separate."""
        _, fable_body = read_guide("claude-fable-5-1")
        normalized_fable = normalized_markdown(fable_body)
        attribution = "workcell findings attributed to claude fable 5.1"
        self.assertIn(
            attribution,
            normalized_fable,
            "The Fable extract must explicitly attribute the supplied Workcell "
            "findings to Claude Fable 5.1.",
        )
        for finding in FABLE_FINDINGS:
            with self.subTest(fable_finding=finding):
                self.assertIn(finding, normalized_fable)

        model_native_topics = {
            "claude-opus-5": (
                "effort",
                "tool",
                "narration",
                "delegation",
                "verification",
            ),
            "claude-sonnet-5": (
                "effort",
                "tool",
                "progress updates",
                "verification",
                "literal",
            ),
        }
        for model, topics in model_native_topics.items():
            _, body = read_guide(model)
            normalized_body = normalized_markdown(body)
            for topic in topics:
                with self.subTest(model=model, native_topic=topic):
                    self.assertIn(topic, normalized_body)
            for fable_label in FABLE_ONLY_LABELS:
                with self.subTest(model=model, leaked_fable_label=fable_label):
                    self.assertNotIn(
                        fable_label,
                        normalized_body,
                        f"{model} must not label the Fable-only finding "
                        f"'{fable_label}' as its guidance.",
                    )

    def test_claude_guides_are_live_fresh(self):
        """All official pages are live-fresh; fixture drift names only its model."""
        for model in MODEL_URLS:
            with self.subTest(live_model=model):
                result = run_check("--check", "--model", model)
                self.assertEqual(
                    result.returncode,
                    0,
                    f"Live freshness failed for {model}:\n"
                    f"stdout: {result.stdout}\nstderr: {result.stderr}",
                )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            models_dir = tmp_path / "models"
            fixtures_dir = tmp_path / "fixtures"
            fixtures_dir.mkdir(parents=True)
            fixture_map: dict[str, dict] = {}

            for model, exact_url in MODEL_URLS.items():
                source = MODELS_ROOT / model / "prompting.md"
                target = models_dir / model / "prompting.md"
                fields, body = read_guide(model)
                target.parent.mkdir(parents=True)
                shutil.copyfile(source, target)

                passages = CHECKER.extract_passages(body)
                article_html = "<html><body><article>" + "".join(
                    f"<p>{html.escape(passage)}</p>" for passage in passages
                ) + f"<p>Stable fixture for {html.escape(model)}</p></article></body></html>"
                normalized_article = CHECKER.extract(article_html, vendor="anthropic")
                fields["normalized_source_digests"] = {
                    exact_url: hashlib.sha256(
                        normalized_article.encode("utf-8")
                    ).hexdigest()
                }
                target.write_text(
                    CHECKER.render_frontmatter(fields) + body,
                    encoding="utf-8",
                )
                fixture_map[exact_url] = {"status": 200, "content": article_html}

            fixtures_file = fixtures_dir / "fixtures.json"
            fixtures_file.write_text(json.dumps(fixture_map), encoding="utf-8")
            baseline = run_check(
                "--check",
                "--root",
                str(models_dir),
                "--fixtures-dir",
                str(fixtures_dir),
            )
            self.assertEqual(
                baseline.returncode,
                0,
                f"Synthetic unchanged fixtures must pass:\n"
                f"stdout: {baseline.stdout}\nstderr: {baseline.stderr}",
            )

            drifted_model = "claude-opus-5"
            drifted_url = MODEL_URLS[drifted_model]
            fixture_map[drifted_url]["content"] = fixture_map[drifted_url][
                "content"
            ].replace("</article>", "<p>Changed upstream text.</p></article>")
            fixtures_file.write_text(json.dumps(fixture_map), encoding="utf-8")

            drift = run_check(
                "--check",
                "--root",
                str(models_dir),
                "--fixtures-dir",
                str(fixtures_dir),
            )
            output = drift.stdout + drift.stderr
            self.assertNotEqual(drift.returncode, 0)
            self.assertIn("drift", output.casefold())
            self.assertIn(drifted_model, output)
            for unchanged_model in set(MODEL_URLS) - {drifted_model}:
                self.assertNotIn(
                    unchanged_model,
                    output,
                    "A one-page fixture change must name only the drifted model.",
                )


if __name__ == "__main__":
    unittest.main()
