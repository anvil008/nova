"""Acceptance tests for agent handoff contract model and effort documentation (#203)."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HANDOFF_MD = ROOT / "agents" / "handoff.md"


def get_section(text: str, title: str) -> str:
    """Extract the content of a markdown section under a ## heading."""
    pattern = rf"##\s+{re.escape(title)}\s*\n(.*?)(?=\n##\s+|$)"
    match = re.search(pattern, text, re.DOTALL)
    assert match is not None, f"Section '## {title}' not found in {HANDOFF_MD}"
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


class TestAgentHandoffContract(unittest.TestCase):
    """Verify agents/handoff.md specifies model string and reasoning effort."""

    def setUp(self) -> None:
        self.assertTrue(HANDOFF_MD.is_file(), f"{HANDOFF_MD} does not exist")
        self.content = HANDOFF_MD.read_text(encoding="utf-8")

    def test_handoff_brief_documents_model_and_effort(self) -> None:
        """agents/handoff.md dispatch brief section explicitly specifies optional model and effort fields."""
        brief_section = get_section(self.content, "Dispatch brief")

        model_entry = extract_field_entry(brief_section, "model")
        self.assertIsNotNone(
            model_entry,
            "Dispatch brief section must document 'model' field (e.g. - `model`: ...)",
        )
        self.assertIn(
            "optional",
            model_entry.lower(),
            "Dispatch brief section must explicitly specify 'model' as optional",
        )
        self.assertTrue(
            "model" in model_entry.lower(),
            "Dispatch brief 'model' field must describe the model string",
        )

        effort_entry = extract_field_entry(brief_section, "effort")
        self.assertIsNotNone(
            effort_entry,
            "Dispatch brief section must document 'effort' field (e.g. - `effort`: ...)",
        )
        self.assertIn(
            "optional",
            effort_entry.lower(),
            "Dispatch brief section must explicitly specify 'effort' as optional",
        )
        self.assertTrue(
            "effort" in effort_entry.lower() or "reasoning" in effort_entry.lower(),
            "Dispatch brief 'effort' field must describe reasoning effort level",
        )

    def test_handoff_record_documents_model_and_effort(self) -> None:
        """agents/handoff.md handoff record section explicitly defines model and effort within the anvil.agent-handoff/v1 specification."""
        record_section = get_section(self.content, "Handoff record")

        model_entry = extract_field_entry(record_section, "model")
        self.assertIsNotNone(
            model_entry,
            "Handoff record section must define 'model' field (e.g. - `model`: ...)",
        )
        self.assertTrue(
            "optional" in model_entry.lower() or "null" in model_entry.lower(),
            "Handoff record 'model' field must specify optional or null when unset",
        )
        self.assertTrue(
            "model" in model_entry.lower(),
            "Handoff record 'model' field must specify the model string",
        )

        effort_entry = extract_field_entry(record_section, "effort")
        self.assertIsNotNone(
            effort_entry,
            "Handoff record section must define 'effort' field (e.g. - `effort`: ...)",
        )
        self.assertTrue(
            "optional" in effort_entry.lower() or "null" in effort_entry.lower(),
            "Handoff record 'effort' field must specify optional or null when unset",
        )
        self.assertTrue(
            "effort" in effort_entry.lower() or "reasoning" in effort_entry.lower(),
            "Handoff record 'effort' field must specify the reasoning effort level",
        )

    def test_handoff_examples_include_model_and_effort(self) -> None:
        """Both dispatch brief and handoff record JSON examples in agents/handoff.md contain valid model and effort fields."""
        brief_example_section = get_section(self.content, "Dispatch brief example")
        brief_json = extract_json_block(brief_example_section)

        self.assertIn(
            "model",
            brief_json,
            "Dispatch brief JSON example must contain 'model' field",
        )
        self.assertIsInstance(
            brief_json["model"],
            str,
            "Dispatch brief JSON example 'model' must be a string",
        )
        self.assertTrue(
            len(brief_json["model"].strip()) > 0,
            "Dispatch brief JSON example 'model' must not be empty",
        )

        self.assertIn(
            "effort",
            brief_json,
            "Dispatch brief JSON example must contain 'effort' field",
        )
        self.assertIsInstance(
            brief_json["effort"],
            str,
            "Dispatch brief JSON example 'effort' must be a string",
        )
        self.assertIn(
            brief_json["effort"].strip().lower(),
            {"low", "medium", "high"},
            "Dispatch brief JSON example 'effort' must be a valid reasoning effort level (low, medium, high)",
        )

        record_example_section = get_section(self.content, "Handoff record example")
        record_json = extract_json_block(record_example_section)

        self.assertIn(
            "model",
            record_json,
            "Handoff record JSON example must contain 'model' field",
        )
        self.assertIsInstance(
            record_json["model"],
            str,
            "Handoff record JSON example 'model' must be a string",
        )
        self.assertTrue(
            len(record_json["model"].strip()) > 0,
            "Handoff record JSON example 'model' must not be empty",
        )

        self.assertIn(
            "effort",
            record_json,
            "Handoff record JSON example must contain 'effort' field",
        )
        self.assertIsInstance(
            record_json["effort"],
            str,
            "Handoff record JSON example 'effort' must be a string",
        )
        self.assertIn(
            record_json["effort"].strip().lower(),
            {"low", "medium", "high"},
            "Handoff record JSON example 'effort' must be a valid reasoning effort level (low, medium, high)",
        )


if __name__ == "__main__":
    unittest.main()
