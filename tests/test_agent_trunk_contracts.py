"""Acceptance tests for local trunk handoff contract and agent bodies (#214)."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HANDOFF_MD = ROOT / "agents" / "handoff.md"
BUILDER_MD = ROOT / "agents" / "bodies" / "builder.md"
INTEGRATOR_MD = ROOT / "agents" / "bodies" / "integrator.md"


def get_section(text: str, title: str) -> str:
    """Extract the content of a markdown section under a ## heading."""
    pattern = rf"##\s+{re.escape(title)}\s*\n(.*?)(?=\n##\s+|$)"
    match = re.search(pattern, text, re.DOTALL)
    assert match is not None, f"Section '## {title}' not found"
    return match.group(1).strip()


def extract_field_entry(section: str, field_name: str) -> str | None:
    """Extract a list item definition for - `field_name`... from a markdown section."""
    pattern = (
        rf"(?:^|\n)\s*-\s*`{re.escape(field_name)}`.*?(?=\n\s*-\s*`|\n##|\n\n[^\n-]|\Z)"
    )
    match = re.search(pattern, section, re.DOTALL)
    return match.group(0).strip() if match else None


def extract_json_block(section: str) -> dict:
    """Extract and parse the first ```json code block in a markdown section."""
    match = re.search(r"```json\s*\n(.*?)\n```", section, re.DOTALL)
    assert match is not None, "No ```json code block found in section"
    return json.loads(match.group(1))


class TestAgentTrunkContracts(unittest.TestCase):
    """Acceptance tests for issue #214: local trunk handoff contract and agent bodies."""

    def test_handoff_contract_defines_change_id(self) -> None:
        """verify agents/handoff.md specifies optional changeId in anvil.agent-handoff/v1 schema and notes pr is null in local trunk handoff."""
        self.assertTrue(HANDOFF_MD.is_file(), f"{HANDOFF_MD} does not exist")
        content = HANDOFF_MD.read_text(encoding="utf-8")

        record_section = get_section(content, "Handoff record")
        change_id_entry = extract_field_entry(record_section, "changeId")
        self.assertIsNotNone(
            change_id_entry,
            "agents/handoff.md 'Handoff record' section must define 'changeId' field (e.g. - `changeId`: ...)",
        )
        self.assertTrue(
            "optional" in change_id_entry.lower() or "null" in change_id_entry.lower(),
            "agents/handoff.md 'changeId' field must specify that it is optional or null when unset",
        )
        self.assertTrue(
            "change" in change_id_entry.lower() or "jj" in change_id_entry.lower(),
            "agents/handoff.md 'changeId' field must describe Jujutsu change ID",
        )

        pr_entry = extract_field_entry(record_section, "pr")
        self.assertIsNotNone(
            pr_entry,
            "agents/handoff.md 'Handoff record' section must define 'pr' field",
        )
        self.assertTrue(
            ("local trunk" in pr_entry.lower() and "null" in pr_entry.lower())
            or ("local trunk" in record_section.lower() and "null" in record_section.lower()),
            "agents/handoff.md must note that pr is null in local trunk handoff",
        )

    def test_builder_body_scopes_test_and_eliminates_intermediate_pr(self) -> None:
        """verify agents/bodies/builder.md instructs builders to verify ONLY sealed acceptance tests, forbids broad test suites, and eliminates jj git push and gh pr create."""
        self.assertTrue(BUILDER_MD.is_file(), f"{BUILDER_MD} does not exist")
        builder_text = BUILDER_MD.read_text(encoding="utf-8")

        # 1. Eliminates jj git push and gh pr create
        self.assertFalse(
            "jj git push" in builder_text,
            "agents/bodies/builder.md must eliminate 'jj git push'",
        )
        self.assertFalse(
            "gh pr create" in builder_text,
            "agents/bodies/builder.md must eliminate 'gh pr create'",
        )

        # 2. Instructs builders to verify ONLY sealed acceptance tests
        has_only_sealed = (
            re.search(
                r"(?:verify|run)\s+(?:only|ONLY)\s+(?:the\s+)?sealed\s+(?:acceptance\s+)?tests?",
                builder_text,
                re.IGNORECASE,
            )
            is not None
            or "only the sealed acceptance test" in builder_text.lower()
            or "only sealed acceptance test" in builder_text.lower()
            or "only the sealed test" in builder_text.lower()
            or "only sealed test" in builder_text.lower()
        )
        self.assertTrue(
            has_only_sealed,
            "agents/bodies/builder.md must instruct builders to verify ONLY sealed acceptance tests",
        )

        # 3. Forbids broad test suites or whole-project test runners
        forbids_broad = (
            re.search(
                r"(?:forbid|never|prohibit|do not run).*?(?:broad|whole-project|whole project).*?(?:suite|runner|tests?)",
                builder_text,
                re.IGNORECASE,
            )
            is not None
            or re.search(
                r"(?:broad|whole-project|whole project).*?(?:suite|runner|tests?).*?(?:forbid|never|prohibit)",
                builder_text,
                re.IGNORECASE,
            )
            is not None
            or ("broad" in builder_text.lower() and ("forbid" in builder_text.lower() or "never" in builder_text.lower()))
        )
        self.assertTrue(
            forbids_broad,
            "agents/bodies/builder.md must forbid broad test suites or whole-project test runners",
        )

    def test_integrator_body_documents_jj_rebase(self) -> None:
        """verify agents/bodies/integrator.md documents combining wave changes via jj rebase onto integration trunk and running full project test suite once."""
        self.assertTrue(INTEGRATOR_MD.is_file(), f"{INTEGRATOR_MD} does not exist")
        integrator_text = INTEGRATOR_MD.read_text(encoding="utf-8")

        # 1. Documents jj rebase
        self.assertTrue(
            "jj rebase" in integrator_text,
            "agents/bodies/integrator.md must document 'jj rebase'",
        )

        # 2. Documents integration trunk
        has_integration_trunk = (
            "integration trunk" in integrator_text.lower()
            or "<integration-trunk>" in integrator_text.lower()
            or "integration-trunk" in integrator_text.lower()
        )
        self.assertTrue(
            has_integration_trunk,
            "agents/bodies/integrator.md must document rebasing onto integration trunk",
        )

        # 3. Documents combining wave changes
        has_wave_combine = (
            "wave" in integrator_text.lower()
            and ("combine" in integrator_text.lower() or "combining" in integrator_text.lower() or "rebase" in integrator_text.lower())
        )
        self.assertTrue(
            has_wave_combine,
            "agents/bodies/integrator.md must document combining wave changes",
        )

        # 4. Documents running full project test suite once
        has_full_suite_once = (
            re.search(
                r"(?:full project test|full project verification|whole project|scripts/run-tests\.sh).*?once|once.*?(?:full project|scripts/run-tests\.sh)",
                integrator_text,
                re.IGNORECASE,
            )
            is not None
            or ("full project" in integrator_text.lower() and "once" in integrator_text.lower())
            or ("run-tests.sh" in integrator_text.lower() and "once" in integrator_text.lower())
        )
        self.assertTrue(
            has_full_suite_once,
            "agents/bodies/integrator.md must document running full project test suite once",
        )


if __name__ == "__main__":
    unittest.main()
