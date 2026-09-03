"""Asserts that the harness body checker is wired into CI (.github/workflows/ci.yml)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def ci_steps(workflow: str) -> list[str]:
    """Return every step block in the workflow as a raw string."""
    starts = [m.start() for m in re.finditer(r"(?m)^\s*-\s*name:", workflow)]
    return [
        workflow[starts[i] : starts[i + 1] if i + 1 < len(starts) else len(workflow)]
        for i in range(len(starts))
    ]


def assert_harness_bodies_gate(workflow: str) -> None:
    steps = ci_steps(workflow)
    predicate = lambda s: (
        "name: Harness bodies" in s
        and "scripts/check-harness-bodies.py" in s
        and "timeout-minutes: 5" in s
    )
    if not any(predicate(s) for s in steps):
        raise AssertionError("harness bodies checker gate missing from CI steps")


class CIBodyCheckWiringTests(unittest.TestCase):
    """Verifies that the Harness bodies gate runs in CI with required parameters."""

    def test_harness_bodies_step_is_gated(self) -> None:
        workflow_path = ROOT / ".github" / "workflows" / "ci.yml"
        self.assertTrue(workflow_path.is_file(), "missing .github/workflows/ci.yml")
        workflow = workflow_path.read_text(encoding="utf-8")

        assert_harness_bodies_gate(workflow)

        # Mutation check: deleting the step must cause assert_harness_bodies_gate to fail
        steps = ci_steps(workflow)
        matching = next(
            s
            for s in steps
            if "name: Harness bodies" in s
            and "scripts/check-harness-bodies.py" in s
            and "timeout-minutes: 5" in s
        )
        mutated = workflow.replace(matching, "", 1)
        with self.assertRaisesRegex(
            AssertionError, "harness bodies checker gate missing"
        ):
            assert_harness_bodies_gate(mutated)
