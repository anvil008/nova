"""Acceptance tests for Grok Build-owned skill bodies (issue #164).

Verifies that:
1. all-grok-skills-are-owned-and-resolved (unit):
   Exactly 16 outputs have no fallback and cite the Grok 4.6 guide;
   unresolved inherit fails rather than guessing.
2. native-workflows-preserve-gates (unit):
   Any workflow/fork/background use declares I/O and returns through
   shared handoff/gates; none bypasses seal/reviewer/integrator.
3. grok-skill-gates-are-green (integration):
   Skill sync, Grok evals and parity exit 0.
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

GROK_SKILLS_DIR = ROOT / "harnesses" / "grok" / "skills"
CONTRACTS_FILE = ROOT / "contracts" / "harness-contracts.json"

VALID_GROK_GUIDES = {
    "grok-4.6",
    "docs/models/grok-4.6/prompting.md",
    "docs/models/grok-4.6",
}

FALLBACK_MARKERS = (
    "<!-- generated harness-owned procedure:",
    "<!-- generated harness-owned procedure: Grok Build -->",
    "legacy-shared-body",
    "migration fallback",
)

OTHER_HARNESS_PATTERNS = (
    "harnesses/claude/skills",
    "harnesses/codex/skills",
    "harnesses/agy/skills",
    "harnesses/claude/agents",
    "harnesses/codex/agents",
    "harnesses/agy/agents",
)

MULTI_AGENT_SKILLS = {
    "build",
    "code-analysis",
    "code-refactor",
    "code-review",
    "debug",
    "new-feature",
    "plan",
    "repo-setup",
    "research",
    "review-fix-loop",
}


def _cleanup_pycache() -> None:
    for cache_dir in (
        Path(__file__).parent / "__pycache__",
        ROOT / "harnesses" / "grok" / "skills" / "tests" / "__pycache__",
        ROOT / "scripts" / "__pycache__",
        ROOT / "evals" / "__pycache__",
    ):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir, ignore_errors=True)


atexit.register(_cleanup_pycache)


def load_contracts() -> dict:
    if CONTRACTS_FILE.is_file():
        return json.loads(CONTRACTS_FILE.read_text(encoding="utf-8"))
    carrier = ROOT / "harnesses" / "grok" / "runtime" / "contracts.json"
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


class GrokSkillsAcceptanceTests(unittest.TestCase):
    def test_all_grok_skills_are_owned_and_resolved(self) -> None:
        """all-grok-skills-are-owned-and-resolved (unit):

        Exactly 16 outputs have no fallback and cite the Grok 4.6 guide;
        unresolved inherit fails rather than guessing.
        """
        registry = load_contracts()
        expected_skills = [entry["name"] for entry in registry["skills"]]
        self.assertEqual(
            len(expected_skills),
            16,
            f"Expected exactly 16 skills in registry, got {len(expected_skills)}",
        )

        # 1. Exactly 16 Grok skill directories exist under harnesses/grok/skills
        found_dirs = {
            p.name
            for p in GROK_SKILLS_DIR.iterdir()
            if p.is_dir() and p.name != "tests" and not p.name.startswith(".")
        }
        self.assertEqual(
            found_dirs,
            set(expected_skills),
            f"Directories under {GROK_SKILLS_DIR.relative_to(ROOT)} must match exactly the 16 skills",
        )

        for skill_name in expected_skills:
            skill_file = GROK_SKILLS_DIR / skill_name / "SKILL.md"
            self.assertTrue(
                skill_file.is_file(),
                f"Grok skill file missing: {skill_file.relative_to(ROOT)}",
            )
            content = skill_file.read_text(encoding="utf-8")
            front, _ = parse_frontmatter(content)

            # Cite the Grok 4.6 guide
            cites_guide = (
                any(guide in content for guide in VALID_GROK_GUIDES)
                or "docs/models/grok-4.6" in content
            )
            self.assertTrue(
                cites_guide,
                f"Grok skill source {skill_name} does not cite the Grok 4.6 guide "
                f"({', '.join(sorted(VALID_GROK_GUIDES))} or docs/models/grok-4.6/prompting.md)",
            )

            # Contain no fallback marker
            for marker in FALLBACK_MARKERS:
                self.assertNotIn(
                    marker,
                    content,
                    f"Grok skill source {skill_name} contains fallback marker {marker!r}; "
                    "Grok skills must be directly owned without fallback markers",
                )

            # Read no other harness body
            for pattern in OTHER_HARNESS_PATTERNS:
                self.assertNotIn(
                    pattern,
                    content,
                    f"Grok skill source {skill_name} must not read another harness body; found {pattern!r}",
                )

            # Frontmatter must not use unresolved inherit for model
            self.assertNotEqual(
                front.get("model"),
                "inherit",
                f"Grok skill {skill_name} frontmatter has model: inherit; "
                "Grok roster must resolve grok-4.6 pin without unresolved inherit",
            )

        # 2. Exactly 16 staged outputs cite the Grok 4.6 guide, contain no fallback, and read no other harness
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
                [sys.executable, "scripts/build-grok-plugin.py"],
                cwd=tmp_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                stager_res.returncode,
                0,
                f"build-grok-plugin.py failed in temp staging:\n{stager_res.stdout}\n{stager_res.stderr}",
            )

            staged_skills_dir = (
                tmp_root / "dist" / "grok" / "plugins" / "workcell" / "skills"
            )
            self.assertTrue(
                staged_skills_dir.is_dir(),
                f"Staged skills directory missing: {staged_skills_dir}",
            )

            for skill_name in expected_skills:
                staged_file = staged_skills_dir / skill_name / "SKILL.md"
                self.assertTrue(
                    staged_file.is_file(),
                    f"Staged Grok skill file missing: {staged_file.relative_to(tmp_root)}",
                )
                staged_content = staged_file.read_text(encoding="utf-8")

                cites_guide = (
                    any(guide in staged_content for guide in VALID_GROK_GUIDES)
                    or "docs/models/grok-4.6" in staged_content
                )
                self.assertTrue(
                    cites_guide,
                    f"Staged Grok skill output {skill_name} does not cite the Grok 4.6 guide",
                )

                for marker in FALLBACK_MARKERS:
                    self.assertNotIn(
                        marker,
                        staged_content,
                        f"Staged Grok skill output {skill_name} contains fallback marker {marker!r}",
                    )

                for pattern in OTHER_HARNESS_PATTERNS:
                    self.assertNotIn(
                        pattern,
                        staged_content,
                        f"Staged Grok skill output {skill_name} must not read another harness body; found {pattern!r}",
                    )

        # 3. Unresolved inherit fails rather than guessing
        models = json.loads((ROOT / "agents/models.json").read_text(encoding="utf-8"))
        self.assertEqual(
            models["defaults"]["grok"]["model"],
            "grok-4.6",
            "Grok default model must be pinned to grok-4.6",
        )
        for agent_name, agent_cfg in models.get("agents", {}).items():
            if isinstance(agent_cfg, dict):
                grok_cfg = agent_cfg.get("grok", {})
                self.assertNotEqual(
                    grok_cfg.get("model"),
                    "inherit",
                    f"Grok agent route {agent_name} has unresolved inherit model",
                )

        # Verify that unresolved inherit for Grok in models.json fails generation rather than guessing
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir) / "workcell"
            shutil.copytree(
                ROOT,
                tmp_root,
                ignore=shutil.ignore_patterns(
                    ".git", ".jj", ".workcell", "dist", "__pycache__", "*.pyc"
                ),
            )
            bad_models_path = tmp_root / "agents" / "models.json"
            bad_models = json.loads(bad_models_path.read_text(encoding="utf-8"))
            bad_models["defaults"]["grok"]["model"] = "inherit"
            bad_models_path.write_text(
                json.dumps(bad_models, indent=2), encoding="utf-8"
            )
            res_bad_inherit = subprocess.run(
                [sys.executable, "scripts/sync-agents.py", "--check"],
                cwd=tmp_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(
                res_bad_inherit.returncode,
                0,
                "Unresolved inherit model for Grok must fail generation rather than guessing",
            )

    def test_native_workflows_preserve_gates(self) -> None:
        """native-workflows-preserve-gates (unit):

        Any workflow/fork/background use declares I/O and returns through
        shared handoff/gates; none bypasses seal/reviewer/integrator.
        """
        registry = load_contracts()
        entries_by_name = {entry["name"]: entry for entry in registry["skills"]}

        for skill_name, entry in entries_by_name.items():
            skill_file = GROK_SKILLS_DIR / skill_name / "SKILL.md"
            self.assertTrue(
                skill_file.is_file(),
                f"Grok skill file missing: {skill_file.relative_to(ROOT)}",
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
                f"Grok skill {skill_name} must declare its contract invocation {entry['invocation']!r}",
            )

            # Contract fidelity: ordered gates
            for gate in entry.get("orderedGates", []):
                self.assertIn(
                    gate.lower(),
                    content.lower(),
                    f"Grok skill {skill_name} missing contract ordered gate: {gate!r}",
                )

            # Contract fidelity: handoff schema
            if entry.get("handoffSchema") and skill_name in {
                "build",
                "code-analysis",
                "code-refactor",
                "debug",
                "new-feature",
                "plan",
                "use-other-harness",
            }:
                self.assertIn(
                    entry["handoffSchema"],
                    content,
                    f"Grok skill {skill_name} must reference handoff schema {entry['handoffSchema']!r}",
                )

            # 1. Gate preservation: no gate or test is bypassed
            self.assertNotRegex(
                content,
                r"(?i)\b(?:bypass|skip|ignore)\b[^\n]*(?:seal|reviewer|integrator|gate|test|tdd|baseline)",
                f"Grok skill {skill_name} must not bypass mechanical gates (seal, reviewer, integrator)",
            )

            # ADR 0013: Eval mode retains identical meaning (removes human pauses, not mechanical gates)
            self.assertNotRegex(
                content,
                r"(?i)eval.*(?:skip|bypass|ignore).*(?:gate|test|tdd|seal|baseline)",
                f"Skill {skill_name} must not bypass mechanical gates or tests in eval mode (ADR 0013)",
            )

            # 2. Multi-agent skills: workflows/forks/background subagents declare I/O and return through shared handoff/gates
            if skill_name in MULTI_AGENT_SKILLS:
                # Must declare I/O contracts (inputs and outputs per Grok 4.6 guidance)
                has_io = bool(
                    re.search(
                        r"(?i)\b(?:inputs?\b[^\n]*\boutputs?|input and output contracts?|i/o contracts?)\b",
                        body,
                    )
                )
                self.assertTrue(
                    has_io,
                    f"Grok skill {skill_name} orchestrates agents and must declare I/O contracts (inputs and outputs)",
                )

                # Must use Grok native subagent dispatch or workflow mechanisms
                has_native_mechanism = bool(
                    re.search(
                        r"\b(?:spawn_subagent|get_command_or_subagent_output|/workflow|create-workflow)\b",
                        body,
                    )
                )
                self.assertTrue(
                    has_native_mechanism,
                    f"Grok skill {skill_name} must declare Grok native subagents (spawn_subagent/background) or workflows (/workflow)",
                )

                # Must not declare Claude tools
                self.assertNotRegex(
                    body,
                    r"(?i)\bAgent\s+tool\b",
                    f"Grok skill {skill_name} must not declare Claude's 'Agent tool'",
                )
                self.assertNotRegex(
                    body,
                    r"(?i)\bBash\s+tool\b",
                    f"Grok skill {skill_name} must not declare Claude's 'Bash tool'",
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
                        f"Grok skill {skill_name} must not declare API-only feature {api_feature!r} as a tool",
                    )

            # 3. Build specifically enforces seal -> builder -> reviewer -> integrator
            if skill_name == "build":
                self.assertIn("specifier", body)
                self.assertIn("tdd-guard seal", body)
                self.assertIn("builder", body)
                self.assertIn("reviewer", body)
                self.assertIn("integrator", body)

        # use-other-harness specific semantics
        uoh_file = GROK_SKILLS_DIR / "use-other-harness" / "SKILL.md"
        self.assertTrue(uoh_file.is_file())
        uoh_text = uoh_file.read_text(encoding="utf-8")
        uoh_lower = uoh_text.lower()
        self.assertIn("explicit", uoh_lower)
        self.assertIn("never", uoh_lower)
        self.assertIn("router", uoh_lower)
        self.assertIn("leaf", uoh_lower)
        for req in ("harness", "model", "effort"):
            self.assertTrue(
                bool(re.search(rf"\b{req}\b", uoh_lower)),
                f"use-other-harness must require parameter {req!r}",
            )
        self.assertTrue(
            "grok -p" in uoh_text
            or "grok --no-auto-update -p" in uoh_text
            or "grok" in uoh_lower,
            "use-other-harness must declare native Grok invocation",
        )

    def test_grok_skill_gates_are_green(self) -> None:
        """grok-skill-gates-are-green (integration):

        Skill sync, Grok evals and parity exit 0.
        """
        # 1. Harness ownership recognition in scripts/harness_generation.py
        self.assertIn(
            "grok",
            HARNESS_OWNED_SKILLS,
            "scripts/harness_generation.py: HARNESS_OWNED_SKILLS must register 'grok' as a harness-owned skill family",
        )

        registry = load_contracts()
        for entry in registry["skills"]:
            skill_path = GROK_SKILLS_DIR / entry["name"] / "SKILL.md"
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

        # 3. Grok evals: python3 evals/run_evals.py --harness grok
        res_evals = subprocess.run(
            [
                sys.executable,
                str(ROOT / "evals" / "run_evals.py"),
                "--harness",
                "grok",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            res_evals.returncode,
            0,
            f"evals/run_evals.py --harness grok failed:\n{res_evals.stdout}\n{res_evals.stderr}",
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
