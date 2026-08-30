from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "workcell_run_evals", ROOT / "evals" / "run_evals.py"
)
assert SPEC and SPEC.loader
run_evals = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_evals
SPEC.loader.exec_module(run_evals)

ROUTING_FLOOR = 77.0


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def case_data(
    name: str, kind: str, owner: str, prompts: list[str] | None = None
) -> dict:
    positives = prompts or [
        f"route alpha {name}",
        f"route beta {name}",
        f"route gamma {name}",
    ]
    return {
        "name": name,
        "kind": kind,
        "trigger": {
            "positive": [{"prompt": prompt, "top_k": 2} for prompt in positives],
            "negative": [
                {"prompt": f"route first {owner}", "owner": owner},
                {"prompt": f"route second {owner}", "owner": owner},
            ],
        },
        "evals": [
            {
                "id": 1,
                "kind": "dialogue",
                "prompt": "Choose the correct route.",
                "expected_output": "A bounded routing decision.",
                "expectations": ["The response chooses an owner."],
            }
        ],
    }


def synthetic_root(
    root: Path,
    first_description: str = "alpha orchard quartz compass",
    second_description: str = "beta harbor violin lantern",
) -> None:
    write(
        root / "skills" / "alpha" / "SKILL.md",
        f"---\nname: alpha\ndescription: {first_description}\n---\n",
    )
    agents = {"vars": {}, "agents": {"beta": {"description": second_description}}}
    write(root / "agents" / "agents.json", json.dumps(agents))
    alpha_case = case_data("alpha", "skill", "agent:beta", [first_description] * 3)
    alpha_case["trigger"]["negative"] = [
        {"prompt": second_description, "owner": "agent:beta"},
        {"prompt": second_description, "owner": "agent:beta"},
    ]
    beta_case = case_data("beta", "agent", "skill:alpha", [second_description] * 3)
    beta_case["trigger"]["negative"] = [
        {"prompt": first_description, "owner": "skill:alpha"},
        {"prompt": first_description, "owner": "skill:alpha"},
    ]
    write(root / "evals" / "cases" / "skills" / "alpha.json", json.dumps(alpha_case))
    write(root / "evals" / "cases" / "agents" / "beta.json", json.dumps(beta_case))
    (root / "evals" / "fixtures").mkdir(parents=True)


class EvalRunnerTests(unittest.TestCase):
    def run_main(self, *args: str) -> tuple[int, str]:
        output = io.StringIO()
        status = run_evals.main(list(args), output)
        return status, output.getvalue()

    def test_every_skill_and_agent_has_a_case(self) -> None:
        status, output = self.run_main("--root", str(ROOT), "--structural")
        self.assertEqual(status, 0, output)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            synthetic_root(root)
            alpha_case = root / "evals" / "cases" / "skills" / "alpha.json"
            alpha_case.unlink()
            status, output = self.run_main("--root", str(root), "--structural")
            self.assertNotEqual(status, 0)
            self.assertIn("missing case file for skill:alpha", output)

        for field, reduced in (
            (
                "positive",
                [{"prompt": "one", "top_k": 1}, {"prompt": "two", "top_k": 1}],
            ),
            ("negative", [{"prompt": "one", "owner": "agent:beta"}]),
            ("evals", []),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                synthetic_root(root)
                path = root / "evals" / "cases" / "skills" / "alpha.json"
                data = json.loads(path.read_text(encoding="utf-8"))
                if field == "evals":
                    data[field] = reduced
                else:
                    data["trigger"][field] = reduced
                path.write_text(json.dumps(data), encoding="utf-8")
                status, output = self.run_main("--root", str(root), "--structural")
                self.assertNotEqual(status, 0)
                self.assertIn("requires at least", output)

    def test_routing_floor_holds_and_mismatch_names_winner(self) -> None:
        status, output = self.run_main(
            "--root", str(ROOT), "--min-rank1", str(ROUTING_FLOOR)
        )
        self.assertEqual(status, 0, output)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            synthetic_root(root)
            path = root / "evals" / "cases" / "skills" / "alpha.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["trigger"]["positive"] = [
                {"prompt": "beta harbor violin lantern", "top_k": 1} for _ in range(3)
            ]
            path.write_text(json.dumps(data), encoding="utf-8")
            status, output = self.run_main("--root", str(root), "--min-rank1", "100")
            self.assertNotEqual(status, 0)
            rows = [
                [field.strip() for field in line.split("|")]
                for line in output.splitlines()
                if line.startswith("skill:alpha | positive |")
            ]
            self.assertEqual(len(rows), 3, output)
            self.assertTrue(all(row[3] == "agent:beta" for row in rows), output)
            self.assertTrue(all(row[5] == "no" for row in rows), output)

    def test_collision_check_errors_at_75_and_warns_at_50(self) -> None:
        shared = "amber cobalt delta ember forest galaxy harbor island"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            synthetic_root(root, f"{shared} juniper kettle", f"{shared} lantern meadow")
            status, output = self.run_main("--root", str(root), "--min-rank1", "0")
            self.assertEqual(status, 0, output)
            self.assertIn("WARNING collision", output)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            synthetic_root(root, shared, shared)
            status, output = self.run_main("--root", str(root), "--min-rank1", "0")
            self.assertNotEqual(status, 0)
            self.assertIn("ERROR collision", output)

    def test_behavioral_dry_run_spawns_nothing(self) -> None:
        results = ROOT / "evals" / "results"
        before = sorted(results.glob("*.json"))
        output = io.StringIO()
        with mock.patch.object(run_evals.subprocess, "run") as spawn:
            status = run_evals.main(
                ["--root", str(ROOT), "--behavioral", "build", "--dry-run"], output
            )
        self.assertEqual(status, 0, output.getvalue())
        spawn.assert_not_called()
        self.assertIn("executor: claude -p", output.getvalue())
        self.assertIn("grader:   claude -p", output.getvalue())
        self.assertEqual(before, sorted(results.glob("*.json")))

    def test_grader_output_validated_before_result_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            synthetic_root(root)
            case = run_evals.load_cases(root)[0]["skill:alpha"]
            evaluation = case.data["evals"][0]
            completed = subprocess.CompletedProcess([], 0, stdout="not JSON", stderr="")
            output = io.StringIO()
            with mock.patch.object(run_evals.subprocess, "run", return_value=completed):
                status = run_evals.run_behavioral_eval(
                    root, case, evaluation, "claude", output
                )
            self.assertNotEqual(status, 0)
            self.assertIn("grader output is not JSON", output.getvalue())
            self.assertFalse(list((root / "evals" / "results").glob("*.json")))

    def test_invalid_json_grader_shapes_are_rejected_before_result_write(self) -> None:
        expectation = "The response chooses an owner."
        valid_result = {
            "expectations": [
                {"text": expectation, "pass": True, "evidence": "trace evidence"}
            ],
            "pass": True,
        }
        invalid_results = {
            "missing expectations": {"pass": True},
            "missing pass": {"expectations": valid_result["expectations"]},
            "expectation count mismatch": {"expectations": [], "pass": True},
            "non-boolean pass": {**valid_result, "pass": "true"},
            "extra top-level key": {**valid_result, "summary": "extra"},
            "disagreeing top-level pass": {
                "expectations": [
                    {
                        "text": expectation,
                        "pass": False,
                        "evidence": "expectation failed",
                    }
                ],
                "pass": True,
            },
        }
        for name, result in invalid_results.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                synthetic_root(root)
                case = run_evals.load_cases(root)[0]["skill:alpha"]
                evaluation = case.data["evals"][0]
                completed = subprocess.CompletedProcess(
                    [], 0, stdout=json.dumps(result), stderr=""
                )
                output = io.StringIO()
                with mock.patch.object(
                    run_evals.subprocess, "run", return_value=completed
                ):
                    status = run_evals.run_behavioral_eval(
                        root, case, evaluation, "claude", output
                    )
                self.assertNotEqual(status, 0, output.getvalue())
                self.assertIn("ERROR grader", output.getvalue())
                self.assertFalse(list((root / "evals" / "results").glob("*.json")))

    def test_ci_and_docs_name_the_free_tiers_and_milestone_contracts(self) -> None:
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        commands = (
            "python3 evals/run_evals.py --structural",
            f"python3 evals/run_evals.py --min-rank1 {ROUTING_FLOOR:g}",
            "python3 -m unittest discover -s evals/tests -p 'test_*.py'",
        )
        for command in commands:
            self.assertIn(command, ci)
            self.assertIn(command, readme)
        self.assertRegex(readme, r"`research`\s*\|\s*findings envelope")
        self.assertIn("single-PR mode", readme)
        self.assertIn("agents/handoff.md", readme)
        for issue in ("#85", "#86", "#87"):
            self.assertIn(issue, changelog)


if __name__ == "__main__":
    unittest.main()
