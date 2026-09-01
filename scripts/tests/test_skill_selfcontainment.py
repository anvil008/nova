"""Enforce ADR 0022: skill scripts are self-contained.

Two checks. Every ``skills/*/templates/report.css`` is byte-identical to the
others (the lockstep rule each report-rendering.md states in prose), and no
file under ``skills/<name>/scripts/`` builds a code path into a sibling
skill's scripts — mirror-comments and docstrings naming a source are allowed,
executable path constants are not.
"""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"


class ReportCssLockstep(unittest.TestCase):
    def test_report_css_copies_are_byte_identical(self):
        copies = sorted(SKILLS.glob("*/templates/report.css"))
        self.assertGreaterEqual(len(copies), 2, "expected shared report.css copies")
        reference = copies[0].read_bytes()
        for copy in copies[1:]:
            self.assertEqual(
                copy.read_bytes(),
                reference,
                f"{copy.relative_to(ROOT)} drifted from {copies[0].relative_to(ROOT)}; "
                "change all copies together or none (ADR 0022)",
            )


def docstring_nodes(tree):
    """Ids of Constant nodes serving as docstrings, which may cite siblings."""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


class NoCrossSkillScriptReach(unittest.TestCase):
    def test_skill_scripts_do_not_reference_sibling_skill_scripts(self):
        skill_names = {p.name for p in SKILLS.iterdir() if p.is_dir()}
        violations = []
        for script in sorted(SKILLS.glob("*/scripts/**/*.py")):
            own = script.relative_to(SKILLS).parts[0]
            siblings = skill_names - {own}
            tree = ast.parse(script.read_text(encoding="utf-8"))
            allowed = docstring_nodes(tree)
            for node in ast.walk(tree):
                # A bare sibling name only reaches out as a path segment
                # (`parent / "plan"`); elsewhere a constant must name a
                # sibling's scripts directory to count.
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                    right = node.right
                    if isinstance(right, ast.Constant) and right.value in siblings:
                        violations.append(
                            f"{script.relative_to(ROOT)}:{right.lineno}: {right.value!r}"
                        )
                    continue
                if not isinstance(node, ast.Constant) or not isinstance(
                    node.value, str
                ):
                    continue
                if id(node) in allowed:
                    continue
                value = node.value
                if any(
                    f"skills/{name}/scripts" in value or f"../{name}/" in value
                    for name in siblings
                ):
                    violations.append(
                        f"{script.relative_to(ROOT)}:{node.lineno}: {value!r}"
                    )
        self.assertEqual(
            violations,
            [],
            "skill scripts must not reach into sibling skills (ADR 0022); "
            "mirror the helper with a mirror-comment instead:\n"
            + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
