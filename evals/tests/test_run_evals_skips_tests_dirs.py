"""Regression test for run_evals skipping 'tests' directories across harnesses.

Proves that evals/run_evals.py skips any 'tests/' directories when enumerating
agents and skills for every harness (agy, claude, codex), ensuring that harness-owned
test directories like harnesses/agy/agents/tests/ do not cause missing agent.md or
skill errors.
"""

from __future__ import annotations

import importlib.util
import io
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


class RunEvalsSkipsTestsDirsTests(unittest.TestCase):
    def test_run_evals_agy_succeeds_with_existing_harness_tests(self) -> None:
        """agy harness in repo has harnesses/agy/agents/tests/; run_evals must exit 0."""
        status, output = run_main("--harness", "agy")
        self.assertEqual(status, 0, f"Expected 0 exit status for agy, got {status}: {output}")
        self.assertNotIn("missing agent.md", output)

    def test_run_evals_skips_tests_dirs_for_all_harnesses(self) -> None:
        """Synthetic tests/ directories under agents/ and skills/ must be skipped for agy, claude, codex."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            for harness in ("agy", "claude", "codex"):
                docs, errors = run_evals.load_documents(ROOT, harness=harness)
                self.assertEqual(errors, [], f"Unexpected errors loading documents for {harness}: {errors}")

            for harness in ("agy", "claude", "codex"):
                h_dir = tmp_root / "harnesses" / harness
                skills_dir = h_dir / "skills"
                agents_dir = h_dir / "agents"
                skills_dir.mkdir(parents=True, exist_ok=True)
                agents_dir.mkdir(parents=True, exist_ok=True)

                # Add dummy skill
                s_dir = skills_dir / "test-skill"
                s_dir.mkdir()
                (s_dir / "SKILL.md").write_text(
                    "---\nname: test-skill\ndescription: Test skill description\n---\n",
                    encoding="utf-8",
                )

                # Add tests/ dir in skills (without SKILL.md or with invalid files)
                s_tests = skills_dir / "tests"
                s_tests.mkdir()
                (s_tests / "test_something.py").write_text("# dummy test\n", encoding="utf-8")

                # Add tests/ dir in agents
                a_tests = agents_dir / "tests"
                a_tests.mkdir()
                (a_tests / "test_agent.py").write_text("# dummy test\n", encoding="utf-8")

                # Add dummy agent
                if harness == "agy":
                    b_dir = agents_dir / "builder"
                    b_dir.mkdir()
                    (b_dir / "agent.md").write_text(
                        "---\nname: builder\ndescription: Builder agent\n---\n",
                        encoding="utf-8",
                    )
                else:
                    (agents_dir / "builder.md").write_text(
                        "---\nname: builder\ndescription: Builder agent\n---\n",
                        encoding="utf-8",
                    )

                docs, errors = run_evals.load_documents(tmp_root, harness=harness)
                self.assertEqual(
                    errors,
                    [],
                    f"Harness {harness} failed to skip tests/ dir: {errors}",
                )
                self.assertIn("skill:test-skill", docs)
                self.assertIn("agent:builder", docs)
                self.assertNotIn("agent:tests", docs)
                self.assertNotIn("skill:tests", docs)


if __name__ == "__main__":
    unittest.main()
