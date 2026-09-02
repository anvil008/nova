"""Acceptance tests for the Grok Build and Grok 4.6 guide (#151)."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODELS_ROOT = ROOT / "docs" / "models"
GUIDE = MODELS_ROOT / "grok-4.6" / "prompting.md"
CHECK_GUIDES = MODELS_ROOT / "check" / "check_guides.py"

REQUIRED_BUILD_URLS = {
    "https://docs.x.ai/build/overview",
    "https://docs.x.ai/build/features/skills-plugins-marketplaces",
    "https://docs.x.ai/build/modes-and-commands",
    "https://docs.x.ai/build/cli/headless-scripting",
    "https://docs.x.ai/build/settings",
}
GROK_46_URLS = {
    "https://docs.x.ai/developers/grok-4-6",
    "https://docs.x.ai/developers/models/grok-4.6",
}

SPEC = importlib.util.spec_from_file_location("workcell_check_guides", CHECK_GUIDES)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def run_check(*args: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(CHECK_GUIDES), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def h2_sections(markdown: str) -> list[tuple[str, str]]:
    """Return normalized H2 headings and their bodies."""
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", markdown))
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        heading = re.sub(r"[^a-z0-9]+", " ", match.group(1).lower()).strip()
        sections.append((heading, markdown[match.end() : end]))
    return sections


class GrokGuideAcceptanceTests(unittest.TestCase):
    maxDiff = None

    def read_guide(self) -> tuple[str, dict, str]:
        self.assertTrue(
            GUIDE.is_file(),
            f"Missing Grok 4.6 extract: {GUIDE.relative_to(ROOT)}",
        )
        content = GUIDE.read_text(encoding="utf-8")
        fields, body = CHECKER.parse_frontmatter(content)
        return content, fields, body

    def section(self, body: str, *heading_words: str) -> str:
        for heading, section_body in h2_sections(body):
            if all(word in heading.split() for word in heading_words):
                return section_body
        self.fail(
            "Missing H2 section whose heading contains "
            f"{', '.join(heading_words)}; found: "
            + ", ".join(heading for heading, _ in h2_sections(body))
        )

    def assert_tokens(self, section: str, *tokens: str) -> None:
        for token in tokens:
            with self.subTest(token=token):
                self.assertIn(token.lower(), section.lower())

    def test_grok_guide_provenance_and_native_surfaces(self):
        """grok-guide-provenance-and-native-surfaces (unit)."""
        content, fields, body = self.read_guide()

        self.assertEqual(fields.get("model"), "grok-4.6")
        self.assertIn("Grok 4.6", body)
        self.assertIn("Grok Build", body)

        urls = fields.get("official_source_urls")
        self.assertIsInstance(urls, list)
        url_set = set(urls)
        self.assertTrue(
            REQUIRED_BUILD_URLS <= url_set,
            f"Missing official Grok Build sources: {sorted(REQUIRED_BUILD_URLS - url_set)}",
        )
        self.assertTrue(
            GROK_46_URLS & url_set,
            "The extract must include an official Grok 4.6 model page.",
        )
        self.assertTrue(
            all(url.startswith("https://docs.x.ai/") for url in urls),
            f"Every configured source must be official docs.x.ai: {urls}",
        )

        digests = fields.get("normalized_source_digests")
        self.assertIsInstance(digests, dict)
        self.assertEqual(set(digests), url_set)
        for url, digest in digests.items():
            with self.subTest(source=url):
                self.assertRegex(digest, r"\A[0-9a-f]{64}\Z")

        fetched_date = fields.get("fetched_date", "")
        self.assertEqual(dt.date.fromisoformat(fetched_date).isoformat(), fetched_date)
        self.assertRegex(fields.get("extractor_version", ""), r"\A\d+\.\d+\.\d+\Z")

        self.assertIn("xai-org/grok-build", content)
        self.assertIn("docs/user-guide", content)

        roster = self.section(body, "roster", "pin")
        self.assert_tokens(roster, "agents/models.json", "grok models", "grok-4.6")

        instructions = self.section(body, "instruction", "rules")
        self.assert_tokens(instructions, "AGENTS.md", ".grok/rules/")
        self.assertTrue(
            "--rules" in instructions or "--system-prompt-override" in instructions,
            "Instruction rules must record a native one-run instruction flag.",
        )

        agents = self.section(body, "agents", "personas")
        self.assert_tokens(
            agents,
            ".grok/agents/",
            ".grok/personas/",
            "general-purpose",
            "explore",
            "plan",
        )

        io_contracts = self.section(body, "input", "output", "contracts")
        self.assert_tokens(
            io_contracts,
            "inputs",
            "outputs",
            "name",
            "io_type",
            "required",
            "description",
        )

        background = self.section(body, "background", "subagents")
        self.assert_tokens(
            background,
            "spawn_subagent",
            "background",
            "get_command_or_subagent_output",
        )

        forks = self.section(body, "forks")
        self.assert_tokens(forks, "/fork", "--fork-session")

        workflows = self.section(body, "workflows")
        self.assert_tokens(
            workflows,
            "/create-workflow",
            "/workflow",
            ".grok/workflows/",
        )

        capability_modes = self.section(body, "capability", "modes")
        self.assert_tokens(
            capability_modes,
            "read-only",
            "read-write",
            "execute",
            "all",
        )

        headless = self.section(body, "headless", "flags")
        self.assert_tokens(
            headless,
            "-p",
            "--model",
            "--effort",
            "--output-format",
            "--always-approve",
            "--max-turns",
            "--no-plan",
            "--no-subagents",
            "--no-auto-update",
        )

        unsupported = self.section(body, "unsupported", "fields")
        self.assert_tokens(
            unsupported,
            "allowed-tools",
            "model",
            "effort",
            "license",
            "compatibility",
        )
        unsupported_lower = unsupported.lower()
        self.assertIn("not appl", unsupported_lower)
        self.assertRegex(unsupported_lower, r"does not (grant|restrict)")

    def test_grok_guide_is_live_fresh(self):
        """grok-guide-is-live-fresh (integration)."""
        original, fields, _ = self.read_guide()

        live = run_check(
            "--check",
            "--model",
            "grok-4.6",
            "--root",
            str(MODELS_ROOT),
        )
        self.assertEqual(
            live.returncode,
            0,
            "The live official xAI sources must be fresh.\n"
            f"stdout:\n{live.stdout}\nstderr:\n{live.stderr}",
        )
        self.assertEqual(GUIDE.read_text(encoding="utf-8"), original)

        drift_url = "https://docs.x.ai/build/overview"
        stored_digest = fields["normalized_source_digests"][drift_url]
        fixture_fields = {
            "model": "grok-4.6",
            "official_source_urls": [drift_url],
            "fetched_date": fields["fetched_date"],
            "extractor_version": fields["extractor_version"],
            "normalized_source_digests": {drift_url: stored_digest},
        }

        with tempfile.TemporaryDirectory() as temporary:
            temp_root = Path(temporary)
            temp_models = temp_root / "models"
            temp_guide = temp_models / "grok-4.6" / "prompting.md"
            fixtures_dir = temp_root / "fixtures"
            temp_guide.parent.mkdir(parents=True)
            fixtures_dir.mkdir()
            temp_guide.write_text(
                CHECKER.render_frontmatter(fixture_fields) + "# Changed-page fixture\n",
                encoding="utf-8",
            )
            (fixtures_dir / "fixtures.json").write_text(
                json.dumps(
                    {
                        drift_url: {
                            "status": 200,
                            "content": (
                                "<html><main>Changed xAI Grok Build overview "
                                "fixture.</main></html>"
                            ),
                        }
                    }
                ),
                encoding="utf-8",
            )
            fixture_before = temp_guide.read_bytes()

            drift = run_check(
                "--check",
                "--model",
                "grok-4.6",
                "--root",
                str(temp_models),
                "--fixtures-dir",
                str(fixtures_dir),
            )
            output = drift.stdout + drift.stderr
            self.assertNotEqual(drift.returncode, 0, output)
            self.assertIn("drift", output.lower())
            self.assertIn("grok-4.6", output)
            self.assertIn(drift_url, output)
            self.assertEqual(temp_guide.read_bytes(), fixture_before)


if __name__ == "__main__":
    unittest.main()
