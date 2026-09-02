"""Acceptance tests for Issue #157: Contract parity detection across harness families.

Covers acceptance test:
- parity-detects-each-contract-field (integration)
  Oracle: Real tree passes; temporary drift in invocation, gate order, handoff or
  oracle fails naming harness/artifact/field/expected/actual.
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import shutil
import sys
import tempfile
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


def copied_tree() -> tuple[tempfile.TemporaryDirectory, Path]:
    tmpdir = tempfile.TemporaryDirectory()
    target = Path(tmpdir.name) / "workcell"
    shutil.copytree(
        ROOT,
        target,
        ignore=shutil.ignore_patterns(".git", ".jj", "dist", "__pycache__", "*.pyc"),
    )
    return tmpdir, target


class ContractParityTests(unittest.TestCase):
    """Test contract parity verification across all four harnesses."""

    def test_real_tree_contract_parity_passes(self) -> None:
        """Real tree passes contract parity check."""
        status, output = run_main("--root", str(ROOT), "--contract-parity")
        self.assertEqual(
            status,
            0,
            f"contract parity on real tree must pass, got status {status}:\n{output}",
        )
        # Direct function call must also exit 0
        direct_out = io.StringIO()
        self.assertEqual(run_evals.check_contract_parity(ROOT, direct_out), 0)

    def test_parity_detects_invocation_drift(self) -> None:
        """Temporary drift in invocation fails naming harness/artifact/field/expected/actual."""
        tmpdir, temp_root = copied_tree()
        with tmpdir:
            target = temp_root / "harnesses" / "claude" / "skills" / "build" / "SKILL.md"
            self.assertTrue(target.is_file())
            content = target.read_text(encoding="utf-8")
            self.assertIn("Invocation: `/workcell:build`", content)
            tampered = content.replace(
                "Invocation: `/workcell:build`",
                "Invocation: `/workcell:drifted-build`",
            )
            target.write_text(tampered, encoding="utf-8")

            status, output = run_main("--root", str(temp_root), "--contract-parity")
            self.assertNotEqual(
                status,
                0,
                "contract parity must fail on drifted invocation",
            )
            # Must name harness, artifact, field, expected, actual
            self.assertIn("claude", output.lower(), "failure must name harness")
            self.assertIn("build", output.lower(), "failure must name artifact")
            self.assertTrue(
                re.search(r"invocation", output, re.IGNORECASE),
                f"failure must name field 'invocation':\n{output}",
            )
            self.assertIn("/workcell:build", output, "failure must name expected value")
            self.assertIn("/workcell:drifted-build", output, "failure must name actual value")

    def test_parity_detects_gate_order_drift(self) -> None:
        """Temporary drift in gate order fails naming harness/artifact/field/expected/actual."""
        tmpdir, temp_root = copied_tree()
        with tmpdir:
            target = temp_root / "harnesses" / "claude" / "skills" / "build" / "SKILL.md"
            self.assertTrue(target.is_file())
            content = target.read_text(encoding="utf-8")
            # Swap gates 1 and 2 in Ordered Gates
            gate1 = "1. **approved plan**: Validate `plan.sidecar.json` and snapshot GitHub issue state to schedule dependency waves."
            gate2 = "2. **specifier RED seal**: Specifier authors failing acceptance tests and seals them with `tdd-guard seal`."
            self.assertIn(gate1, content)
            self.assertIn(gate2, content)
            swapped_content = content.replace(gate1, "TMP_GATE").replace(gate2, gate1).replace("TMP_GATE", gate2)
            target.write_text(swapped_content, encoding="utf-8")

            status, output = run_main("--root", str(temp_root), "--contract-parity")
            self.assertNotEqual(
                status,
                0,
                "contract parity must fail on drifted gate order",
            )
            self.assertIn("claude", output.lower(), "failure must name harness")
            self.assertIn("build", output.lower(), "failure must name artifact")
            self.assertTrue(
                re.search(r"(?:gate\s*order|orderedGates|gates)", output, re.IGNORECASE),
                f"failure must name field 'gate order' or 'orderedGates':\n{output}",
            )
            self.assertTrue(
                "approved plan" in output or "expected" in output.lower(),
                f"failure must name expected gate order:\n{output}",
            )
            self.assertTrue(
                "specifier RED seal" in output or "actual" in output.lower(),
                f"failure must name actual gate order:\n{output}",
            )

    def test_parity_detects_handoff_drift(self) -> None:
        """Temporary drift in handoff schema fails naming harness/artifact/field/expected/actual."""
        tmpdir, temp_root = copied_tree()
        with tmpdir:
            # Drift handoff in agy builder agent
            target = temp_root / "harnesses" / "agy" / "agents" / "builder" / "agent.md"
            self.assertTrue(target.is_file(), f"missing fixture: {target}")
            content = target.read_text(encoding="utf-8")
            self.assertIn("anvil.agent-handoff/v1", content)
            tampered = content.replace("anvil.agent-handoff/v1", "anvil.agent-handoff/v9-drifted")
            target.write_text(tampered, encoding="utf-8")

            status, output = run_main("--root", str(temp_root), "--contract-parity")
            self.assertNotEqual(
                status,
                0,
                "contract parity must fail on drifted handoff schema",
            )
            self.assertIn("agy", output.lower(), "failure must name harness")
            self.assertIn("builder", output.lower(), "failure must name artifact")
            self.assertTrue(
                re.search(r"handoff(?:Schema)?", output, re.IGNORECASE),
                f"failure must name field 'handoff':\n{output}",
            )
            self.assertIn("anvil.agent-handoff/v1", output, "failure must name expected handoff")
            self.assertIn("anvil.agent-handoff/v9-drifted", output, "failure must name actual handoff")

    def test_parity_detects_oracle_drift(self) -> None:
        """Temporary drift in acceptance oracle fails naming harness/artifact/field/expected/actual."""
        tmpdir, temp_root = copied_tree()
        with tmpdir:
            # Drift oracle in contracts carrier or skill doc
            carrier = temp_root / "harnesses" / "claude" / "runtime" / "contracts.json"
            self.assertTrue(carrier.is_file(), f"missing carrier: {carrier}")
            data = json.loads(carrier.read_text(encoding="utf-8"))
            skill_entry = next(s for s in data["contract"]["skills"] if s["name"] == "build")
            original_oracle = skill_entry["acceptanceOracle"]
            skill_entry["acceptanceOracle"] = "Tampered oracle that must fail parity check."
            carrier.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

            status, output = run_main("--root", str(temp_root), "--contract-parity")
            self.assertNotEqual(
                status,
                0,
                "contract parity must fail on drifted acceptance oracle",
            )
            self.assertIn("claude", output.lower(), "failure must name harness")
            self.assertIn("build", output.lower(), "failure must name artifact")
            self.assertTrue(
                re.search(r"(?:acceptance)?oracle", output, re.IGNORECASE),
                f"failure must name field 'oracle':\n{output}",
            )
            self.assertIn(original_oracle, output, "failure must name expected oracle")
            self.assertIn("Tampered oracle", output, "failure must name actual oracle")

    def test_parity_excludes_body_prose_differences(self) -> None:
        """Body prose differences are excluded and do not fail contract parity."""
        tmpdir, temp_root = copied_tree()
        with tmpdir:
            target = temp_root / "harnesses" / "claude" / "skills" / "build" / "SKILL.md"
            self.assertTrue(target.is_file())
            content = target.read_text(encoding="utf-8")
            # Append body prose commentary that doesn't modify contract fields
            tampered = content + "\n\n## Custom Commentary\n\nThis is extra body prose explaining internal implementation details.\n"
            target.write_text(tampered, encoding="utf-8")

            status, output = run_main("--root", str(temp_root), "--contract-parity")
            self.assertEqual(
                status,
                0,
                f"body prose modifications must be excluded from contract parity failures:\n{output}",
            )


if __name__ == "__main__":
    unittest.main()
