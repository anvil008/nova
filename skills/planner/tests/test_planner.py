# Load reconcile_github
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = str(ROOT / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
import reconcile_github

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "scripts" / "render_plan.py"
RECONCILE = ROOT / "scripts" / "reconcile_github.py"


def sample_plan():
    return {
        "planId": "planner-v3",
        "planName": "Planner v3",
        "repo": "foundry-zero/workcell",
        "generatedAt": "2026-08-26T12:00:00Z",
        "summary": "Ship an offline plan report and approved GitHub milestone.",
        "architecture": {
            "changeSummary": "Move from a sidecar that feeds an unlabeled target view to an explicit current-versus-proposed review before approval.",
            "components": [
                {"name": "Renderer", "purpose": "Build the offline report."},
                {"name": "Reconciler", "purpose": "Apply approved GitHub state."},
            ],
            "diagramsMermaid": {
                "currentArchitecture": "flowchart LR\n  Plan[Sidecar] --> Report[Target-only HTML]\n  Plan --> GitHub[GitHub]",
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
        "risks": [
            {
                "id": "R-01",
                "title": "Renderer and reconciler drift apart",
                "likelihood": 2,
                "impact": 3,
                "owner": "planner",
                "mitigation": "Both read the same validated sidecar.",
            },
        ],
}


REPO_ROOT = ROOT.parents[1]
RECONCILE_FINDINGS = REPO_ROOT / "skills" / "code-review" / "scripts" / "reconcile_findings.py"
REVIEW_EXAMPLE = REPO_ROOT / "skills" / "code-review" / "examples" / "expected-review.json"
STUB_LOGIN = "real-user"
STUB_REPO = "stub-owner/stub-repo"

GH_STUB = r'''#!/usr/bin/env python3
import json
import os
import sys

LOGIN = "real-user"
argv = sys.argv[1:]
with open(os.environ["GH_STUB_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(argv) + "\n")

if not argv or argv[0] != "api":
    raise SystemExit(0)
rest = argv[1:]
TAKES_VALUE = {"--method", "--jq", "-q", "--input", "--field", "-f", "-F", "-H", "--header", "--template"}
method, endpoint, skip = "GET", "", False
for index, item in enumerate(rest):
    if skip:
        skip = False
        continue
    if item in TAKES_VALUE:
        skip = True
        if item == "--method" and index + 1 < len(rest):
            method = rest[index + 1].upper()
        continue
    if item.startswith("-"):
        continue
    endpoint = item
path = endpoint.split("?")[0].strip("/")
if path == "user":
    print(json.dumps({"login": LOGIN, "id": 1}))
elif method == "GET":
    print("[]")
elif method == "POST" and path.endswith("/milestones"):
    print(json.dumps({"number": 1}))
elif method == "POST":
    print(json.dumps({"number": 101}))
elif method == "PATCH":
    tail = path.rsplit("/", 1)[-1]
    print(json.dumps({"number": int(tail) if tail.isdigit() else 1}))
else:
    print("{}")
'''


def gh_stub(directory):
    binary = Path(directory) / "bin"
    binary.mkdir(parents=True, exist_ok=True)
    stub = binary / "gh"
    stub.write_text(GH_STUB, encoding="utf-8")
    stub.chmod(0o755)
    log = Path(directory) / "gh-calls.log"
    log.write_text("", encoding="utf-8")
    environment = dict(os.environ)
    environment["PATH"] = f"{binary}{os.pathsep}{environment.get('PATH', '')}"
    environment["GH_STUB_LOG"] = str(log)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment, log


def gh_calls(log):
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def writes_attempted(log):
    return [call for call in gh_calls(log)
            if any(item.upper() in {"POST", "PATCH", "PUT", "DELETE"} for item in call)]


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
            check=False,
        )

    def test_render_is_self_contained_structured_and_has_visual_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            output = Path(tmp) / "plan.html"
            sidecar.write_text(json.dumps(sample_plan()), encoding="utf-8")
            result = self.run_script(RENDER, sidecar, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = output.read_text(encoding="utf-8")

        for token in (
            '[data-theme="light"]',
            "--sev-critical:",
            "--sev-high:",
            "--sev-medium:",
            "--sev-low:",
            "--sev-nit:",
            "--wave-1:",
            "--wave-stroke:",
            "@media print",
            "prefers-reduced-motion",
            "@media (max-width: 900px)",
        ):
            self.assertIn(token, rendered)
        self.assertNotIn("https://cdn", rendered)
        self.assertNotIn("<link rel=", rendered)
        self.assertIn("mermaid.initialize", rendered)
        self.assertIn("flowchart LR", rendered)
        self.assertIn("flowchart TD", rendered)
        self.assertIn("diagram-fallback", rendered)
        self.assertIn('class="architecture-state current"', rendered)
        self.assertIn('class="architecture-state proposed"', rendered)
        self.assertIn(">Current</h3>", rendered)
        self.assertIn(">Proposed</h3>", rendered)
        self.assertIn("Target-only HTML", rendered)
        self.assertIn("explicit current-versus-proposed review", rendered)
        self.assertIn("data-theme", rendered)

        parser = StructureParser()
        parser.feed(rendered)
        self.assertGreaterEqual(parser.mermaid_blocks, 4)
        headings = [
            "Overview",
            "Architecture",
            "Task Breakdown",
            "Execution Waves",
            "Risks",
            "Milestone &amp; Execution",
        ]
        positions = [rendered.index(f">{heading}</h2>") for heading in headings]
        self.assertEqual(positions, sorted(positions))

    def test_renderer_requires_current_and_proposed_visuals(self):
        for missing in ("currentArchitecture", "targetArchitecture"):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as tmp:
                plan = sample_plan()
                del plan["architecture"]["diagramsMermaid"][missing]
                sidecar = Path(tmp) / "plan.sidecar.json"
                output = Path(tmp) / "plan.html"
                sidecar.write_text(json.dumps(plan), encoding="utf-8")
                result = self.run_script(RENDER, sidecar, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(f"architecture.diagramsmermaid.{missing.lower()} is required", result.stderr.lower())

    def test_renderer_requires_textual_architecture_delta(self):
        plan = sample_plan()
        plan["architecture"]["changeSummary"] = "  "
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            output = Path(tmp) / "plan.html"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            result = self.run_script(RENDER, sidecar, output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("architecture.changesummary must be a non-empty string", result.stderr.lower())

    def test_two_renders_are_byte_identical_and_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            first = Path(tmp) / "first.html"
            second = Path(tmp) / "second.html"
            sidecar.write_text(json.dumps(sample_plan()), encoding="utf-8")
            first_result = self.run_script(RENDER, sidecar, first)
            second_result = self.run_script(RENDER, sidecar, second)
            self.assertEqual(first_result.returncode, 0, first_result.stderr)
            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            first_bytes = first.read_bytes()
            second_bytes = second.read_bytes()
        self.assertEqual(first_bytes, second_bytes)
        rendered = first_bytes.decode("utf-8")
        self.assertNotIn("<script src=", rendered)
        self.assertNotIn("<link rel=", rendered)
        self.assertIn("@media print", rendered)
        self.assertIn("Proposed &mdash; awaiting explicit human approval", rendered)
        self.assertIn("<!-- workcell-planner planId=planner-v3 -->", rendered)

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

        contract = (ROOT / "references" / "sidecar-contract.md").read_text(encoding="utf-8")
        self.assertIn("mixed-case ASCII slug", contract)
        self.assertIn("string shorthand", contract)

    def test_brief_style_uppercase_keys_reconcile_without_duplication(self):
        plan = sample_plan()
        plan["issues"][0]["key"] = "T0"
        plan["issues"][1]["key"] = "T1"
        plan["issues"][1]["dependsOn"] = ["T0"]
        marker = "<!-- workcell-planner planId=planner-v3 issue=T0 -->"
        snapshot = {
            "milestones": [{
                "number": 7,
                "title": plan["planName"],
                "description": "<!-- workcell-planner planId=planner-v3 -->",
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
        marker = "<!-- workcell-planner planId=planner-v3 issue=render -->"
        snapshot = {
            "milestones": [
                {
                    "number": 7,
                    "title": "Old title",
                    "description": "<!-- workcell-planner planId=planner-v3 -->",
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
                    "body": "Gone\n\n<!-- workcell-planner planId=planner-v3 issue=removed -->",
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

    def test_risks_are_required_and_validated(self):
        for mutate, message in (
            (lambda plan: plan.pop("risks"), "missing field"),
            (lambda plan: plan["risks"][0].update({"likelihood": 4}), "must be 1, 2, or 3"),
            (lambda plan: plan["risks"][0].update({"impact": 0}), "must be 1, 2, or 3"),
            (lambda plan: plan["risks"].append(dict(plan["risks"][0])), "duplicate risk id"),
            (lambda plan: plan["risks"][0].update({"id": "bad id"}), "stable ascii slug"),
        ):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                plan = sample_plan()
                mutate(plan)
                sidecar = Path(tmp) / "plan.sidecar.json"
                output = Path(tmp) / "plan.html"
                sidecar.write_text(json.dumps(plan), encoding="utf-8")
                result = self.run_script(RENDER, sidecar, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(message, result.stderr.lower())

    def test_empty_risks_render_an_explicit_empty_state(self):
        plan = sample_plan()
        plan["risks"] = []
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            output = Path(tmp) / "plan.html"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            result = self.run_script(RENDER, sidecar, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = output.read_text(encoding="utf-8")
        self.assertIn("No risks recorded for this plan.", rendered)

    def test_open_questions_are_not_a_sidecar_field_and_must_be_asked_first(self):
        """A plan carrying unanswered questions is not ready for approval, so the
        schema gives them nowhere to live and the skill says to ask instead."""
        plan = sample_plan()
        plan["openQuestions"] = [{"id": "Q-01", "text": "Who signs?", "blocking": True}]
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            output = Path(tmp) / "plan.html"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            result = self.run_script(RENDER, sidecar, output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown field", result.stderr.lower())
        self.assertIn("openquestions", result.stderr.lower())

        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Resolve open questions with the human before writing the plan", skill)
        self.assertNotIn("openQuestions", skill)

    def test_risks_are_plotted_on_the_matrix_at_their_likelihood_impact_cell(self):
        plan = sample_plan()
        plan["risks"] = [
            {"id": "R-hi", "title": "Top band", "likelihood": 3, "impact": 3,
             "owner": "planner", "mitigation": "Mitigate."},
            {"id": "R-lo", "title": "Bottom band", "likelihood": 1, "impact": 1,
             "owner": "planner", "mitigation": "Mitigate."},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            output = Path(tmp) / "plan.html"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            result = self.run_script(RENDER, sidecar, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = output.read_text(encoding="utf-8")
        self.assertIn('<div class="cell s9"><span class="pin">R-hi</span></div>', rendered)
        self.assertIn('<div class="cell s1"><span class="pin">R-lo</span></div>', rendered)

    def test_folio_lands_in_docs_plans_with_the_numbered_name(self):
        plan = sample_plan()
        plan["planName"] = "Ship the Offline Plan Folio!"
        plan["generatedAt"] = "2026-08-26T12:00:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            plans = Path(tmp) / "docs" / "plans"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            result = self.run_script(RENDER, sidecar, "--plans-dir", plans)
            self.assertEqual(result.returncode, 0, result.stderr)
            written = sorted(plans.glob("*.html"))
            self.assertEqual([p.name for p in written], ["plan01-20260826-ship-the-offline-plan-folio.html"])

    def test_rerendering_a_plan_reuses_its_number_and_a_new_plan_takes_the_next(self):
        """Numbers are allocated per planId, not per render: revising a plan must
        overwrite its own folio, never scatter plan02/plan03 copies of the same plan."""
        first = sample_plan()
        with tempfile.TemporaryDirectory() as tmp:
            plans = Path(tmp) / "docs" / "plans"
            sidecar = Path(tmp) / "plan.sidecar.json"

            sidecar.write_text(json.dumps(first), encoding="utf-8")
            self.assertEqual(self.run_script(RENDER, sidecar, "--plans-dir", plans).returncode, 0)

            first["summary"] = "A revised summary for the very same plan."
            sidecar.write_text(json.dumps(first), encoding="utf-8")
            self.assertEqual(self.run_script(RENDER, sidecar, "--plans-dir", plans).returncode, 0)
            self.assertEqual(len(list(plans.glob("*.html"))), 1, "re-render claimed a new number")
            self.assertIn("A revised summary", next(plans.glob("*.html")).read_text(encoding="utf-8"))

            second = sample_plan()
            second["planId"] = "a-second-plan"
            second["planName"] = "A Second Plan"
            second["generatedAt"] = "2026-09-02T09:00:00Z"
            other = Path(tmp) / "second.sidecar.json"
            other.write_text(json.dumps(second), encoding="utf-8")
            self.assertEqual(self.run_script(RENDER, other, "--plans-dir", plans).returncode, 0)

            names = sorted(p.name for p in plans.glob("*.html"))
        self.assertEqual(names, [
            "plan01-20260826-planner-v3.html",
            "plan02-20260902-a-second-plan.html",
        ])

    def test_explicit_output_path_still_overrides_the_convention(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            output = Path(tmp) / "scratch" / "somewhere-else.html"
            sidecar.write_text(json.dumps(sample_plan()), encoding="utf-8")
            result = self.run_script(RENDER, sidecar, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.exists())
            self.assertFalse((Path(tmp) / "docs").exists())

    def test_padded_ids_round_trip(self):
        """A padded planId or key must never leak into markers, and a second
        reconcile against the first run's payloads must be a no-op."""
        plan = sample_plan()
        plan["planId"] = " x "
        plan["issues"][0]["key"] = "k "
        plan["issues"][1]["dependsOn"] = [" k"]
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            result = self.run_script(RENDER, sidecar, Path(tmp) / "out.html")
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = (Path(tmp) / "out.html").read_text(encoding="utf-8")
            self.assertIn("<!-- workcell-planner planId=x -->", rendered)
            self.assertNotIn("planId= x", rendered)
            state = Path(tmp) / "snapshot.json"
            state.write_text(json.dumps({"milestones": [], "issues": []}), encoding="utf-8")
            first = self.run_script(RECONCILE, sidecar, "--snapshot", state)
            self.assertEqual(first.returncode, 0, first.stderr)
            actions = json.loads(first.stdout)["actions"]
            created = [a for a in actions if a["action"] == "create_issue"]
            self.assertEqual({a["key"] for a in created}, {"k", "sync"})
            for action in created:
                self.assertIn(f'<!-- workcell-planner planId=x issue={action["key"]} -->', action["payload"]["body"])
            snapshot = {
                "milestones": [{"number": 1, "title": plan["planName"], "description": "<!-- workcell-planner planId=x -->", "state": "open"}],
                "issues": [
                    {
                        "number": 10 + i, "title": a["payload"]["title"], "body": a["payload"]["body"],
                        "labels": [{"name": n} for n in a["payload"]["labels"]],
                        "milestone": {"number": 1}, "state": "open",
                    }
                    for i, a in enumerate(created)
                ],
            }
            state.write_text(json.dumps(snapshot), encoding="utf-8")
            second = self.run_script(RECONCILE, sidecar, "--snapshot", state)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(json.loads(second.stdout)["actions"], [])

    def test_token_in_user_text_is_inert(self):
        plan = sample_plan()
        plan["summary"] = "Beware {{MERMAID_JS}} and {{ISSUE_CARDS}} in prose."
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            result = self.run_script(RENDER, sidecar, Path(tmp) / "out.html")
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = (Path(tmp) / "out.html").read_text(encoding="utf-8")
        self.assertIn("Beware {{MERMAID_JS}} and {{ISSUE_CARDS}} in prose.", rendered)
        bundle_head = (ROOT / "assets" / "mermaid.min.js").read_text(encoding="utf-8")[:200]
        self.assertEqual(rendered.count(bundle_head), 1)
        self.assertEqual(rendered.count('class="issue-key"'), len(plan["issues"]))

    def test_mermaid_label_neutralises_directive_and_markup_characters(self):
        sys.path.insert(0, SCRIPTS_DIR)
        import render_plan

        label = render_plan.mermaid_label('a#b;c`d<e>f"g[h]\ni')
        for char in '#;`<>"[]\n':
            self.assertNotIn(char, label)
        self.assertIn("a", label)
        self.assertIn("i", label)

    def test_reconcile_does_not_reopen_done_issues_unless_asked(self):
        plan = sample_plan()
        snapshot = {"milestones": [{"number": 7, "title": plan["planName"], "description": "<!-- workcell-planner planId=planner-v3 -->", "state": "open"}], "issues": []}
        first = reconcile_github.plan_actions(plan, snapshot)
        issues = []
        for i, action in enumerate(a for a in first if a["action"] == "create_issue"):
            issues.append({
                "number": 10 + i, "title": action["payload"]["title"], "body": action["payload"]["body"],
                "labels": [{"name": n} for n in action["payload"]["labels"]],
                "milestone": {"number": 7}, "state": "open",
            })
        issues[0]["state"] = "closed"
        issues[0]["labels"].append({"name": "status:done"})
        issues[1]["state"] = "closed"
        issues[1]["state_reason"] = "completed"
        snapshot["issues"] = issues

        self.assertEqual(reconcile_github.plan_actions(plan, snapshot), [])
        # A done canonical still gets its open duplicates closed, with a reason
        # that keeps the reconciler's own closures distinguishable from done work.
        duplicate = dict(issues[0], number=99, state="closed", state_reason=None, labels=[])
        duplicate["state"] = "open"
        with_duplicate = reconcile_github.plan_actions(plan, dict(snapshot, issues=issues + [duplicate]))
        self.assertEqual([(a["action"], a["number"]) for a in with_duplicate], [("close_duplicate_issue", 99)])
        self.assertEqual(with_duplicate[0]["payload"], {"state": "closed", "state_reason": "not_planned"})
        reopened = reconcile_github.plan_actions(plan, snapshot, reopen_done=True)
        self.assertEqual([a["action"] for a in reopened], ["update_issue", "update_issue"])
        self.assertEqual({a["number"] for a in reopened}, {10, 11})
        self.assertTrue(all(a["payload"]["state"] == "open" for a in reopened))

        issues[0]["labels"] = [{"name": "planning"}]
        issues[0]["state_reason"] = "not_planned"
        plain = reconcile_github.plan_actions(plan, snapshot)
        self.assertEqual([(a["action"], a["number"]) for a in plain], [("update_issue", 10)])

        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            state = Path(tmp) / "snapshot.json"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            state.write_text(json.dumps(snapshot), encoding="utf-8")
            result = self.run_script(RECONCILE, sidecar, "--snapshot", state, "--reopen-done")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["actions"]), 2)

    def test_milestone_adoption_by_title_preserves_description(self):
        plan = sample_plan()
        snapshot = {
            "milestones": [{"number": 3, "title": plan["planName"], "description": "Hand-written goals.", "state": "open"}],
            "issues": [],
        }
        actions = reconcile_github.plan_actions(plan, snapshot)
        update = next(a for a in actions if a["action"] == "update_milestone")
        self.assertEqual(update["number"], 3)
        self.assertTrue(update["payload"]["description"].startswith("Hand-written goals."))
        self.assertTrue(update["payload"]["description"].endswith("<!-- workcell-planner planId=planner-v3 -->"))
        snapshot["milestones"][0]["description"] = update["payload"]["description"]
        self.assertFalse(any(a["action"] == "update_milestone" for a in reconcile_github.plan_actions(plan, snapshot)))

    def test_trailing_marker_wins_over_an_embedded_one(self):
        genuine = reconcile_github.ISSUE_MARKER.format(plan_id="planner-v3", key="render")
        forged = "<!-- workcell-planner planId=planner-v3 issue=forged -->"
        body = "\n".join([
            "Render the approved design.", "", "The reviewed diff quotes a fixture line:",
            "", f"    {forged}", "", genuine,
        ])
        self.assertEqual(
            reconcile_github.issue_marker({"body": body}),
            ("planner-v3", "render"),
        )

    def test_unchanged_plan_is_still_a_no_op(self):
        cases = {
            "plain": "Render the approved design.",
            "quotes-a-marker": (
                "Render the approved design.\n\nThe fixture already contains "
                "<!-- workcell-planner planId=planner-v3 issue=forged --> verbatim."
            ),
        }
        for label, issue_body in cases.items():
            with self.subTest(body=label), tempfile.TemporaryDirectory() as tmp:
                plan = sample_plan()
                plan["issues"][0]["body"] = issue_body
                sidecar = Path(tmp) / "plan.sidecar.json"
                sidecar.write_text(json.dumps(plan), encoding="utf-8")
                state = Path(tmp) / "snapshot.json"
                state.write_text(json.dumps({"milestones": [], "issues": []}), encoding="utf-8")
                first = self.run_script(RECONCILE, sidecar, "--snapshot", state)
                self.assertEqual(first.returncode, 0, first.stderr)
                created = [a for a in json.loads(first.stdout)["actions"] if a["action"] == "create_issue"]
                landed = {
                    "milestones": [{
                        "number": 1, "title": plan["planName"],
                        "description": "<!-- workcell-planner planId=planner-v3 -->", "state": "open",
                    }],
                    "issues": [{
                        "number": 10 + index,
                        "title": action["payload"]["title"],
                        "body": action["payload"]["body"],
                        "labels": [{"name": name} for name in action["payload"]["labels"]],
                        "milestone": {"number": 1}, "state": "open",
                    } for index, action in enumerate(created)],
                }
                state.write_text(json.dumps(landed), encoding="utf-8")
                second = self.run_script(RECONCILE, sidecar, "--snapshot", state)
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertEqual(json.loads(second.stdout)["actions"], [])

    def approval_command(self, tool, source, approved_by):
        if tool == RECONCILE_FINDINGS:
            return [
                sys.executable, "-B", str(tool), str(source),
                "--repo", STUB_REPO, "--review-id", "pr-4821", "--subject", "PR #4821",
                "--apply", "--approved-by", approved_by,
            ]
        return [sys.executable, "-B", str(tool), str(source), "--apply", "--approved-by", approved_by]

    def approval_sources(self, directory):
        plan = sample_plan()
        plan["repo"] = STUB_REPO
        sidecar = Path(directory) / "plan.sidecar.json"
        sidecar.write_text(json.dumps(plan), encoding="utf-8")
        return ((RECONCILE, sidecar), (RECONCILE_FINDINGS, REVIEW_EXAMPLE))

    def test_approved_by_must_match_the_authenticated_login(self):
        with tempfile.TemporaryDirectory() as shared:
            for tool, source in self.approval_sources(shared):
                with self.subTest(tool=tool.name), tempfile.TemporaryDirectory() as tmp:
                    environment, log = gh_stub(tmp)
                    mismatch = subprocess.run(
                        self.approval_command(tool, source, "the human"),
                        cwd=tool.parent, env=environment, text=True, capture_output=True, check=False,
                    )
                    self.assertNotEqual(mismatch.returncode, 0)
                    self.assertIn("the human", mismatch.stderr)
                    self.assertIn(STUB_LOGIN, mismatch.stderr)
                    self.assertEqual(writes_attempted(log), [])
                    environment, log = gh_stub(tmp)
                    accepted = subprocess.run(
                        self.approval_command(tool, source, STUB_LOGIN),
                        cwd=tool.parent, env=environment, text=True, capture_output=True, check=False,
                    )
                    self.assertEqual(accepted.returncode, 0, accepted.stderr)
                    self.assertEqual(json.loads(accepted.stdout)["approvedBy"], STUB_LOGIN)
                    self.assertTrue(writes_attempted(log))

    def test_receipt_pins_the_approved_file_digest(self):
        with tempfile.TemporaryDirectory() as shared:
            for tool, source in self.approval_sources(shared):
                with self.subTest(tool=tool.name), tempfile.TemporaryDirectory() as tmp:
                    environment, _ = gh_stub(tmp)
                    result = subprocess.run(
                        self.approval_command(tool, source, STUB_LOGIN),
                        cwd=tool.parent, env=environment, text=True, capture_output=True, check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    output = json.loads(result.stdout)
                    digest = hashlib.sha256(source.read_bytes()).hexdigest()
                    carrying = [key for key, value in output.items() if value == digest]
                    self.assertTrue(carrying)
                    self.assertTrue(any(re.search(r"digest|sha256", key, re.IGNORECASE) for key in carrying))

    def test_skill_documents_reopen_done_and_marker_normalisation(self):
        text = (ROOT / "references" / "sidecar-contract.md").read_text(encoding="utf-8")
        self.assertIn("--reopen-done", text)
        self.assertIn("status:done", text)

    def test_planner_contract_split(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        contract_path = ROOT / "references" / "sidecar-contract.md"
        self.assertTrue(contract_path.exists())
        contract = contract_path.read_text(encoding="utf-8")
        self.assertIn("references/sidecar-contract.md", skill)
        self.assertNotIn("```json", skill)
        for field in (
            '"planId"', '"planName"', '"repo"', '"generatedAt"', '"summary"',
            '"architecture"', '"issues"', '"risks"',
        ):
            self.assertIn(field, contract)

    def test_planner_renderer_detail_is_progressively_disclosed(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        rendering = (ROOT / "references" / "report-rendering.md").read_text(encoding="utf-8")
        self.assertNotIn("byte-identical", skill)
        self.assertIn("references/report-rendering.md", skill)
        self.assertIn("byte-identical", rendering)
        self.assertIn("fixed folio section order", rendering)

    def test_shared_report_css_is_byte_identical_across_skills(self):
        repo_root = ROOT.parents[1]
        planner = (repo_root / "skills" / "planner" / "templates" / "report.css").read_bytes()
        for skill in ("code-review", "research"):
            other = (repo_root / "skills" / skill / "templates" / "report.css").read_bytes()
            self.assertEqual(
                planner, other,
                f"report.css must stay byte-identical in skills/planner and skills/{skill}",
            )

    def test_skill_requires_approval_and_documents_milestones_only(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\nname: planner\n"))
        self.assertIn("human approval", skill.lower())
        self.assertIn("must stop", skill.lower())
        self.assertIn("GitHub milestone", skill)
        self.assertIn("Use milestones only; never create or modify a GitHub Project", skill)
        self.assertIn("--apply", skill)


    @patch("reconcile_github.subprocess.run")
    def test_reconcile_gh_timeout(self, mock_run):
        # mock subprocess.run to raise subprocess.TimeoutExpired
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["gh", "api"], timeout=30)
        with self.assertRaises(Exception) as ctx:
            reconcile_github.gh_json(["repos/foo/milestones"])
        # Verify that it raised ReconcileError
        self.assertEqual(ctx.exception.__class__.__name__, "ReconcileError")
        self.assertIn("timed out", str(ctx.exception))

    def test_skill_doc_relative_paths(self):
        import re
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[3]
        skill_files = list(repo_root.glob("skills/*/SKILL.md"))
        self.assertGreater(len(skill_files), 0, "No SKILL.md files found")
        
        script_pattern = re.compile(r"\b(?:skills/[\w-]+/)?scripts/[\w.-]+\.py\b")
        
        for skill_file in skill_files:
            content = skill_file.read_text(encoding="utf-8")
            matches = script_pattern.findall(content)
            for match in matches:
                # Every match must start with "skills/" to be explicit repo-relative
                self.assertTrue(match.startswith("skills/"), f"Script path {match!r} in {skill_file.relative_to(repo_root)} is not an explicit repo-relative path starting with 'skills/\'")
                # And the file must exist
                full_path = repo_root / match
                self.assertTrue(full_path.exists(), f"Script path {match!r} in {skill_file.relative_to(repo_root)} does not exist on disk")


    # --- ownershipHint granularity contract (issue #99) ---------------------------------------

    def test_prose_ownership_hint_is_rejected(self):
        prose = "templates/** and scripts/render_plan.py"
        plan = sample_plan()
        plan["issues"][0]["ownershipHint"] = prose
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            output = Path(tmp) / "plan.html"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            result = self.run_script(RENDER, sidecar, output)
            self.assertNotEqual(
                result.returncode, 0,
                "a prose ownershipHint naming two paths must be rejected, not rendered",
            )
            self.assertFalse(output.exists(), "a rejected sidecar must not leave a folio behind")
        stderr = result.stderr.lower()
        self.assertIn("issues[0].ownershiphint", stderr, "the error must name the offending issue index and field")
        self.assertIn(prose.lower(), stderr, "the error must quote the offending value")
        self.assertIn("one path or glob", stderr, "the error must say the field takes one path or glob")

    def test_comma_or_space_separated_hints_are_rejected(self):
        for hint in ("a/**, b/**", "a/** b/**"):
            with self.subTest(hint=hint), tempfile.TemporaryDirectory() as tmp:
                plan = sample_plan()
                plan["issues"][1]["ownershipHint"] = hint
                sidecar = Path(tmp) / "plan.sidecar.json"
                output = Path(tmp) / "plan.html"
                sidecar.write_text(json.dumps(plan), encoding="utf-8")
                result = self.run_script(RENDER, sidecar, output)
                stderr = result.stderr.lower()
                self.assertNotEqual(result.returncode, 0, f"{hint!r} is two globs, not one")
                self.assertIn("issues[1].ownershiphint", stderr)
                self.assertIn(hint.lower(), stderr)
                self.assertIn(
                    "one path or glob", stderr,
                    "comma- and space-separated hints must fail through the same validation path",
                )

        padded = "  skills/build/scripts/**  "
        plan = sample_plan()
        plan["issues"][1]["ownershipHint"] = padded
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            output = Path(tmp) / "plan.html"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            result = self.run_script(RENDER, sidecar, output)
            rendered = output.read_text(encoding="utf-8") if output.exists() else ""
        if result.returncode == 0:
            self.assertFalse(
                padded in rendered,
                f"the padded hint {padded!r} must be stripped before it reaches the folio",
            )
            ownership_cells = re.findall(r'<td class="mono">([^<]*)</td></tr>', rendered)
            self.assertIn(padded.strip(), ownership_cells)
            for cell in ownership_cells:
                self.assertEqual(cell, cell.strip(), "the folio must not carry a padded ownership hint")
        else:
            self.assertIn("issues[1].ownershiphint", result.stderr.lower())

    def test_single_glob_hints_still_render(self):
        hints = ("skills/build/scripts/**", "docs/adr/**")
        plan = sample_plan()
        plan["issues"][0]["ownershipHint"] = hints[0]
        plan["issues"][1]["ownershipHint"] = hints[1]
        with tempfile.TemporaryDirectory() as tmp:
            sidecar = Path(tmp) / "plan.sidecar.json"
            output = Path(tmp) / "plan.html"
            sidecar.write_text(json.dumps(plan), encoding="utf-8")
            result = self.run_script(RENDER, sidecar, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = output.read_text(encoding="utf-8")
        ownership_cells = re.findall(r'<td class="mono">([^<]*)</td></tr>', rendered)
        for hint in hints:
            self.assertIn(hint, ownership_cells, "a single-glob hint must appear in the folio issue table")

    def test_shipped_sample_sidecar_passes_the_rule(self):
        sample = ROOT / "examples" / "sample.sidecar.json"
        plan = json.loads(sample.read_text(encoding="utf-8"))
        for index, issue in enumerate(plan["issues"]):
            hint = issue["ownershipHint"]
            where = f"issues[{index}].ownershipHint"
            self.assertNotIn(",", hint, f"{where} is a comma list, not one path or glob: {hint!r}")
            self.assertEqual(
                hint.split(), [hint],
                f"{where} contains whitespace, so it is not one path or glob: {hint!r}",
            )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "sample.html"
            result = self.run_script(RENDER, sample, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.exists(), "the shipped sample sidecar must render")

    def test_contract_states_the_granularity_rule(self):
        contract = (ROOT / "references" / "sidecar-contract.md").read_text(encoding="utf-8")
        lowered = contract.lower()
        for phrase, rule in (
            ("exactly one path or glob", "the hint is exactly one path or glob, never prose or a list"),
            ("narrowest glob", "the hint is the narrowest glob covering every file the issue changes"),
            ("the tests the specifier will write", "the hint also covers the tests the specifier will write"),
            ("disjoint", "hints are disjoint within a wave"),
            ("split the issue", "an issue spanning unrelated subtrees is split rather than widened"),
        ):
            self.assertIn(phrase, lowered, f"sidecar-contract.md must state that {rule}")
        for token in ("skills/build/scripts/**", "skills/**", "*.md"):
            self.assertIn(
                token, contract,
                "sidecar-contract.md must give the worked narrow-versus-coarse ownershipHint contrasts",
            )

if __name__ == "__main__":
    unittest.main()
