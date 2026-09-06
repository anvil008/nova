"""Acceptance tests for Issue #157: use-other-harness semantic parity across harness families.

Covers acceptance test:
- use-other-harness-means-the-same (e2e)
  Oracle: Explicit harness/model/effort requests route natively and implicit cross-harness
  suggestions are refused across all three, with identical handoff fields and no silent fallback.
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "workcell_run_evals", ROOT / "evals" / "run_evals.py"
)
assert SPEC and SPEC.loader
run_evals = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_evals
SPEC.loader.exec_module(run_evals)

HARNESSES = ("claude", "codex", "agy")


def run_main(*args: str) -> tuple[int, str]:
    output = io.StringIO()
    error_output = io.StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    try:
        sys.stdout = output
        sys.stderr = error_output
        status = run_evals.main(list(args), output)
    except SystemExit as exc:
        status = exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
    return status, output.getvalue() + error_output.getvalue()


class UseOtherHarnessParityTests(unittest.TestCase):
    """Test use-other-harness semantics, routing, refusal, and handoff parity across harnesses."""

    def test_explicit_requests_route_natively_across_all_three(self) -> None:
        """Explicit harness/model/effort requests route natively across all three harnesses."""
        for harness in HARNESSES:
            skill_doc = (
                ROOT
                / "harnesses"
                / harness
                / "skills"
                / "use-other-harness"
                / "SKILL.md"
            )
            self.assertTrue(
                skill_doc.is_file(),
                f"missing use-other-harness skill for harness: {harness}",
            )
            content = skill_doc.read_text(encoding="utf-8")

            # Must document native invocation patterns for all targets
            self.assertIn(
                "claude -p", content, f"missing claude native syntax in {harness}"
            )
            self.assertIn(
                "codex exec", content, f"missing codex native syntax in {harness}"
            )
            self.assertIn("agy -p", content, f"missing agy native syntax in {harness}")

            # Behavioral dry-run for use-other-harness must emit native commands
            status, output = run_main(
                "--root",
                str(ROOT),
                "--behavioral",
                "use-other-harness",
                "--harness",
                harness,
                "--dry-run",
            )
            self.assertEqual(
                status, 0, f"dry-run for use-other-harness failed:\n{output}"
            )
            if harness == "claude":
                self.assertIn("claude -p", output)
            elif harness == "codex":
                self.assertIn("codex exec", output)
                self.assertIn("--cd", output)
                self.assertIn("-o", output)
            elif harness == "agy":
                self.assertIn("agy -p", output)

    def test_implicit_cross_harness_suggestions_refused_across_all_three(self) -> None:
        """Implicit cross-harness suggestions are refused across all three harnesses."""
        # 1. Structural/textual refusal rules across all 3 generated skill files
        for harness in HARNESSES:
            skill_doc = (
                ROOT
                / "harnesses"
                / harness
                / "skills"
                / "use-other-harness"
                / "SKILL.md"
            )
            content = skill_doc.read_text(encoding="utf-8")
            self.assertIn(
                "ONLY when the user explicitly asks",
                content,
                f"{harness} must require explicit user request",
            )
            self.assertIn(
                "Never invoke this for automatic cross-harness routing",
                content,
                f"{harness} must refuse automatic cross-harness routing",
            )
            self.assertIn(
                "If any of the three is missing, ask for it",
                content,
                f"{harness} must ask for missing harness/model/effort",
            )

        # 2. Case definition verification: dialogue eval tests refusal when parameters missing
        case_path = ROOT / "evals" / "cases" / "skills" / "use-other-harness.json"
        self.assertTrue(case_path.is_file(), f"missing case file: {case_path}")
        case_data = json.loads(case_path.read_text(encoding="utf-8"))
        evals = case_data.get("evals", [])
        dialogue_evals = [e for e in evals if e.get("kind") == "dialogue"]
        self.assertTrue(
            dialogue_evals,
            "use-other-harness must have a dialogue eval testing refusal",
        )
        dialogue = dialogue_evals[0]
        self.assertIn("Claude Code", dialogue.get("prompt", ""))
        expectations = dialogue.get("expectations", [])
        self.assertTrue(
            any("exact model and reasoning effort" in exp for exp in expectations),
            f"dialogue eval must expect clarification for model/effort:\n{expectations}",
        )
        self.assertTrue(
            any("No alternate harness command is run" in exp for exp in expectations),
            f"dialogue eval must expect no command run until explicit:\n{expectations}",
        )

        # 3. Routing eval: run_evals --harness <h> must not route implicit prompts to use-other-harness
        for harness in HARNESSES:
            status, output = run_main(
                "--root", str(ROOT), "--harness", harness, "--min-rank1", "77"
            )
            self.assertEqual(
                status, 0, f"routing evals failed for harness {harness}:\n{output}"
            )
            self.assertIn(
                harness,
                output.lower(),
                f"evals output must name harness {harness}:\n{output}",
            )

    def test_identical_handoff_fields_across_all_three(self) -> None:
        """Handoff schema is identically anvil.agent-handoff/v1 across all three harnesses."""
        contracts_path = ROOT / "contracts" / "harness-contracts.json"
        self.assertTrue(
            contracts_path.is_file(), f"missing contracts registry: {contracts_path}"
        )
        contracts = json.loads(contracts_path.read_text(encoding="utf-8"))
        skill_contract = next(
            s for s in contracts["skills"] if s["name"] == "use-other-harness"
        )
        self.assertEqual(skill_contract["handoffSchema"], "anvil.agent-handoff/v1")

        for harness in HARNESSES:
            carrier = ROOT / "harnesses" / harness / "runtime" / "contracts.json"
            self.assertTrue(
                carrier.is_file(), f"missing contracts carrier for {harness}"
            )
            data = json.loads(carrier.read_text(encoding="utf-8"))
            skill_entry = next(
                s
                for s in data["contract"]["skills"]
                if s["name"] == "use-other-harness"
            )
            self.assertEqual(
                skill_entry["handoffSchema"],
                "anvil.agent-handoff/v1",
                f"handoffSchema drift in {harness} contracts carrier",
            )

        # Contract parity check must enforce handoff schema for use-other-harness
        status, output = run_main("--root", str(ROOT), "--contract-parity")
        self.assertEqual(
            status, 0, f"contract parity on real tree must pass:\n{output}"
        )

    def test_no_silent_fallback_across_all_three(self) -> None:
        """No silent fallback is permitted across all three harnesses."""
        for harness in HARNESSES:
            skill_doc = (
                ROOT
                / "harnesses"
                / harness
                / "skills"
                / "use-other-harness"
                / "SKILL.md"
            )
            content = skill_doc.read_text(encoding="utf-8")
            normalized = re.sub(r"\s+", " ", content)
            self.assertIn(
                "Do not guess a model or effort, and do not pick a harness on the user's behalf.",
                normalized,
                f"{harness} must explicitly prohibit silent fallback",
            )

        # In temporary copy, introducing silent fallback drift must fail contract parity
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir) / "workcell"
            shutil.copytree(
                ROOT,
                temp_root,
                ignore=shutil.ignore_patterns(
                    ".git", ".jj", "dist", "__pycache__", "*.pyc"
                ),
            )
            target = (
                temp_root
                / "harnesses"
                / "codex"
                / "skills"
                / "use-other-harness"
                / "SKILL.md"
            )
            self.assertTrue(target.is_file())
            # Replace no-fallback rule with silent fallback instruction
            original_text = target.read_text(encoding="utf-8")
            tampered = original_text.replace(
                "Do not guess a model or effort, and do not pick a harness on the user's behalf.",
                "If unavailable, silently fall back to host harness execution.",
            )
            self.assertNotEqual(original_text, tampered, "tamper fixture must change the actual contract")
            target.write_text(tampered, encoding="utf-8")
            status, output = run_main("--root", str(temp_root), "--contract-parity")
            self.assertNotEqual(
                status,
                0,
                "contract parity must fail when silent fallback is introduced into use-other-harness",
            )
            self.assertIn("use-other-harness", output.lower())


if __name__ == "__main__":
    unittest.main()
