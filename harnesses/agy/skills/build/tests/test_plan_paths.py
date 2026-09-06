"""A planner-accepted write boundary must also be safe to schedule in build."""

import ast
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
SCHEMA = ROOT / "scripts" / "plan_sidecar.py"
RENDER = REPO / "skills" / "plan" / "scripts" / "render_plan.py"
WAVES = ROOT / "scripts" / "waves.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_schema = load("build_write_target_schema", SCHEMA)
plan_schema = load("build_write_target_renderer", RENDER)


def plan():
    return json.loads((ROOT / "examples" / "plan.sidecar.json").read_text())


def set_target(sidecar, field, value):
    issue = sidecar["issues"][0]
    if field == "ownershipHint":
        issue[field] = value
        return "issues[0].ownershipHint"
    issue["acceptanceTests"][0][field] = value
    return "issues[0].acceptanceTests[0].testPath"


class BuildPlanPathTests(unittest.TestCase):
    def test_both_schema_copies_reject_aliases_with_identical_errors(self):
        invalid = (
            "/shared.py", "//host/shared.py", "../shared.py", "tests/../shared.py",
            "tests/../../shared.py", "./shared.py", "tests/./shared.py", ".", "..",
            "tests//shared.py", "tests/shared.py/", "tests\\shared.py", "C:/shared.py",
            "C:shared.py", " shared.py", "shared.py ", "tests/\x00shared.py",
            "tests/\x1bshared.py", "tests/\x7fshared.py", "tests/a.py tests/b.py", "a.py,b.py",
        )
        for field in ("ownershipHint", "testPath"):
            for value in invalid:
                with self.subTest(field=field, value=value):
                    sidecar = plan()
                    where = set_target(sidecar, field, value)
                    errors = []
                    for schema in (plan_schema, build_schema):
                        with self.assertRaises(schema.PlanError) as raised:
                            schema.validate_plan(copy.deepcopy(sidecar))
                        errors.append(str(raised.exception))
                    self.assertEqual(errors[0], errors[1])
                    self.assertIn(where, errors[0])
                    self.assertIn(repr(value), errors[0])

    def test_concrete_tests_and_posix_ownership_globs_match_between_schemas(self):
        for ownership in ("src/**", "*.md", ".github/workflows/*.yml", "src/[ab]/file?.py"):
            with self.subTest(ownership=ownership):
                sidecar = plan()
                set_target(sidecar, "ownershipHint", ownership)
                set_target(sidecar, "testPath", "tests/test_export.py")
                self.assertEqual(
                    plan_schema.validate_plan(copy.deepcopy(sidecar)),
                    build_schema.validate_plan(copy.deepcopy(sidecar)),
                )
        for value in ("tests/**", "tests/test_*.py", "tests/test_?.py", "tests/test_[ab].py"):
            with self.subTest(testPath=value):
                sidecar = plan()
                set_target(sidecar, "testPath", value)
                for schema in (plan_schema, build_schema):
                    with self.assertRaisesRegex(schema.PlanError, "testPath must name one concrete test file"):
                        schema.validate_plan(copy.deepcopy(sidecar))

    def test_alias_collision_fails_before_local_wave_selection(self):
        for field in ("ownershipHint", "testPath"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                sidecar = plan()
                sidecar["repo"] = None
                for index, issue in enumerate(sidecar["issues"]):
                    issue["wave"] = 1
                    issue["dependsOn"] = []
                    issue["ownershipHint"] = f"src/unit{index}/**"
                    for test_index, specification in enumerate(issue["acceptanceTests"]):
                        specification["testPath"] = f"tests/test_unit{index}_{test_index}.py"
                where = set_target(sidecar, field, "tests/../shared.py")
                second = sidecar["issues"][1]
                if field == "ownershipHint":
                    second[field] = "shared.py"
                else:
                    second["acceptanceTests"][0][field] = "shared.py"
                source = Path(temporary) / "plan.sidecar.json"
                source.write_text(json.dumps(sidecar))
                result = subprocess.run(
                    [sys.executable, "-B", str(WAVES), str(source), "--local"],
                    text=True, capture_output=True, check=False,
                )
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(where, result.stderr)
                self.assertIn("canonical relative POSIX", result.stderr)
                self.assertEqual(result.stdout, "", "an invalid plan must not emit a runnable wave")

    def test_mirrored_validation_closure_stays_identical(self):
        functions = ("require_exact_fields", "nonempty_string", "canonical_write_target", "validate_plan", "validate_risks")
        bodies = []
        for source in (RENDER, SCHEMA):
            tree = ast.parse(source.read_text())
            bodies.append({node.name: ast.dump(node) for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in functions})
        self.assertEqual(set(bodies[0]), set(functions))
        self.assertEqual(bodies[0], bodies[1])


if __name__ == "__main__":
    unittest.main()
