"""Generator --check is independent of the checkout's umask (#152).

Only the executable bit is generation's business. Read/write bits come from the
umask of whoever checked the repository out, so a tracked file that arrives as
664 under umask 0002 — the default on Debian-style hosts and on any machine with
a shared group — must not read as drift.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class CheckIsUmaskIndependent(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "workcell"
        shutil.copytree(
            ROOT,
            self.root,
            ignore=shutil.ignore_patterns(
                ".git", ".jj", ".workcell", "dist", "__pycache__", "*.pyc"
            ),
        )

    def check(self, kind: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, f"scripts/sync-{kind}.py", "--check"],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_group_writable_checkout_is_not_drift(self) -> None:
        for path in self.root.rglob("*"):
            if path.is_file() and not os.access(path, os.X_OK):
                path.chmod(0o664)
        for kind in ("agents", "skills"):
            with self.subTest(kind=kind):
                result = self.check(kind)
                self.assertEqual(
                    result.returncode,
                    0,
                    "a umask-0002 checkout must not read as drift:\n"
                    + result.stdout
                    + result.stderr,
                )

    def test_a_lost_executable_bit_is_still_drift(self) -> None:
        script = self.root / "harnesses/claude/skills/build/scripts/waves.py"
        self.assertTrue(script.is_file(), script)
        script.chmod(0o644)
        result = self.check("skills")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            str(script.relative_to(self.root)), result.stdout + result.stderr
        )


if __name__ == "__main__":
    unittest.main()
