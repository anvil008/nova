"""Acceptance tests for synchronizing harness replicas with trunk build skill and contracts (#217)."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestHarnessTrunkSync(unittest.TestCase):
    """Verifies synchronization of build skill and contracts across all harness replicas."""

    def test_sync_skills_reports_zero_drift(self) -> None:
        """Verify python3 scripts/sync-skills.py --check exits 0 reporting zero drift across all 16 skills."""
        cmd = [sys.executable, str(ROOT / "scripts" / "sync-skills.py"), "--check"]
        res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(
            res.returncode,
            0,
            f"sync-skills.py --check failed (exit code {res.returncode}):\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}",
        )
        self.assertIn(
            "16 skills in sync across 4 harnesses",
            res.stdout,
            f"Unexpected output from sync-skills.py --check:\n{res.stdout}",
        )

    def test_sync_agents_reports_zero_drift(self) -> None:
        """Verify python3 scripts/sync-agents.py --check exits 0 reporting zero drift across all 10 agents."""
        cmd = [sys.executable, str(ROOT / "scripts" / "sync-agents.py"), "--check"]
        res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(
            res.returncode,
            0,
            f"sync-agents.py --check failed (exit code {res.returncode}):\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}",
        )
        self.assertIn(
            "10 agents in sync across 4 harnesses",
            res.stdout,
            f"Unexpected output from sync-agents.py --check:\n{res.stdout}",
        )

    def test_contract_parity_and_bodies_pass(self) -> None:
        """Verify python3 scripts/check-contract-parity.py and python3 scripts/check-harness-bodies.py exit 0 with no violations."""
        # 1. Contract parity check
        parity_cmd = [sys.executable, str(ROOT / "scripts" / "check-contract-parity.py")]
        res_parity = subprocess.run(
            parity_cmd, cwd=ROOT, capture_output=True, text=True, check=False
        )
        self.assertEqual(
            res_parity.returncode,
            0,
            f"check-contract-parity.py failed (exit code {res_parity.returncode}):\nSTDOUT:\n{res_parity.stdout}\nSTDERR:\n{res_parity.stderr}",
        )

        # 2. Harness bodies check
        bodies_cmd = [sys.executable, str(ROOT / "scripts" / "check-harness-bodies.py")]
        res_bodies = subprocess.run(
            bodies_cmd, cwd=ROOT, capture_output=True, text=True, check=False
        )
        self.assertEqual(
            res_bodies.returncode,
            0,
            f"check-harness-bodies.py failed with violations (exit code {res_bodies.returncode}):\nSTDOUT:\n{res_bodies.stdout}\nSTDERR:\n{res_bodies.stderr}",
        )
        self.assertIn(
            "All harness bodies match shared sources cleanly.",
            res_bodies.stdout,
            f"check-harness-bodies.py reported unexpected output:\n{res_bodies.stdout}",
        )


if __name__ == "__main__":
    unittest.main()
