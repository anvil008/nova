"""Resumable build protocol keeps acceptance separate from source preparation."""

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("build_protocol", ROOT / "scripts/build_run.py")
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)


class AcceptanceContracts(unittest.TestCase):
    def test_unprepared_or_failed_receipt_cannot_advance_integration(self):
        for status in ("preparing", "failed"):
            state = {"head": "accepted", "rounds": {"candidate": {"status": status, "base": "accepted"}}}
            with self.subTest(status=status), patch.object(protocol, "jj") as vcs:
                with self.assertRaisesRegex(protocol.RunError, "only a prepared candidate"):
                    protocol.accept(state, Path("unused"), {}, "candidate", "unused")
                vcs.assert_not_called()

    def test_tracking_mode_survives_resume_and_cannot_drop_remote_dependencies(self):
        plan = {"planId": "local", "planName": "Local", "issues": [
            {"key": "A", "ownershipHint": "a", "wave": 1, "dependsOn": []}
        ]}
        state = {"trackingMode": "github", "integrated": {}, "rounds": {}}
        with patch.object(protocol, "check_head"), patch.object(protocol, "write") as write:
            with self.assertRaisesRegex(protocol.RunError, "preserve that mode"):
                protocol.select(state, Path("unused"), plan, local=True)
            write.assert_not_called()

    def test_existing_github_ledger_cannot_be_reinterpreted_as_local(self):
        state = {"integrated": {"A": "receipt"}, "rounds": {}}
        with patch.object(protocol, "check_head"):
            with self.assertRaisesRegex(protocol.RunError, "run uses github tracking"):
                protocol.select(state, Path("unused"), {}, local=True)


if __name__ == "__main__":
    unittest.main()
