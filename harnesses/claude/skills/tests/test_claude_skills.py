"""Acceptance tests for Claude-owned skills (#154)."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import unittest

# Prevent bytecode generation
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[4]
CLAUDE_SKILLS_DIR = ROOT / "harnesses" / "claude" / "skills"
CONTRACTS_FILE = ROOT / "contracts" / "harness-contracts.json"

VALID_CLAUDE_GUIDES = {
    "claude-fable-5-1",
    "claude-opus-5",
    "claude-sonnet-5",
}

FALLBACK_MARKERS = (
    "<!-- generated harness-owned procedure:",
    "<!-- generated harness-owned procedure: Claude Code -->",
    "legacy-shared-body",
    "migration fallback",
)

OTHER_HARNESS_PATTERNS = (
    "harnesses/codex/skills",
    "harnesses/agy/skills",
    "harnesses/grok/skills",
    "harnesses/codex/agents",
    "harnesses/agy/agents",
    "harnesses/grok/agents",
)


def load_contracts() -> dict:
    if CONTRACTS_FILE.is_file():
        return json.loads(CONTRACTS_FILE.read_text(encoding="utf-8"))
    runtime_carrier = ROOT / "harnesses" / "claude" / "runtime" / "contracts.json"
    data = json.loads(runtime_carrier.read_text(encoding="utf-8"))
    return data.get("contract", data)


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    block = text[4:end]
    values = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("\t"):
            key, val = line.split(":", 1)
            values[key.strip()] = val.strip()
    return values


class ClaudeSkillsAcceptanceTests(unittest.TestCase):
    """Acceptance test suite for Claude-owned Workcell skills (#154)."""

    def test_all_claude_skills_are_owned(self) -> None:
        """all-claude-skills-are-owned (unit):

        Exactly 12 Claude skill sources/outputs exist, cite applicable guide(s),
        contain no fallback marker, and read no other harness body.
        """
        registry = load_contracts()
        expected_skills = [entry["name"] for entry in registry["skills"]]
        self.assertEqual(
            len(expected_skills),
            12,
            f"Expected exactly 12 skills in registry, got {len(expected_skills)}",
        )

        # 1. Exactly 12 Claude skill directories exist with SKILL.md
        found_dirs = {
            p.name
            for p in CLAUDE_SKILLS_DIR.iterdir()
            if p.is_dir() and p.name != "tests" and not p.name.startswith(".")
        }
        self.assertEqual(
            found_dirs,
            set(expected_skills),
            f"Directories under {CLAUDE_SKILLS_DIR.relative_to(ROOT)} must match exactly the 12 skills",
        )

        for skill_name in expected_skills:
            skill_file = CLAUDE_SKILLS_DIR / skill_name / "SKILL.md"
            self.assertTrue(
                skill_file.is_file(),
                f"Claude skill file missing: {skill_file.relative_to(ROOT)}",
            )
            content = skill_file.read_text(encoding="utf-8")

            # 2. Cite applicable guide(s)
            cites_guide = (
                any(guide in content for guide in VALID_CLAUDE_GUIDES)
                or "docs/models/claude-" in content
                or "docs/models/claude" in content
            )
            self.assertTrue(
                cites_guide,
                f"Claude skill {skill_name} does not cite any applicable Claude model guide "
                f"({', '.join(sorted(VALID_CLAUDE_GUIDES))} or docs/models/claude-*/prompting.md)",
            )

            # 3. Contain no fallback marker
            for marker in FALLBACK_MARKERS:
                self.assertNotIn(
                    marker,
                    content,
                    f"Claude skill {skill_name} contains fallback marker {marker!r}; "
                    "Claude skills must be directly owned without fallback markers",
                )

            # 4. Read no other harness body
            for pattern in OTHER_HARNESS_PATTERNS:
                self.assertNotIn(
                    pattern,
                    content,
                    f"Claude skill {skill_name} must not read another harness body; found {pattern!r}",
                )

    def test_claude_skill_compatibility_is_identical(self) -> None:
        """claude-skill-compatibility-is-identical (integration):

        Generated contracts equal the registry for names/invocations/gates/handoff/oracle;
        use-other-harness and eval mode retain identical meaning.
        """
        registry = load_contracts()
        entries_by_name = {entry["name"]: entry for entry in registry["skills"]}

        for skill_name, entry in entries_by_name.items():
            skill_file = CLAUDE_SKILLS_DIR / skill_name / "SKILL.md"
            self.assertTrue(
                skill_file.is_file(),
                f"Claude skill file missing: {skill_file.relative_to(ROOT)}",
            )
            content = skill_file.read_text(encoding="utf-8")
            front = parse_frontmatter(content)

            # Skill name matches contract
            self.assertEqual(
                front.get("name"),
                entry["name"],
                f"Skill {skill_name} frontmatter name must match registry name {entry['name']!r}",
            )

            # Invocation matches registry (/workcell:<name>)
            self.assertIn(
                entry["invocation"],
                content,
                f"Claude skill {skill_name} must declare its contract invocation {entry['invocation']!r}",
            )

            # Ordered gates from registry are all represented
            for gate in entry.get("orderedGates", []):
                self.assertIn(
                    gate.lower(),
                    content.lower(),
                    f"Claude skill {skill_name} missing contract ordered gate: {gate!r}",
                )

            # Handoff schema contract
            if entry.get("handoffSchema"):
                expected_schema = entry["handoffSchema"]
                if skill_name in {
                    "build",
                    "debug",
                    "docs",
                    "refactor",
                    "review",
                    "profile",
                    "plan",
                    "use-other-harness",
                }:
                    self.assertIn(
                        expected_schema,
                        content,
                        f"Claude skill {skill_name} must reference handoff schema {expected_schema!r}",
                    )

            # Eval mode retains identical meaning (ADR 0013: removes human pauses, not mechanical gates)
            self.assertNotRegex(
                content,
                r"(?i)eval.*(?:skip|bypass|ignore).*(?:gate|test|tdd|seal|baseline)",
                f"Skill {skill_name} must not bypass mechanical gates or tests in eval mode (ADR 0013)",
            )

        # use-other-harness semantics
        uoh_file = CLAUDE_SKILLS_DIR / "use-other-harness" / "SKILL.md"
        self.assertTrue(uoh_file.is_file())
        uoh_text = uoh_file.read_text(encoding="utf-8")
        uoh_lower = uoh_text.lower()

        # 1. Explicit user request only
        self.assertTrue(
            bool(re.search(r"explicit(?:ly)?[^.\n]{0,80}user", uoh_lower)),
            "use-other-harness must require explicit user request",
        )
        # 2. Never an automatic router
        self.assertTrue(
            bool(re.search(r"(?:not|never)[^.\n]{0,80}(?:router|routing)", uoh_lower)),
            "use-other-harness must explicitly state it is not an automatic router",
        )
        # 3. Requires harness, model, and effort
        for req in ("harness", "model", "effort"):
            self.assertTrue(
                bool(re.search(rf"\b{req}\b", uoh_lower)),
                f"use-other-harness must require parameter {req!r}",
            )
        # 4. Leaf capability
        self.assertIn(
            "leaf",
            uoh_lower,
            "use-other-harness must enforce leaf-only execution",
        )
        # 5. Native Claude tokens
        for token in ("claude", "-p", "--dangerously-skip-permissions"):
            self.assertIn(
                token,
                uoh_text,
                f"use-other-harness must retain native Claude headless token {token!r}",
            )

    def test_native_fields_are_capability_safe(self) -> None:
        """native-fields-are-capability-safe (unit):

        Fork/Workflow/agent fields appear only with supporting capability metadata;
        unsupported surfaces are omitted with deterministic notes.
        """
        registry = load_contracts()
        entries_by_name = {entry["name"]: entry for entry in registry["skills"]}

        for skill_name, entry in entries_by_name.items():
            skill_file = CLAUDE_SKILLS_DIR / skill_name / "SKILL.md"
            if not skill_file.is_file():
                continue
            content = skill_file.read_text(encoding="utf-8")
            front = parse_frontmatter(content)

            # 1. Fork/Workflow/agent fields appear only with supporting capability metadata
            for key in front.keys():
                if key in {"fork", "context_fork", "workflow", "workflows", "subagents"}:
                    matching_surfaces = [
                        s
                        for s in entry.get("optionalSurfaces", [])
                        if s.get("name") == key and s.get("harness") == "claude"
                    ]
                    self.assertTrue(
                        any(s.get("supported") is True for s in matching_surfaces),
                        f"Claude skill {skill_name} uses frontmatter field {key!r} "
                        "without supporting capability metadata",
                    )

            # 2. Unsupported surfaces declared in registry are omitted with deterministic notes
            for surface in entry.get("optionalSurfaces", []):
                if surface.get("harness") != "claude":
                    continue
                if surface.get("supported") is False:
                    note = surface.get("limitationNote", "")
                    self.assertIn(
                        note,
                        content,
                        f"Claude skill {skill_name} is missing deterministic limitation note: {note!r}",
                    )

            # No generic limitations paragraph is required when the registry
            # declares no unsupported surface. Actual declared omissions above
            # still require their deterministic notes.


if __name__ == "__main__":
    unittest.main()
