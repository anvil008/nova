"""Acceptance tests for Gemini 3.8 Flash Antigravity skill bodies (issue #161).

Verifies that:
1. all-agy-skills-are-owned (unit):
   Exactly 12 sources/outputs cite Gemini guidance, contain no fallback,
   and preserve the declared invocation, gates, and handoff contracts.
2. teamwork-is-optional-and-correctly-scoped (unit):
   Only long-horizon entry workflows mention Teamwork, state paid/interactive
   availability and retain headless fallback; issue-sized worker skills never invoke it.
3. agy-skill-gates-are-green (integration):
   Skill sync, agy evals and parity exit 0.
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

AGY_SKILLS_DIR = ROOT / "harnesses" / "agy" / "skills"
CONTRACTS_FILE = ROOT / "contracts" / "harness-contracts.json"

VALID_GEMINI_GUIDES = {
    "gemini-3.8-flash",
    "gemini-3.8",
    "docs/models/gemini-3.8-flash/prompting.md",
    "docs/models/gemini-3.8-flash",
    "Gemini 3.8 Flash",
    "gemini-3.8-flash",
    "gemini-3.8",
    "docs/models/gemini-3.8-flash/prompting.md",
    "docs/models/gemini-3.8-flash",
    "Gemini 3.8 Flash",
}

FALLBACK_MARKERS = (
    "<!-- generated harness-owned procedure:",
    "<!-- generated harness-owned procedure: Antigravity -->",
    "legacy-shared-body",
    "migration fallback",
)

OTHER_HARNESS_PATTERNS = (
    "harnesses/claude/skills",
    "harnesses/codex/skills",
    "harnesses/grok/skills",
    "harnesses/claude/agents",
    "harnesses/codex/agents",
    "harnesses/grok/agents",
)

LONG_HORIZON_ENTRY_WORKFLOWS = {"plan", "build"}

WORKER_SKILLS = {
    "debug",
    "refactor",
    "review",
    "profile",
    "deploy",
    "docs",
    "jj",
    "repo-setup",
    "use-other-harness",
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
    carrier = ROOT / "harnesses" / "agy" / "runtime" / "contracts.json"
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



class AgySkillsAcceptanceTests(unittest.TestCase):
    """Acceptance test suite for Gemini 3.8 Flash Antigravity skills (#161)."""

    def test_all_agy_skills_are_owned(self) -> None:
        """all-agy-skills-are-owned (unit):

        Exactly 12 sources/outputs cite Gemini guidance, contain no fallback,
        and preserve the declared invocation, gates, and handoff contracts.
        """
        registry = load_contracts()
        expected_skills = [entry["name"] for entry in registry["skills"]]
        self.assertEqual(
            len(expected_skills),
            12,
            f"Expected exactly 12 skills in registry, got {len(expected_skills)}",
        )

        found_dirs = {
            p.name
            for p in AGY_SKILLS_DIR.iterdir()
            if p.is_dir() and p.name != "tests" and not p.name.startswith(".")
        }

        # On Antigravity, 11 skills are globally invocable under harnesses/agy/skills;
        # jj is agent-owned by builder/specifier by contract (or 12 if jj is staged globally).
        global_skills = [
            s for s in expected_skills if s != "jj" or (AGY_SKILLS_DIR / "jj").is_dir()
        ]
        self.assertTrue(
            found_dirs.issuperset(set(global_skills)),
            f"Missing global skills in {AGY_SKILLS_DIR.relative_to(ROOT)}: {set(global_skills) - found_dirs}",
        )
        self.assertIn(
            len(found_dirs),
            (11, 12),
            f"Expected 11 or 12 skill directories in {AGY_SKILLS_DIR.relative_to(ROOT)}, got {len(found_dirs)}",
        )

        entries_by_name = {entry["name"]: entry for entry in registry["skills"]}

        # 1. Skill sources inspection
        for skill_name in sorted(found_dirs):
            skill_file = AGY_SKILLS_DIR / skill_name / "SKILL.md"
            self.assertTrue(
                skill_file.is_file(),
                f"Antigravity skill file missing: {skill_file.relative_to(ROOT)}",
            )
            content = skill_file.read_text(encoding="utf-8")

            # Cite Gemini guidance
            cites_guide = (
                any(guide in content for guide in VALID_GEMINI_GUIDES)
                or "docs/models/gemini-3.8-flash" in content
                or "gemini-3.8-flash" in content.lower()
            )
            self.assertTrue(
                cites_guide,
                f"Antigravity skill source {skill_name} does not cite Gemini guidance "
                f"({', '.join(sorted(VALID_GEMINI_GUIDES))})",
            )

            # Contain no fallback marker
            for marker in FALLBACK_MARKERS:
                self.assertNotIn(
                    marker,
                    content,
                    f"Antigravity skill source {skill_name} contains fallback marker {marker!r}; "
                    "Antigravity skills must be directly owned without fallback markers",
                )

            # Read no other harness body
            for pattern in OTHER_HARNESS_PATTERNS:
                self.assertNotIn(
                    pattern,
                    content,
                    f"Antigravity skill source {skill_name} must not read another harness body; found {pattern!r}",
                )

            front, body = parse_frontmatter(content)
            self.assertTrue(front.get("description", "").strip())

            # Contract fidelity
            entry = entries_by_name.get(skill_name)
            if entry:
                self.assertEqual(
                    front.get("name"),
                    entry["name"],
                    f"Skill {skill_name} frontmatter name must match registry name {entry['name']!r}",
                )
                self.assertIn(
                    entry["invocation"],
                    content,
                    f"Antigravity skill {skill_name} must declare its contract invocation {entry['invocation']!r}",
                )
                for gate in entry.get("orderedGates", []):
                    self.assertIn(
                        gate.lower(),
                        content.lower(),
                        f"Antigravity skill {skill_name} missing contract ordered gate: {gate!r}",
                    )
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
                        f"Antigravity skill {skill_name} must reference handoff schema {entry['handoffSchema']!r}",
                    )

            # ADR 0013: Eval mode retains identical meaning (does not bypass mechanical gates)
            self.assertNotRegex(
                content,
                r"(?i)eval.*(?:skip|bypass|ignore).*(?:gate|test|tdd|seal|baseline)",
                f"Skill {skill_name} must not bypass mechanical gates or tests in eval mode (ADR 0013)",
            )

        # use-other-harness specific semantics
        uoh_file = AGY_SKILLS_DIR / "use-other-harness" / "SKILL.md"
        self.assertTrue(uoh_file.is_file())
        uoh_text = uoh_file.read_text(encoding="utf-8")
        uoh_lower = uoh_text.lower()
        self.assertIn("explicit", uoh_lower)
        self.assertIn("never", uoh_lower)
        self.assertIn("router", uoh_lower)
        self.assertIn("leaf", uoh_lower)
        self.assertTrue(
            "agy" in uoh_lower or "antigravity" in uoh_lower,
            "use-other-harness must reference native Antigravity environment",
        )

        # 2. Staged outputs inspection
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
                [sys.executable, "scripts/build-agy-plugin.py"],
                cwd=tmp_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                stager_res.returncode,
                0,
                f"build-agy-plugin.py failed in temp staging:\n{stager_res.stdout}\n{stager_res.stderr}",
            )

            staged_skills_dir = tmp_root / "dist" / "agy" / "workcell" / "skills"
            self.assertTrue(
                staged_skills_dir.is_dir(),
                f"Staged skills directory missing: {staged_skills_dir}",
            )

            staged_dirs = {
                p.name
                for p in staged_skills_dir.iterdir()
                if p.is_dir() and not p.name.startswith(".")
            }
            self.assertIn(
                len(staged_dirs),
                (11, 12),
                f"Expected 11 or 12 staged skill directories, got {len(staged_dirs)}",
            )

            for staged_name in staged_dirs:
                staged_file = staged_skills_dir / staged_name / "SKILL.md"
                self.assertTrue(
                    staged_file.is_file(),
                    f"Staged Antigravity skill file missing: {staged_file.relative_to(tmp_root)}",
                )
                staged_content = staged_file.read_text(encoding="utf-8")

                cites_guide = (
                    any(guide in staged_content for guide in VALID_GEMINI_GUIDES)
                    or "docs/models/gemini-3.8-flash" in staged_content
                    or "gemini-3.8-flash" in staged_content.lower()
                )
                self.assertTrue(
                    cites_guide,
                    f"Staged Antigravity skill output {staged_name} does not cite Gemini guidance",
                )

                for marker in FALLBACK_MARKERS:
                    self.assertNotIn(
                        marker,
                        staged_content,
                        f"Staged Antigravity skill output {staged_name} contains fallback marker {marker!r}",
                    )

                for pattern in OTHER_HARNESS_PATTERNS:
                    self.assertNotIn(
                        pattern,
                        staged_content,
                        f"Staged Antigravity skill output {staged_name} must not read another harness body; found {pattern!r}",
                    )

                front, body = parse_frontmatter(staged_content)
                self.assertTrue(front.get("description", "").strip())

    def test_teamwork_is_optional_and_correctly_scoped(self) -> None:
        """teamwork-is-optional-and-correctly-scoped (unit):

        Only long-horizon entry workflows mention Teamwork, state paid/interactive
        availability and retain headless fallback; issue-sized worker skills never invoke it.
        """
        registry = load_contracts()

        found_dirs = {
            p.name
            for p in AGY_SKILLS_DIR.iterdir()
            if p.is_dir() and p.name != "tests" and not p.name.startswith(".")
        }

        # 1. Issue-sized worker skills never invoke or mention Teamwork
        for skill_name in found_dirs:
            skill_file = AGY_SKILLS_DIR / skill_name / "SKILL.md"
            if not skill_file.is_file():
                continue
            content = skill_file.read_text(encoding="utf-8")
            if skill_name in WORKER_SKILLS:
                self.assertNotIn(
                    "teamwork",
                    content.lower(),
                    f"Issue-sized worker skill '{skill_name}' must never invoke or mention Teamwork; "
                    "Teamwork is restricted to top-level long-horizon entry workflows.",
                )

            # A non-operative note does not claim availability or invoke a feature.
            operative = re.sub(r"(?i)Teamwork is optional and never required\.", "", content)
            # Actual Teamwork instructions must still name its availability and fallback.
            if "teamwork" in operative.lower():
                self.assertIn(
                    skill_name,
                    LONG_HORIZON_ENTRY_WORKFLOWS,
                    f"Skill '{skill_name}' mentions Teamwork, but only long-horizon entry workflows "
                    f"({sorted(LONG_HORIZON_ENTRY_WORKFLOWS)}) may mention it.",
                )

                # State paid/interactive availability
                has_availability = any(
                    term in content.lower()
                    for term in ("interactive", "paid", "subscription", "web interface")
                )
                self.assertTrue(
                    has_availability,
                    f"Skill '{skill_name}' mentions Teamwork but does not state paid/interactive "
                    "availability as required by Gemini/Antigravity guidance.",
                )

                # Retain headless fallback
                has_fallback = any(
                    term in content.lower()
                    for term in (
                        "headless",
                        "headless fallback",
                        "cli fallback",
                        "fallback",
                    )
                )
                self.assertTrue(
                    has_fallback,
                    f"Skill '{skill_name}' mentions Teamwork but does not retain an explicit "
                    "headless fallback.",
                )

                # Must not make Teamwork mandatory or required
                self.assertNotRegex(
                    content,
                    r"(?i)\b(?:require[s]?|mandatory|must\s+use)\s+teamwork\b",
                    f"Skill '{skill_name}' must not make Teamwork mandatory or required.",
                )

                # Must not misstate Teamwork as a Gemini model feature (per prompting.md)
                self.assertNotRegex(
                    content,
                    r"(?i)\b(?:gemini(?:'s)?\s+teamwork|teamwork\s+capability\s+of\s+gemini)\b",
                    f"Skill '{skill_name}' must not describe Teamwork as a Gemini model capability; "
                    "it is an Antigravity orchestration surface.",
                )

        # Teamwork is optional. A native invoke_subagent workflow need not
        # mention or require a separate orchestration surface.

    def test_agy_skill_gates_are_green(self) -> None:
        """agy-skill-gates-are-green (integration):

        Skill sync, agy evals and parity exit 0.
        """
        # 1. Harness ownership recognition in scripts/harness_generation.py
        self.assertIn(
            "agy",
            HARNESS_OWNED_SKILLS,
            "scripts/harness_generation.py: HARNESS_OWNED_SKILLS must register 'agy' as a harness-owned skill family",
        )

        registry = load_contracts()
        for entry in registry["skills"]:
            skill_path = AGY_SKILLS_DIR / entry["name"] / "SKILL.md"
            if skill_path.is_file():
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

        # 3. Antigravity evals: python3 evals/run_evals.py --harness agy
        res_evals = subprocess.run(
            [
                sys.executable,
                str(ROOT / "evals" / "run_evals.py"),
                "--harness",
                "agy",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            res_evals.returncode,
            0,
            f"evals/run_evals.py --harness agy failed:\n{res_evals.stdout}\n{res_evals.stderr}",
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
