"""Planner write boundaries must not alias another task's lexical ownership."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "scripts" / "render_plan.py"
SPEC = importlib.util.spec_from_file_location("planner_write_target_renderer", RENDER)
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)

INVALID_TARGETS = (
    "/shared.py", "//host/shared.py", "../shared.py", "tests/../shared.py",
    "tests/../../shared.py", "./shared.py", "tests/./shared.py", ".", "..",
    "tests//shared.py", "tests/shared.py/", "tests\\shared.py", "C:/shared.py",
    "C:shared.py", " shared.py", "shared.py ", "tests/\x00shared.py",
    "tests/\x1bshared.py", "tests/\x7fshared.py",
)


def plan():
    return json.loads((ROOT / "examples" / "sample.sidecar.json").read_text())


def set_target(sidecar, field, value):
    issue = sidecar["issues"][0]
    if field == "ownershipHint":
        issue[field] = value
        return "issues[0].ownershipHint"
    issue["acceptanceTests"][0][field] = value
    return "issues[0].acceptanceTests[0].testPath"


class PlannerWriteTargetTests(unittest.TestCase):
    def test_aliases_are_rejected_for_implementation_and_test_writes(self):
        for field in ("ownershipHint", "testPath"):
            for value in INVALID_TARGETS:
                with self.subTest(field=field, value=value):
                    sidecar = plan()
                    where = set_target(sidecar, field, value)
                    with self.assertRaises(renderer.PlanError) as raised:
                        renderer.validate_plan(sidecar)
                    self.assertIn(where, str(raised.exception))
                    self.assertIn("canonical relative POSIX", str(raised.exception))
                    self.assertIn(repr(value), str(raised.exception))

    def test_relative_posix_ownership_globs_still_validate(self):
        for value in (
            "src/**", "*.md", ".github/workflows/*.yml", "tests/test_[ab].py",
            "src/fixture?.json", "src/a-b_c.1.py", "src/.../file.py",
        ):
            with self.subTest(value=value):
                sidecar = plan()
                set_target(sidecar, "ownershipHint", value)
                self.assertEqual(renderer.validate_plan(sidecar)["issues"][0]["ownershipHint"], value)

    def test_test_paths_are_concrete_and_preserved(self):
        for value in ("tests/test_api.py", ".github/test.py", "test_export.py", "src/a-b_c.1.py"):
            with self.subTest(value=value):
                sidecar = plan()
                set_target(sidecar, "testPath", value)
                validated = renderer.validate_plan(sidecar)
                self.assertEqual(validated["issues"][0]["acceptanceTests"][0]["testPath"], value)
        for value in ("tests/**", "tests/test_*.py", "tests/test_?.py", "tests/test_[ab].py"):
            with self.subTest(value=value):
                sidecar = plan()
                set_target(sidecar, "testPath", value)
                with self.assertRaisesRegex(renderer.PlanError, "testPath must name one concrete test file"):
                    renderer.validate_plan(sidecar)

    def test_renderer_rejects_alias_before_writing_artifacts(self):
        for field in ("ownershipHint", "testPath"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                sidecar = plan()
                where = set_target(sidecar, field, "tests/../shared.py")
                source = Path(temporary) / "plan.sidecar.json"
                output = Path(temporary) / "plan.md"
                source.write_text(json.dumps(sidecar))
                result = subprocess.run(
                    [sys.executable, "-B", str(RENDER), str(source), str(output)],
                    text=True, capture_output=True, check=False,
                )
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(where, result.stderr)
                self.assertIn("canonical relative POSIX", result.stderr)
                self.assertFalse(output.exists())
                self.assertFalse(output.with_suffix(".html").exists())


if __name__ == "__main__":
    unittest.main()
