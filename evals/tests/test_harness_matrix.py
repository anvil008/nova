"""Acceptance tests for Issue #157: Harness matrix and behavioral dry-runs.

Covers acceptance tests:
- free-evals-run-for-four-families (integration)
- four-native-behavioral-dry-runs (unit)
"""

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
SPEC = importlib.util.spec_from_file_location(
    "workcell_run_evals", ROOT / "evals" / "run_evals.py"
)
assert SPEC and SPEC.loader
run_evals = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_evals
SPEC.loader.exec_module(run_evals)

HARNESSES = ("claude", "codex", "agy", "grok")


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


class HarnessMatrixTests(unittest.TestCase):
    """Test run_evals matrix across all four harness families."""

    def test_free_evals_run_for_four_families(self) -> None:
        """run_evals.py --harness <h> exits 0 for all four and prints harness/document/case totals."""
        for harness in HARNESSES:
            status, output = run_main("--root", str(ROOT), "--harness", harness)
            self.assertEqual(
                status,
                0,
                f"run_evals --harness {harness} failed with status {status}:\n{output}",
            )
            self.assertIn(
                harness,
                output.lower(),
                f"run_evals --harness {harness} output must name the harness family:\n{output}",
            )
            # Must print document totals from that generated family (25 or 26 documents/descriptions)
            self.assertTrue(
                re.search(r"(?:25|26)\s*(?:documents?|descriptions?)", output, re.IGNORECASE),
                f"run_evals --harness {harness} output must report document totals from that generated family:\n{output}",
            )
            # Must print case totals (26 cases)
            self.assertTrue(
                re.search(r"26\s*cases?", output, re.IGNORECASE),
                f"run_evals --harness {harness} output must report case totals:\n{output}",
            )

    def test_free_evals_structural_run_for_four_families(self) -> None:
        """run_evals.py --harness <h> --structural exits 0 and prints totals for all four."""
        for harness in HARNESSES:
            status, output = run_main(
                "--root", str(ROOT), "--harness", harness, "--structural"
            )
            self.assertEqual(
                status,
                0,
                f"run_evals --harness {harness} --structural failed with status {status}:\n{output}",
            )
            self.assertIn(
                harness,
                output.lower(),
                f"run_evals --harness {harness} --structural output must name the harness:\n{output}",
            )
            self.assertTrue(
                re.search(r"(?:25|26)\s*(?:documents?|descriptions?)", output, re.IGNORECASE),
                f"run_evals --harness {harness} --structural must report document totals:\n{output}",
            )
            self.assertTrue(
                re.search(r"26\s*cases?", output, re.IGNORECASE),
                f"run_evals --harness {harness} --structural must report case totals:\n{output}",
            )

    def test_free_evals_loads_generated_documents_by_harness(self) -> None:
        """run_evals.py --harness <h> loads generated documents for that family, catching drift."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir) / "workcell"
            shutil.copytree(
                ROOT,
                temp_root,
                ignore=shutil.ignore_patterns(".git", ".jj", "dist", "__pycache__", "*.pyc"),
            )
            # Corrupt a generated skill document under harnesses/claude
            target = temp_root / "harnesses" / "claude" / "skills" / "build" / "SKILL.md"
            self.assertTrue(target.is_file(), f"missing fixture: {target}")
            target.unlink()

            status, output = run_main("--root", str(temp_root), "--harness", "claude")
            self.assertNotEqual(
                status,
                0,
                "run_evals.py --harness claude must fail when a generated claude document is missing",
            )
            self.assertIn("build", output.lower())


class NativeBehavioralDryRunTests(unittest.TestCase):
    """Test behavioral dry-run command generation across harnesses."""

    def test_four_native_behavioral_dry_runs(self) -> None:
        """Dry runs emit claude -p, codex exec, agy -p, or grok --no-auto-update -p with workspace/trace options."""
        # claude: emits claude -p
        status, output = run_main(
            "--root", str(ROOT), "--behavioral", "build", "--harness", "claude", "--dry-run"
        )
        self.assertEqual(status, 0, output)
        self.assertIn("claude -p", output)

        # codex: emits codex exec with workspace/trace options
        status, output = run_main(
            "--root", str(ROOT), "--behavioral", "build", "--harness", "codex", "--dry-run"
        )
        self.assertEqual(status, 0, output)
        self.assertIn("codex exec", output)
        self.assertIn("--cd", output)
        self.assertIn("-o", output)

        # agy: emits agy -p with workspace/trace options
        status, output = run_main(
            "--root", str(ROOT), "--behavioral", "build", "--harness", "agy", "--dry-run"
        )
        self.assertEqual(status, 0, output)
        self.assertIn("agy -p", output)

        # grok: emits grok --no-auto-update -p with workspace/trace options
        status, output = run_main(
            "--root", str(ROOT), "--behavioral", "build", "--harness", "grok", "--dry-run"
        )
        self.assertEqual(status, 0, output)
        self.assertIn("grok", output)
        self.assertIn("--no-auto-update", output)
        self.assertIn("-p", output)

    def test_behavioral_dry_run_unknown_harness_fails(self) -> None:
        """Unknown harness fails for behavioral dry runs."""
        status, _output = run_main(
            "--root", str(ROOT), "--behavioral", "build", "--harness", "unknown-harness", "--dry-run"
        )
        self.assertNotEqual(status, 0, "unknown harness must fail")

        # Calling _behavioral_commands directly with unknown harness must raise ValueError
        _errors, _documents, cases = run_evals.structural_errors(ROOT)
        case = cases["skill:build"]
        eval_item = case.data["evals"][0]
        with self.assertRaises(ValueError):
            run_evals._behavioral_commands(
                case, eval_item, "unknown-harness", "/tmp/ws", "/tmp/trace.txt"
            )


if __name__ == "__main__":
    unittest.main()
