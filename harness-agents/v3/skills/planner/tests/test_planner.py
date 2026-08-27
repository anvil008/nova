import json
import subprocess
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "scripts" / "render_plan.py"
RECONCILE = ROOT / "scripts" / "reconcile_github.py"


def sample_plan():
    return {
        "planId": "planner-v3",
        "planName": "Planner v3",
        "repo": "foundry-zero/swarm-coder",
        "generatedAt": "2026-08-26T12:00:00Z",
        "summary": "Ship an offline plan report and approved GitHub milestone.",
        "architecture": {
            "components": [
                {"name": "Renderer", "purpose": "Build the offline report."},
                {"name": "Reconciler", "purpose": "Apply approved GitHub state."},
            ],
            "diagramsMermaid": {
                "targetArchitecture": "flowchart LR\n  Plan[Sidecar] --> Report[HTML]\n  Plan --> GitHub[GitHub]"
            },
        },
        "issues": [
            {
                "key": "render",
                "title": "Render offline plan",
                "body": "Render the approved design.",
                "labels": ["planning"],
                "dependsOn": [],
                "ownershipHint": "templates/**",
                "wave": 1,
                "acceptanceTests": [
                    {"name": "renders_offline", "kind": "unit", "oracle": "HTML has no external resource loads", "testPath": "tests/test_render.py"}
                ],
            },
            {
                "key": "sync",
                "title": "Reconcile GitHub milestone",
                "body": "Apply the approved plan without duplicates.",
                "labels": ["planning", "automation"],
                "dependsOn": ["render"],
                "ownershipHint": "scripts/**",
                "wave": 2,
                "acceptanceTests": [
                    {"name": "idempotent_rerun", "kind": "integration", "oracle": "second reconcile yields zero actions"}
                ],
            },
        ],
    }


class StructureParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.mermaid_blocks = 0

    def handle_starttag(self, tag, attrs):
        if tag == "pre" and "mermaid" in dict(attrs).get("class", "").split():
            self.mermaid_blocks += 1


class PlannerSkillTests(unittest.TestCase):
    def run_script(self, script, *args):
        return subprocess.run(
            ["python3", str(script), *map(str, args)],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

    def test_render_is_self_contained_structured_and_has_three_diagrams(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            output = Path(tmp) / "plan.html"
            sidecar.write_text(json.dumps(sample_plan()), encoding="utf-8")
            result = self.run_script(RENDER, sidecar, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = output.read_text(encoding="utf-8")

        for token in (
            "--bg:#f7f6f3",
            "--panel:#ffffff",
            "--fg:#1a1a1a",
            "--mut:#6b6b6b",
            "--accent:#2b4c7e",
            "--border:#e2e0da",
            "--rule:#d8d5cd",
            "--bg:#16171a",
            "--panel:#1d1f24",
            "--fg:#e8e8e6",
            "--mut:#9a9a9a",
            "--accent:#7aa2d6",
            "--border:#2a2d33",
            "--rule:#2a2d33",
        ):
            self.assertIn(token, rendered)
        self.assertNotIn("https://cdn", rendered)
        self.assertNotIn("<link rel=", rendered)
        self.assertIn("mermaid.initialize", rendered)
        self.assertIn("flowchart LR", rendered)
        self.assertIn("flowchart TD", rendered)
        self.assertIn("diagram-fallback", rendered)
        self.assertIn("data-theme", rendered)

        parser = StructureParser()
        parser.feed(rendered)
        self.assertGreaterEqual(parser.mermaid_blocks, 3)
        headings = [
            "Overview / Goal",
            "Architecture",
            "Task Breakdown",
            "Risks &amp; Open Questions",
            "Milestone &amp; Execution",
        ]
        positions = [rendered.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))

    def test_renderer_rejects_unknown_schema_fields(self):
        plan = sample_plan()
        plan["milestone"] = "not in v3 schema"
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            output = Path(tmp) / "plan.html"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            result = self.run_script(RENDER, sidecar, output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown field", result.stderr.lower())

    def test_renderer_rejects_dependency_keys_that_are_not_safe_slugs(self):
        for dependency in ("bad key", 'evil\"] --> injected[\"pwn', "../escape", "bad_key"):
            with self.subTest(dependency=dependency), tempfile.TemporaryDirectory() as tmp:
                plan = sample_plan()
                plan["issues"][1]["dependsOn"] = [dependency]
                sidecar = Path(tmp) / "plan.sidecar.json"
                output = Path(tmp) / "plan.html"
                sidecar.write_text(json.dumps(plan), encoding="utf-8")
                result = self.run_script(RENDER, sidecar, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("stable ascii slugs", result.stderr.lower())

    def test_unknown_valid_dependency_is_neutral_and_component_string_is_safe(self):
        plan = sample_plan()
        plan["architecture"]["components"].append("<External API>")
        plan["issues"][1]["dependsOn"] = ["External-API"]
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            output = Path(tmp) / "plan.html"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            result = self.run_script(RENDER, sidecar, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = output.read_text(encoding="utf-8")
        self.assertIn("issue_External_API", rendered)
        self.assertIn("class issue_External_API neutral", rendered)
        self.assertIn("stroke:var(--mut)!important", rendered)
        self.assertIn("&lt;External API&gt;", rendered)
        self.assertNotIn("<External API>", rendered)

        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("mixed-case ASCII slug", skill)
        self.assertIn("string shorthand", skill)

    def test_brief_style_uppercase_keys_reconcile_without_duplication(self):
        plan = sample_plan()
        plan["issues"][0]["key"] = "T0"
        plan["issues"][1]["key"] = "T1"
        plan["issues"][1]["dependsOn"] = ["T0"]
        marker = "<!-- swarm-planner planId=planner-v3 issue=T0 -->"
        snapshot = {
            "milestones": [{
                "number": 7,
                "title": plan["planName"],
                "description": "<!-- swarm-planner planId=planner-v3 -->",
                "state": "open",
            }],
            "issues": [{
                "number": 10,
                "title": plan["issues"][0]["title"],
                "body": plan["issues"][0]["body"] + "\n\n" + marker,
                "labels": [{"name": "planning"}],
                "milestone": {"number": 7},
                "state": "open",
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            state = Path(tmp) / "snapshot.json"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            state.write_text(json.dumps(snapshot), encoding="utf-8")
            result = self.run_script(RECONCILE, sidecar, "--snapshot", state)
        self.assertEqual(result.returncode, 0, result.stderr)
        actions = json.loads(result.stdout)["actions"]
        self.assertFalse(any(action["action"] in {"create_issue", "close_duplicate_issue"} and action.get("key") == "T0" for action in actions))
        self.assertTrue(any(action["action"] == "create_issue" and action["key"] == "T1" for action in actions))

    def test_reconcile_snapshot_updates_creates_closes_and_deduplicates(self):
        plan = sample_plan()
        marker = "<!-- swarm-planner planId=planner-v3 issue=render -->"
        snapshot = {
            "milestones": [
                {
                    "number": 7,
                    "title": "Old title",
                    "description": "<!-- swarm-planner planId=planner-v3 -->",
                    "state": "open",
                }
            ],
            "issues": [
                {
                    "number": 10,
                    "title": "Old issue title",
                    "body": "Old body\n\n" + marker,
                    "labels": [{"name": "planning"}],
                    "milestone": {"number": 7},
                    "state": "open",
                },
                {
                    "number": 11,
                    "title": "Removed issue",
                    "body": "Gone\n\n<!-- swarm-planner planId=planner-v3 issue=removed -->",
                    "labels": [],
                    "milestone": {"number": 7},
                    "state": "open",
                },
                {
                    "number": 12,
                    "title": "Duplicate",
                    "body": "Duplicate\n\n" + marker,
                    "labels": [],
                    "milestone": {"number": 7},
                    "state": "open",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            state = Path(tmp) / "snapshot.json"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            state.write_text(json.dumps(snapshot), encoding="utf-8")
            result = self.run_script(RECONCILE, sidecar, "--snapshot", state)
        self.assertEqual(result.returncode, 0, result.stderr)
        actions = json.loads(result.stdout)["actions"]
        action_pairs = {(action["action"], action.get("number")) for action in actions}
        self.assertIn(("update_milestone", 7), action_pairs)
        self.assertIn(("update_issue", 10), action_pairs)
        self.assertIn(("close_removed_issue", 11), action_pairs)
        self.assertIn(("close_duplicate_issue", 12), action_pairs)
        self.assertTrue(any(action["action"] == "create_issue" and action["key"] == "sync" for action in actions))
        update = next(action for action in actions if action["action"] == "update_issue")
        self.assertIn(marker, update["payload"]["body"])

    def test_validation_requires_acceptance_tests(self):
        plan = sample_plan()
        del plan["issues"][0]["acceptanceTests"]
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            output = Path(tmp) / "plan.html"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            result = self.run_script(RENDER, sidecar, output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("acceptancetests", result.stderr.lower())

    def test_acceptance_tests_render_into_issue_body_not_html(self):
        plan = sample_plan()
        oracle = "HTML has no external resource loads"
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            output = Path(tmp) / "plan.html"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            result = self.run_script(RENDER, sidecar, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = output.read_text(encoding="utf-8")
        self.assertNotIn("Definition of Done", rendered)
        self.assertNotIn(oracle, rendered)

        snapshot = {"milestones": [], "issues": []}
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            state = Path(tmp) / "snapshot.json"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            state.write_text(json.dumps(snapshot), encoding="utf-8")
            result = self.run_script(RECONCILE, sidecar, "--snapshot", state)
        self.assertEqual(result.returncode, 0, result.stderr)
        actions = json.loads(result.stdout)["actions"]
        create = next(a for a in actions if a["action"] == "create_issue" and a["key"] == "render")
        body = create["payload"]["body"]
        self.assertIn("Definition of Done (tests)", body)
        self.assertIn("renders_offline", body)
        self.assertIn(oracle, body)

    def test_skill_requires_approval_and_documents_milestones_only(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\nname: planner\n"))
        self.assertIn("human approval", skill.lower())
        self.assertIn("must stop", skill.lower())
        self.assertIn("GitHub milestone", skill)
        self.assertIn("Use milestones only; never create or modify a GitHub Project", skill)
        self.assertIn("--apply", skill)


if __name__ == "__main__":
    unittest.main()
