"""Tests for contract parity failure on missing fields and artifacts."""

from __future__ import annotations

import importlib.util
import io
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN_EVALS_PATH = ROOT / "evals" / "run_evals.py"

SPEC = importlib.util.spec_from_file_location("evals_runner", RUN_EVALS_PATH)
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


class ContractParityMissingFieldsTests(unittest.TestCase):
    """Test contract parity failure modes on missing fields and artifacts."""

    def test_parity_holds_on_clean_tree(self) -> None:
        """The un-tampered real repository passes contract parity."""
        output = io.StringIO()
        status = run_evals.check_contract_parity(ROOT, output)
        self.assertEqual(
            status, 0, f"clean tree must pass parity:\n{output.getvalue()}"
        )
        self.assertIn("Contract parity holds", output.getvalue())

    def test_parity_detects_missing_invocation_line(self) -> None:
        """Missing Invocation line fails naming harness, artifact, invocation, expected, actual='missing'."""
        tmpdir, temp_root = copied_tree()
        with tmpdir:
            target = (
                temp_root / "harnesses" / "claude" / "skills" / "build" / "SKILL.md"
            )
            self.assertTrue(target.is_file(), f"missing target: {target}")
            content = target.read_text(encoding="utf-8")
            # Remove the invocation line
            modified = re.sub(r"Invocation:\s*[^\n]+\n?", "", content)
            self.assertNotEqual(content, modified, "failed to strip invocation line")
            target.write_text(modified, encoding="utf-8")

            status, output = run_main("--root", str(temp_root), "--contract-parity")
            self.assertNotEqual(
                status, 0, "contract parity must fail on missing Invocation line"
            )
            self.assertIn("claude", output.lower(), "failure must name harness")
            self.assertIn("build", output.lower(), "failure must name artifact")
            self.assertIn("invocation", output.lower(), "failure must name field")
            self.assertIn(
                "/workcell:build", output, "failure must name expected invocation"
            )
            self.assertIn(
                "'missing'", output.lower(), "failure must name actual as 'missing'"
            )

    def test_parity_detects_deleted_ordered_gates_section(self) -> None:
        """Deleted Ordered Gates section fails naming harness, artifact, gate order, expected, actual='missing'."""
        tmpdir, temp_root = copied_tree()
        with tmpdir:
            target = (
                temp_root / "harnesses" / "claude" / "skills" / "build" / "SKILL.md"
            )
            self.assertTrue(target.is_file(), f"missing target: {target}")
            content = target.read_text(encoding="utf-8")
            # Remove the ## Ordered Gates section
            self.assertIn("## Ordered Gates", content)
            modified = re.sub(
                r"## Ordered Gates\n.*?(?=\n## |\Z)",
                "",
                content,
                flags=re.DOTALL,
            )
            self.assertNotIn("## Ordered Gates", modified)
            target.write_text(modified, encoding="utf-8")

            status, output = run_main("--root", str(temp_root), "--contract-parity")
            self.assertNotEqual(
                status, 0, "contract parity must fail on deleted Ordered Gates section"
            )
            self.assertIn("claude", output.lower(), "failure must name harness")
            self.assertIn("build", output.lower(), "failure must name artifact")
            self.assertTrue(
                "gate order" in output.lower() or "gates" in output.lower(),
                f"failure must name gate field:\n{output}",
            )
            self.assertIn("'approved plan'", output, "failure must name expected gates")
            self.assertIn(
                "'missing'", output.lower(), "failure must name actual as 'missing'"
            )

    def test_parity_detects_truncated_gates(self) -> None:
        """Truncated gates list fails naming harness, artifact, gate order, expected, and actual."""
        tmpdir, temp_root = copied_tree()
        with tmpdir:
            target = (
                temp_root / "harnesses" / "claude" / "skills" / "build" / "SKILL.md"
            )
            self.assertTrue(target.is_file(), f"missing target: {target}")
            content = target.read_text(encoding="utf-8")
            # Replace the 5 ordered gates with only the first 1
            section = content.split("## Ordered Gates", 1)[1].split("\n## ", 1)[0]
            truncated_section = (
                "\n\n1. **approved plan** - required before implementation\n\n"
            )
            modified = content.replace(section, truncated_section)
            self.assertNotEqual(content, modified)
            target.write_text(modified, encoding="utf-8")

            status, output = run_main("--root", str(temp_root), "--contract-parity")
            self.assertNotEqual(
                status, 0, "contract parity must fail on truncated gates list"
            )
            self.assertIn("claude", output.lower(), "failure must name harness")
            self.assertIn("build", output.lower(), "failure must name artifact")
            self.assertTrue(
                "gate order" in output.lower() or "gates" in output.lower(),
                f"failure must name gate field:\n{output}",
            )
            self.assertIn(
                "'integration'",
                output,
                "failure must name expected gates missing from actual",
            )
            self.assertIn(
                "['approved plan']", output, "failure must name actual truncated gates"
            )

    def test_parity_detects_missing_handoff_schema(self) -> None:
        """Missing handoff schema fails naming harness, artifact, handoff, expected, actual='missing'."""
        tmpdir, temp_root = copied_tree()
        with tmpdir:
            target = (
                temp_root / "harnesses" / "claude" / "skills" / "build" / "SKILL.md"
            )
            self.assertTrue(target.is_file(), f"missing target: {target}")
            content = target.read_text(encoding="utf-8")
            self.assertIn("anvil.agent-handoff/v1", content)
            # Remove handoff schema reference
            modified = content.replace("anvil.agent-handoff/v1", "custom-handoff/v1")
            target.write_text(modified, encoding="utf-8")

            status, output = run_main("--root", str(temp_root), "--contract-parity")
            self.assertNotEqual(
                status, 0, "contract parity must fail on missing handoff schema"
            )
            self.assertIn("claude", output.lower(), "failure must name harness")
            self.assertIn("build", output.lower(), "failure must name artifact")
            self.assertIn("handoff", output.lower(), "failure must name field")
            self.assertIn(
                "anvil.agent-handoff/v1", output, "failure must name expected handoff"
            )
            self.assertIn(
                "'missing'", output.lower(), "failure must name actual as 'missing'"
            )

    def test_parity_detects_missing_artifact_file(self) -> None:
        """Missing artifact file fails naming harness, artifact, field artifact drift - expected 'present', got 'missing'."""
        tmpdir, temp_root = copied_tree()
        with tmpdir:
            target = (
                temp_root / "harnesses" / "claude" / "skills" / "build" / "SKILL.md"
            )
            self.assertTrue(target.is_file(), f"missing target: {target}")
            target.unlink()

            status, output = run_main("--root", str(temp_root), "--contract-parity")
            self.assertNotEqual(
                status, 0, "contract parity must fail on missing artifact file"
            )
            self.assertIn("claude", output.lower(), "failure must name harness")
            self.assertIn("build", output.lower(), "failure must name artifact")
            self.assertIn("artifact", output.lower(), "failure must name field")
            self.assertIn(
                "present", output.lower(), "failure must state expected 'present'"
            )
            self.assertIn(
                "missing", output.lower(), "failure must state actual 'missing'"
            )


if __name__ == "__main__":
    unittest.main()
