"""Acceptance tests for model guide extract and freshness gate (#147)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CHECK_GUIDES = ROOT / "docs" / "models" / "check" / "check_guides.py"

REQUIRED_FIELDS = (
    "model",
    "official_source_urls",
    "fetched_date",
    "extractor_version",
    "normalized_source_digests",
)


def run_check(*args: str, **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(CHECK_GUIDES), *args],
        text=True,
        capture_output=True,
        check=False,
        **kwargs,
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_frontmatter(fields: dict) -> str:
    lines = ["---"]
    for key, val in fields.items():
        if isinstance(val, list):
            lines.append(f"{key}:")
            for item in val:
                lines.append(f"  - {item}")
        elif isinstance(val, dict):
            lines.append(f"{key}:")
            for k, v in val.items():
                lines.append(f"  {k}: {v}")
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")
    return "\n".join(lines) + "\n"


class CheckGuidesAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.models_dir = self.root / "models"
        self.fixtures_dir = self.root / "fixtures"
        self.models_dir.mkdir(parents=True)
        self.fixtures_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _write_guide(
        self,
        model: str,
        fields: dict | None = None,
        body: str = "# Guidance\n\n> Focus on direct and concise instructions.\n",
    ) -> Path:
        guide_dir = self.models_dir / model
        guide_dir.mkdir(parents=True, exist_ok=True)
        guide_file = guide_dir / "prompting.md"

        if fields is None:
            url = f"https://example.com/docs/{model}/prompting"
            upstream_text = "Focus on direct and concise instructions."
            digest = sha256_text(upstream_text)
            fields = {
                "model": model,
                "official_source_urls": [url],
                "fetched_date": "2026-09-01",
                "extractor_version": "1.0.0",
                "normalized_source_digests": {url: digest},
            }

        content = render_frontmatter(fields) + body
        guide_file.write_text(content, encoding="utf-8")
        return guide_file

    def _write_fixture(
        self,
        url: str,
        content: str | None = None,
        status: int = 200,
        error: str | None = None,
    ) -> None:
        fixtures_file = self.fixtures_dir / "fixtures.json"
        if fixtures_file.exists():
            data = json.loads(fixtures_file.read_text(encoding="utf-8"))
        else:
            data = {}

        entry: dict = {"status": status}
        if content is not None:
            entry["content"] = content
        if error is not None:
            entry["error"] = error

        data[url] = entry
        fixtures_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def test_required_header_is_enforced(self):
        """required-header-is-enforced (unit)

        Fixture extracts missing each required provenance field make check_guides.py
        --check exit non-zero naming file and field; a complete fixture passes.
        """
        model = "test-model-header"
        url = f"https://example.com/docs/{model}/prompting"
        article_text = "Focus on direct and concise instructions."
        self._write_fixture(
            url,
            content=f"<html><body><article>{article_text}</article></body></html>",
            status=200,
        )

        # 1. Complete fixture passes
        guide_path = self._write_guide(model)
        result = run_check(
            "--check",
            "--root",
            str(self.models_dir),
            "--fixtures-dir",
            str(self.fixtures_dir),
        )
        self.assertEqual(
            result.returncode,
            0,
            f"Expected complete fixture to pass, got exit {result.returncode}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )

        # 2. Missing each required field exits non-zero naming the file and field
        for field in REQUIRED_FIELDS:
            with self.subTest(missing_field=field):
                base_fields = {
                    "model": model,
                    "official_source_urls": [url],
                    "fetched_date": "2026-09-01",
                    "extractor_version": "1.0.0",
                    "normalized_source_digests": {url: sha256_text(article_text)},
                }
                del base_fields[field]

                self._write_guide(model, fields=base_fields)
                res = run_check(
                    "--check",
                    "--root",
                    str(self.models_dir),
                    "--fixtures-dir",
                    str(self.fixtures_dir),
                )
                output = res.stdout + res.stderr
                self.assertNotEqual(
                    res.returncode,
                    0,
                    f"Expected non-zero exit when field '{field}' is missing, got 0.\nOutput:\n{output}",
                )
                self.assertTrue(
                    "prompting.md" in output or str(guide_path) in output,
                    f"Expected output to name file 'prompting.md', got:\n{output}",
                )
                self.assertIn(
                    field,
                    output,
                    f"Expected output to name missing field '{field}', got:\n{output}",
                )

    def test_upstream_drift_is_loud_and_read_only(self):
        """upstream-drift-is-loud-and-read-only (integration)

        Unchanged normalized fixture content exits 0; changing a selected passage
        or article digest exits non-zero naming drift/model/URL and leaves the
        stored extract byte-identical.
        """
        model = "test-model-drift"
        url = f"https://example.com/docs/{model}/prompting"
        original_article = "Section A: Write clear code. Section B: Provide evidence."
        original_digest = sha256_text(original_article)

        # Write matching fixture and guide
        self._write_fixture(
            url,
            content=f"<html><body><article>{original_article}</article></body></html>",
            status=200,
        )
        fields = {
            "model": model,
            "official_source_urls": [url],
            "fetched_date": "2026-09-01",
            "extractor_version": "1.0.0",
            "normalized_source_digests": {url: original_digest},
        }
        body = "# Selected Content\n\n> Section A: Write clear code.\n"
        guide_file = self._write_guide(model, fields=fields, body=body)

        # 1. Unchanged normalized fixture content exits 0
        clean_run = run_check(
            "--check",
            "--root",
            str(self.models_dir),
            "--fixtures-dir",
            str(self.fixtures_dir),
        )
        self.assertEqual(
            clean_run.returncode,
            0,
            f"Expected exit 0 for unchanged fixture, got {clean_run.returncode}:\n"
            f"stdout: {clean_run.stdout}\nstderr: {clean_run.stderr}",
        )

        # 2. Upstream article content changes (digest drift)
        modified_article = (
            "Section A: Write clear code. Section B: Upstream modified content."
        )
        self._write_fixture(
            url,
            content=f"<html><body><article>{modified_article}</article></body></html>",
            status=200,
        )
        initial_bytes = guide_file.read_bytes()

        drift_run = run_check(
            "--check",
            "--root",
            str(self.models_dir),
            "--fixtures-dir",
            str(self.fixtures_dir),
        )
        drift_output = drift_run.stdout + drift_run.stderr

        self.assertNotEqual(
            drift_run.returncode,
            0,
            f"Expected non-zero exit when upstream content drifts, got 0.\nOutput:\n{drift_output}",
        )
        self.assertIn(
            "drift",
            drift_output.lower(),
            f"Expected output to mention 'drift', got:\n{drift_output}",
        )
        self.assertIn(
            model,
            drift_output,
            f"Expected output to name model '{model}', got:\n{drift_output}",
        )
        self.assertIn(
            url,
            drift_output,
            f"Expected output to name URL '{url}', got:\n{drift_output}",
        )
        self.assertEqual(
            guide_file.read_bytes(),
            initial_bytes,
            "Extract file must remain byte-identical under --check mode.",
        )

        # 3. Selected passage changes / missing from upstream
        # Restore upstream fixture to original, but alter selected passage in stored guide
        self._write_fixture(
            url,
            content=f"<html><body><article>{original_article}</article></body></html>",
            status=200,
        )
        drifted_body = "# Selected Content\n\n> Non-existent passage that does not appear in upstream.\n"
        guide_file = self._write_guide(model, fields=fields, body=drifted_body)
        initial_bytes_passage = guide_file.read_bytes()

        passage_drift_run = run_check(
            "--check",
            "--root",
            str(self.models_dir),
            "--fixtures-dir",
            str(self.fixtures_dir),
        )
        passage_output = passage_drift_run.stdout + passage_drift_run.stderr

        self.assertNotEqual(
            passage_drift_run.returncode,
            0,
            f"Expected non-zero exit when selected passage drifts, got 0.\nOutput:\n{passage_output}",
        )
        self.assertIn(
            "drift",
            passage_output.lower(),
            f"Expected output to mention 'drift', got:\n{passage_output}",
        )
        self.assertIn(
            model,
            passage_output,
            f"Expected output to name model '{model}', got:\n{passage_output}",
        )
        self.assertIn(
            url,
            passage_output,
            f"Expected output to name URL '{url}', got:\n{passage_output}",
        )
        self.assertEqual(
            guide_file.read_bytes(),
            initial_bytes_passage,
            "Extract file must remain byte-identical under --check mode.",
        )

    def test_fetch_failure_is_not_freshness(self):
        """fetch-failure-is-not-freshness (unit)

        Timeout, non-2xx, or missing article selector exits non-zero as
        fetch/extraction failure and never reports fresh.
        """
        model = "test-model-fetch-failure"
        url = f"https://example.com/docs/{model}/prompting"
        self._write_guide(model)

        # 1. Timeout failure
        with self.subTest(failure_type="timeout"):
            self._write_fixture(url, status=0, error="Timeout fetching resource")
            res = run_check(
                "--check",
                "--root",
                str(self.models_dir),
                "--fixtures-dir",
                str(self.fixtures_dir),
            )
            output = res.stdout + res.stderr
            self.assertNotEqual(
                res.returncode,
                0,
                f"Expected non-zero exit on timeout, got 0.\nOutput:\n{output}",
            )
            self.assertTrue(
                any(w in output.lower() for w in ("timeout", "fetch", "error", "fail")),
                f"Expected output to describe fetch/timeout failure, got:\n{output}",
            )
            self.assertNotIn(
                "is fresh",
                output.lower(),
                f"Failure must not report freshness, got:\n{output}",
            )
            self.assertNotIn(
                "guides fresh",
                output.lower(),
                f"Failure must not report freshness, got:\n{output}",
            )

        # 2. Non-2xx HTTP status (e.g. 404, 500)
        for status_code in (404, 500):
            with self.subTest(failure_type=f"http_{status_code}"):
                self._write_fixture(
                    url, content="Error response page", status=status_code
                )
                res = run_check(
                    "--check",
                    "--root",
                    str(self.models_dir),
                    "--fixtures-dir",
                    str(self.fixtures_dir),
                )
                output = res.stdout + res.stderr
                self.assertNotEqual(
                    res.returncode,
                    0,
                    f"Expected non-zero exit on HTTP {status_code}, got 0.\nOutput:\n{output}",
                )
                self.assertTrue(
                    any(
                        w in output.lower()
                        for w in ("fetch", "status", "http", str(status_code), "error")
                    ),
                    f"Expected output to describe HTTP failure, got:\n{output}",
                )
                self.assertNotIn(
                    "is fresh",
                    output.lower(),
                    f"HTTP failure must not report freshness, got:\n{output}",
                )
                self.assertNotIn(
                    "guides fresh",
                    output.lower(),
                    f"HTTP failure must not report freshness, got:\n{output}",
                )

        # 3. Missing article selector (extraction failure)
        with self.subTest(failure_type="missing_article_selector"):
            # Return HTML missing expected article/main selector
            self._write_fixture(
                url,
                content="<html><body><nav>Only navigation, no article</nav></body></html>",
                status=200,
            )
            res = run_check(
                "--check",
                "--root",
                str(self.models_dir),
                "--fixtures-dir",
                str(self.fixtures_dir),
            )
            output = res.stdout + res.stderr
            self.assertNotEqual(
                res.returncode,
                0,
                f"Expected non-zero exit on missing article selector, got 0.\nOutput:\n{output}",
            )
            self.assertTrue(
                any(
                    w in output.lower()
                    for w in ("extract", "selector", "article", "error", "fail")
                ),
                f"Expected output to describe extraction failure, got:\n{output}",
            )
            self.assertNotIn(
                "is fresh",
                output.lower(),
                f"Extraction failure must not report freshness, got:\n{output}",
            )
            self.assertNotIn(
                "guides fresh",
                output.lower(),
                f"Extraction failure must not report freshness, got:\n{output}",
            )


class ConsentBannerNormalizationTests(unittest.TestCase):
    """A geo-conditioned cookie banner must not reach the normalized digest."""

    ARTICLE = (
        "<main><h1>Prompting</h1><p>Start at high effort.</p></main>"
    )
    BANNER = (
        '<div data-testid="consent-banner"><h3>Cookie settings</h3>'
        "<p>We use cookies to deliver and improve our services.</p>"
        "<div><button>Reject All Cookies</button></div></div>"
    )

    def _extract(self, html: str) -> str:
        sys.path.insert(0, str(CHECK_GUIDES.parent))
        try:
            import check_guides
        finally:
            sys.path.pop(0)
        return check_guides.extract(html, vendor="anthropic")

    def test_banner_presence_does_not_change_extract(self):
        """The same page served with and without the banner must normalize alike.

        platform.claude.com renders the banner server-side for some IP
        countries and omits it for others, so without this the digest depends
        on where the checker runs.
        """
        with_banner = f'<body><div class="contents">{self.BANNER}{self.ARTICLE}</div></body>'
        without_banner = f'<body><div class="contents">{self.ARTICLE}</div></body>'
        self.assertEqual(
            self._extract(with_banner),
            self._extract(without_banner),
            "Consent banner leaked into the normalized extract",
        )

    def test_banner_text_is_absent_from_extract(self):
        html = f'<body><div class="contents">{self.BANNER}{self.ARTICLE}</div></body>'
        text = self._extract(html)
        self.assertNotIn("Cookie settings", text)
        self.assertNotIn("Reject All Cookies", text)
        self.assertIn("Start at high effort.", text)


if __name__ == "__main__":
    unittest.main()
