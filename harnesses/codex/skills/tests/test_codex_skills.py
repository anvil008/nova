"""Acceptance tests for Astra-native Codex skill bodies (issue #158).

Verifies that:
1. all-codex-skills-are-owned (unit):
   Exactly 12 sources/outputs cite the GPT guide, contain no fallback,
   and read no other harness.
2. codex-prompts-are-lean-and-complete (unit):
   Every body preserves invocation, gates, and handoff contracts, has no
   duplicated routing table, and uses only relevant declared tools.
3. codex-skill-gates-are-green (integration):
   Skill sync, Codex evals and parity exit 0.
"""

from __future__ import annotations

import atexit
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

# Prevent bytecode generation
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from harness_generation import (
    HARNESS_OWNED_SKILLS,
    is_harness_owned_skill_path,
)

CODEX_SKILLS_DIR = ROOT / "harnesses" / "codex" / "skills"
CONTRACTS_FILE = ROOT / "contracts" / "harness-contracts.json"

VALID_CODEX_GUIDES = {
    "gpt-6-astra",
    "GPT-6 Astra",
    "docs/models/gpt-6-astra/prompting.md",
    "docs/models/gpt-6-astra",
}

FALLBACK_MARKERS = (
    "<!-- generated harness-owned procedure:",
    "<!-- generated harness-owned procedure: Codex -->",
    "legacy-shared-body",
    "migration fallback",
)

OTHER_HARNESS_PATTERNS = (
    "harnesses/claude/skills",
    "harnesses/agy/skills",
    "harnesses/grok/skills",
    "harnesses/claude/agents",
    "harnesses/agy/agents",
    "harnesses/grok/agents",
)

MULTI_AGENT_SKILLS = {
    "build",
    "debug",
    "refactor",
    "review",
    "profile",
    "plan",
    "repo-setup",
}


def _cleanup_pycache() -> None:
    for cache_dir in (
        Path(__file__).parent / "__pycache__",
        ROOT / "scripts" / "__pycache__",
        ROOT / "evals" / "__pycache__",
    ):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir, ignore_errors=True)


atexit.register(_cleanup_pycache)


def load_contracts() -> dict:
    if CONTRACTS_FILE.is_file():
        return json.loads(CONTRACTS_FILE.read_text(encoding="utf-8"))
    carrier = ROOT / "harnesses" / "codex" / "runtime" / "contracts.json"
    data = json.loads(carrier.read_text(encoding="utf-8"))
    return data.get("contract", data)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    block = text[4:end]
    values = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("\t"):
            key, val = line.split(":", 1)
            values[key.strip()] = val.strip()
    body = text[end + 5 :].lstrip()
    return values, body



class CodexSkillsAcceptanceTests(unittest.TestCase):
    """Acceptance test suite for Astra-native Codex skills (#158)."""

    def test_all_codex_skills_are_owned(self) -> None:
        """all-codex-skills-are-owned (unit):

        Exactly 12 sources/outputs cite the GPT guide, contain no fallback,
        and read no other harness.
        """
        registry = load_contracts()
        expected_skills = [entry["name"] for entry in registry["skills"]]
        self.assertEqual(
            len(expected_skills),
            12,
            f"Expected exactly 12 skills in registry, got {len(expected_skills)}",
        )

        # 1. Exactly 12 Codex skill sources exist under harnesses/codex/skills
        found_dirs = {
            p.name
            for p in CODEX_SKILLS_DIR.iterdir()
            if p.is_dir() and p.name != "tests" and not p.name.startswith(".")
        }
        self.assertEqual(
            found_dirs,
            set(expected_skills),
            f"Directories under {CODEX_SKILLS_DIR.relative_to(ROOT)} must match exactly the 12 skills",
        )

        for skill_name in expected_skills:
            skill_file = CODEX_SKILLS_DIR / skill_name / "SKILL.md"
            self.assertTrue(
                skill_file.is_file(),
                f"Codex skill file missing: {skill_file.relative_to(ROOT)}",
            )
            content = skill_file.read_text(encoding="utf-8")

            # Cite the GPT guide
            cites_guide = (
                any(guide in content for guide in VALID_CODEX_GUIDES)
                or "docs/models/gpt-6-astra" in content
            )
            self.assertTrue(
                cites_guide,
                f"Codex skill source {skill_name} does not cite the GPT guide "
                f"({', '.join(sorted(VALID_CODEX_GUIDES))} or docs/models/gpt-6-astra/prompting.md)",
            )

            # Contain no fallback marker
            for marker in FALLBACK_MARKERS:
                self.assertNotIn(
                    marker,
                    content,
                    f"Codex skill source {skill_name} contains fallback marker {marker!r}; "
                    "Codex skills must be directly owned without fallback markers",
                )

            # Read no other harness body
            for pattern in OTHER_HARNESS_PATTERNS:
                self.assertNotIn(
                    pattern,
                    content,
                    f"Codex skill source {skill_name} must not read another harness body; found {pattern!r}",
                )

        # 2. Exactly 12 staged outputs cite the GPT guide, contain no fallback, and read no other harness
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir) / "workcell"
            shutil.copytree(
                ROOT,
                tmp_root,
                ignore=shutil.ignore_patterns(
                    ".git", ".jj", ".workcell", "dist", "__pycache__", "*.pyc"
                ),
            )
            stager_res = subprocess.run(
                [sys.executable, "scripts/build-codex-plugin.py"],
                cwd=tmp_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                stager_res.returncode,
                0,
                f"build-codex-plugin.py failed in temp staging:\n{stager_res.stdout}\n{stager_res.stderr}",
            )

            staged_skills_dir = (
                tmp_root / "dist" / "codex" / "plugins" / "workcell" / "skills"
            )
            self.assertTrue(
                staged_skills_dir.is_dir(),
                f"Staged skills directory missing: {staged_skills_dir}",
            )

            for skill_name in expected_skills:
                staged_file = staged_skills_dir / skill_name / "SKILL.md"
                self.assertTrue(
                    staged_file.is_file(),
                    f"Staged Codex skill file missing: {staged_file.relative_to(tmp_root)}",
                )
                staged_content = staged_file.read_text(encoding="utf-8")

                cites_guide = (
                    any(guide in staged_content for guide in VALID_CODEX_GUIDES)
                    or "docs/models/gpt-6-astra" in staged_content
                )
                self.assertTrue(
                    cites_guide,
                    f"Staged Codex skill output {skill_name} does not cite the GPT guide",
                )

                for marker in FALLBACK_MARKERS:
                    self.assertNotIn(
                        marker,
                        staged_content,
                        f"Staged Codex skill output {skill_name} contains fallback marker {marker!r}",
                    )

                for pattern in OTHER_HARNESS_PATTERNS:
                    self.assertNotIn(
                        pattern,
                        staged_content,
                        f"Staged Codex skill output {skill_name} must not read another harness body; found {pattern!r}",
                    )

    def test_codex_prompts_are_lean_and_complete(self) -> None:
        """codex-prompts-are-lean-and-complete (unit):

        Every body preserves invocation, gates, and handoff contracts, has no
        duplicated routing table, and uses only relevant declared tools.
        """
        registry = load_contracts()
        entries_by_name = {entry["name"]: entry for entry in registry["skills"]}

        for skill_name, entry in entries_by_name.items():
            skill_file = CODEX_SKILLS_DIR / skill_name / "SKILL.md"
            self.assertTrue(
                skill_file.is_file(),
                f"Codex skill file missing: {skill_file.relative_to(ROOT)}",
            )
            content = skill_file.read_text(encoding="utf-8")
            front, body = parse_frontmatter(content)

            # Contract fidelity: name
            self.assertEqual(
                front.get("name"),
                entry["name"],
                f"Skill {skill_name} frontmatter name must match registry name {entry['name']!r}",
            )

            # Contract fidelity: invocation (/workcell:<name>)
            self.assertIn(
                entry["invocation"],
                content,
                f"Codex skill {skill_name} must declare its contract invocation {entry['invocation']!r}",
            )

            # Contract fidelity: ordered gates
            for gate in entry.get("orderedGates", []):
                self.assertIn(
                    gate.lower(),
                    content.lower(),
                    f"Codex skill {skill_name} missing contract ordered gate: {gate!r}",
                )

            # Contract fidelity: handoff schema
            if entry.get("handoffSchema") and skill_name in {
                "build",
                "debug",
                "docs",
                "plan",
                "profile",
                "refactor",
                "review",
                "use-other-harness",
            }:
                self.assertIn(
                    entry["handoffSchema"],
                    content,
                    f"Codex skill {skill_name} must reference handoff schema {entry['handoffSchema']!r}",
                )

            # A skill can use prose or relevant references instead of a fixed
            # heading template. Contract identity and gates above remain required.
            self.assertTrue(front.get("description", "").strip())

            # 2. No duplicated contract/routing table
            # Must not duplicate agent routing tables (model/effort assignments)
            self.assertNotRegex(
                body,
                r"(?i)\|[^\n]*(?:model|reasoning_effort)[^\n]*\|",
                f"Codex skill {skill_name} must not duplicate agent routing table in body; "
                "reference generated routes instead",
            )
            self.assertNotRegex(
                body,
                r"(?i)\|[^\n]*gpt-5\.6-sol[^\n]*(?:high|medium|low)[^\n]*\|",
                f"Codex skill {skill_name} must not duplicate model routing table in body",
            )
            # Must not duplicate registry contract table
            self.assertNotRegex(
                body,
                r"(?i)\|[^\n]*(?:ordered\s*gates?|handoff\s*schema)[^\n]*\|",
                f"Codex skill {skill_name} must not duplicate contract registry table in body",
            )

            # 3. Only relevant declared tools
            # Must not declare Claude tools
            self.assertNotIn(
                "Claude Code",
                content,
                f"Codex skill {skill_name} must not reference Claude Code as tool environment",
            )
            self.assertNotRegex(
                body,
                r"(?i)\bAgent\s+tool\b",
                f"Codex skill {skill_name} must not declare Claude's 'Agent tool'; use Codex's 'spawn_agent' instead",
            )
            self.assertNotRegex(
                body,
                r"(?i)\bBash\s+tool\b",
                f"Codex skill {skill_name} must not declare Claude's 'Bash tool'; use Codex shell/exec tools instead",
            )
            # Must not declare unsupported API-only features as tools
            for api_feature in (
                "Programmatic Tool Calling",
                "allowed_callers",
                "program_output",
            ):
                self.assertNotIn(
                    api_feature,
                    body,
                    f"Codex skill {skill_name} must not declare API-only feature {api_feature!r} as a tool",
                )

            # Multi-agent orchestrators declare spawn_agent
            if skill_name in MULTI_AGENT_SKILLS:
                self.assertIn(
                    "spawn_agent",
                    body,
                    f"Codex skill {skill_name} is an agent orchestrator and must declare/use Codex's 'spawn_agent' tool",
                )

            # ADR 0013: Eval mode retains identical meaning (does not bypass mechanical gates)
            self.assertNotRegex(
                content,
                r"(?i)eval.*(?:skip|bypass|ignore).*(?:gate|test|tdd|seal|baseline)",
                f"Skill {skill_name} must not bypass mechanical gates or tests in eval mode (ADR 0013)",
            )

        # use-other-harness specific semantics
        uoh_file = CODEX_SKILLS_DIR / "use-other-harness" / "SKILL.md"
        self.assertTrue(uoh_file.is_file())
        uoh_text = uoh_file.read_text(encoding="utf-8")
        uoh_lower = uoh_text.lower()
        self.assertIn("explicit", uoh_lower)
        self.assertIn("never", uoh_lower)
        self.assertIn("router", uoh_lower)
        self.assertIn("leaf", uoh_lower)
        self.assertTrue(
            "codex exec" in uoh_text or "codex" in uoh_lower,
            "use-other-harness must declare native Codex invocation",
        )

    def test_codex_skill_gates_are_green(self) -> None:
        """codex-skill-gates-are-green (integration):

        Skill sync, Codex evals and parity exit 0.
        """
        # 1. Harness ownership recognition in scripts/harness_generation.py
        self.assertIn(
            "codex",
            HARNESS_OWNED_SKILLS,
            "scripts/harness_generation.py: HARNESS_OWNED_SKILLS must register 'codex' as a harness-owned skill family",
        )

        registry = load_contracts()
        for entry in registry["skills"]:
            skill_path = CODEX_SKILLS_DIR / entry["name"] / "SKILL.md"
            self.assertTrue(
                is_harness_owned_skill_path(skill_path, ROOT),
                f"scripts/harness_generation.py: is_harness_owned_skill_path must return True for {skill_path.relative_to(ROOT)}",
            )

        # 2. Skill sync: python3 scripts/sync-skills.py --check --diff
        res_sync = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "sync-skills.py"),
                "--check",
                "--diff",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            res_sync.returncode,
            0,
            f"scripts/sync-skills.py --check --diff failed:\n{res_sync.stdout}\n{res_sync.stderr}",
        )

        # 3. Codex evals: python3 evals/run_evals.py --harness codex
        res_evals = subprocess.run(
            [
                sys.executable,
                str(ROOT / "evals" / "run_evals.py"),
                "--harness",
                "codex",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            res_evals.returncode,
            0,
            f"evals/run_evals.py --harness codex failed:\n{res_evals.stdout}\n{res_evals.stderr}",
        )

        # 4. Parity: python3 scripts/check-contract-parity.py
        res_parity = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check-contract-parity.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            res_parity.returncode,
            0,
            f"scripts/check-contract-parity.py failed:\n{res_parity.stdout}\n{res_parity.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
