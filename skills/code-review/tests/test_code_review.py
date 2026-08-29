import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "merge_findings.py"
RENDER = ROOT / "scripts" / "render_review.py"
RECONCILE = ROOT / "scripts" / "reconcile_findings.py"
EXAMPLES = ROOT / "examples"
AGENT = ROOT.parents[1] / "agents" / "claude" / "code-reviewer.md"


def run_script(script, *args):
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-B", str(script), *map(str, args)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
    )


def run_helper(*args):
    return run_script(SCRIPT, *args)


def run_render(*args):
    return run_script(RENDER, *args)


def run_reconcile(*args):
    return run_script(RECONCILE, *args)


def snapshot_from(actions):
    """Simulate GitHub after the given create actions landed."""
    return {"issues": [
        {
            "number": 100 + index,
            "title": action["payload"]["title"],
            "body": action["payload"]["body"],
            "labels": [{"name": name} for name in action["payload"]["labels"]],
            "milestone": None,
            "state": "open",
        }
        for index, action in enumerate(actions)
    ]}


class CodeReviewSkillTests(unittest.TestCase):
    def test_agent_requires_exact_no_prose_envelope_and_empty_findings_form(self):
        agent = AGENT.read_text(encoding="utf-8")
        self.assertIn("Return exactly one JSON object and no prose", agent)
        examples = re.findall(r"```json\n(.*?)\n```", agent, flags=re.DOTALL)
        envelope = json.loads(examples[0])
        empty = json.loads(examples[1])
        self.assertEqual(set(envelope), {"lens", "findings"})
        self.assertEqual(envelope["lens"], envelope["findings"][0]["lens"])
        self.assertEqual(empty, {"lens": "tests", "findings": []})

    def test_equal_strength_duplicate_selection_is_permutation_invariant(self):
        correctness = {
            "lens": "correctness",
            "findings": [{
                "file": "src/tie.py", "line": 8, "severity": "medium", "lens": "correctness",
                "claim": "Shared claim", "failureScenario": "Correctness scenario.", "confidence": 0.8,
            }],
        }
        tests = {
            "lens": "tests",
            "findings": [{
                "file": "src/tie.py", "line": 8, "severity": "medium", "lens": "tests",
                "claim": "Shared claim", "failureScenario": "Tests scenario.", "confidence": 0.8,
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "correctness.json"
            second = Path(tmp) / "tests.json"
            first.write_text(json.dumps(correctness), encoding="utf-8")
            second.write_text(json.dumps(tests), encoding="utf-8")
            forward = run_helper("--dedupe-only", first, second)
            reverse = run_helper("--dedupe-only", second, first)
        self.assertEqual(forward.returncode, 0, forward.stderr)
        self.assertEqual(reverse.returncode, 0, reverse.stderr)
        self.assertEqual(forward.stdout, reverse.stdout)
        candidate = json.loads(forward.stdout)["candidates"][0]
        self.assertEqual(candidate["lens"], "correctness")
        self.assertEqual(candidate["failureScenario"], "Correctness scenario.")

    def test_example_dry_run_is_deterministic_and_matches_expected_report(self):
        arguments = [
            "--verification", EXAMPLES / "verification.json",
            EXAMPLES / "correctness.json", EXAMPLES / "tests.json",
            EXAMPLES / "security.json",
        ]
        expected = json.loads((EXAMPLES / "expected-review.json").read_text(encoding="utf-8"))
        first = run_helper(*arguments)
        second = run_helper(*arguments)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(json.loads(first.stdout), expected)
        self.assertEqual(expected["verdict"], "block")
        self.assertEqual(expected["candidateCount"], 3)
        self.assertEqual(expected["droppedCount"], 1)
        self.assertEqual([finding["severity"] for finding in expected["findings"]], ["high", "low"])
        self.assertEqual(len(expected["dropped"]), 1)
        dropped = expected["dropped"][0]
        self.assertEqual(dropped["claim"], "Cache key omits tenant identity")
        self.assertIn("prefixes the tenant id", dropped["verification"]["evidence"])

    def test_dedupe_only_uses_tuple_key_and_strongest_representative(self):
        result = run_helper(
            "--dedupe-only",
            EXAMPLES / "correctness.json", EXAMPLES / "tests.json", EXAMPLES / "security.json",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["candidateCount"], 3)
        duplicate = next(
            finding for finding in output["candidates"]
            if finding["claim"] == "Empty tokens bypass authentication"
        )
        self.assertEqual(duplicate["lens"], "security")
        self.assertEqual(duplicate["severity"], "high")
        self.assertEqual(duplicate["confidence"], 0.97)

    def test_requires_exactly_one_adversarial_verification_per_candidate(self):
        verification = json.loads((EXAMPLES / "verification.json").read_text(encoding="utf-8"))
        verification["verifications"].pop()
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"
            missing.write_text(json.dumps(verification), encoding="utf-8")
            result = run_helper(
                "--verification", missing,
                EXAMPLES / "correctness.json", EXAMPLES / "tests.json", EXAMPLES / "security.json",
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing adversarial verification", result.stderr.lower())

        verification = json.loads((EXAMPLES / "verification.json").read_text(encoding="utf-8"))
        verification["verifications"].append(dict(verification["verifications"][0]))
        with tempfile.TemporaryDirectory() as tmp:
            duplicate = Path(tmp) / "duplicate.json"
            duplicate.write_text(json.dumps(verification), encoding="utf-8")
            result = run_helper(
                "--verification", duplicate,
                EXAMPLES / "correctness.json", EXAMPLES / "tests.json", EXAMPLES / "security.json",
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate adversarial verification", result.stderr.lower())

    def test_rejects_unknown_fields_lens_mismatch_and_unsafe_paths(self):
        source = json.loads((EXAMPLES / "correctness.json").read_text(encoding="utf-8"))
        cases = (
            (lambda value: value.update({"unexpected": True}), "unknown field"),
            (lambda value: value["findings"][0].update({"lens": "tests"}), "must match envelope lens"),
            (lambda value: value["findings"][0].update({"file": "../escape.py"}), "relative repository path"),
        )
        for mutate, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                invalid_source = json.loads(json.dumps(source))
                mutate(invalid_source)
                invalid = Path(tmp) / "invalid.json"
                invalid.write_text(json.dumps(invalid_source), encoding="utf-8")
                result = run_helper("--dedupe-only", invalid)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(message, result.stderr.lower())

    def test_verdict_thresholds_and_severity_order_are_deterministic(self):
        findings = {
            "lens": "correctness",
            "findings": [
                {
                    "file": "src/a.py", "line": 4, "severity": "nit", "lens": "correctness",
                    "claim": "Name is misleading", "failureScenario": "A maintainer reads the inverse meaning.",
                    "confidence": 0.8,
                },
                {
                    "file": "src/a.py", "line": 2, "severity": "medium", "lens": "correctness",
                    "claim": "Retry is skipped", "failureScenario": "A timeout returns immediately instead of retrying.",
                    "confidence": 0.9,
                },
            ],
        }
        verification = {
            "verifications": [
                {
                    "file": item["file"], "line": item["line"], "claim": item["claim"],
                    "substantiated": True, "refutationAttempt": "Tried the opposite control-flow branch.",
                    "evidence": "The branch remains reachable with the stated input.",
                }
                for item in findings["findings"]
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "findings.json"
            verified = Path(tmp) / "verification.json"
            source.write_text(json.dumps(findings), encoding="utf-8")
            verified.write_text(json.dumps(verification), encoding="utf-8")
            result = run_helper("--verification", verified, source)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["verdict"], "approve-with-nits")
        self.assertEqual([finding["severity"] for finding in output["findings"]], ["medium", "nit"])

    def test_empty_verified_report_is_approved(self):
        source = {"lens": "tests", "findings": []}
        verification = {"verifications": []}
        with tempfile.TemporaryDirectory() as tmp:
            findings_path = Path(tmp) / "findings.json"
            verification_path = Path(tmp) / "verification.json"
            findings_path.write_text(json.dumps(source), encoding="utf-8")
            verification_path.write_text(json.dumps(verification), encoding="utf-8")
            result = run_helper("--verification", verification_path, findings_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["verdict"], "approve")

    def test_render_is_self_contained_and_carries_every_verified_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "review.html"
            result = run_render(
                EXAMPLES / "expected-review.json", output,
                "--title", "Empty-token auth bypass",
                "--repo", "acme/platform", "--subject", "PR #4821",
                "--base", "a91f3c2", "--lenses", "correctness,tests,security",
                "--generated-at", "2026-08-28T06:40:00Z",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = output.read_text(encoding="utf-8")

        self.assertNotIn("https://", rendered)
        self.assertNotIn("<link rel=", rendered)
        for token in (
            '[data-theme="light"]', "--sev-nit:", "@media print",
            "prefers-reduced-motion", "@media (max-width: 900px)",
        ):
            self.assertIn(token, rendered)

        expected = json.loads((EXAMPLES / "expected-review.json").read_text(encoding="utf-8"))
        for finding in expected["findings"]:
            self.assertIn(finding["claim"], rendered)
            self.assertIn(finding["failureScenario"], rendered)
            self.assertIn(finding["verification"]["evidence"], rendered)
            self.assertIn(f'data-severity="{finding["severity"]}"', rendered)
            self.assertIn(f'data-lens="{finding["lens"]}"', rendered)
        for finding in expected["dropped"]:
            self.assertIn(finding["claim"], rendered)
            self.assertIn(finding["verification"]["evidence"], rendered)

        headings = [
            "Summary", "Findings", "Touched Files", "Refuted Candidates", "Method",
        ]
        positions = [rendered.index(f">{heading}</h2>") for heading in headings]
        self.assertEqual(positions, sorted(positions))

        for visual in ('aria-labelledby="topology-title"', 'aria-labelledby="impact-title"'):
            self.assertIn(visual, rendered)
        self.assertIn("Review topology", rendered)
        self.assertIn("Verified impact map", rendered)
        self.assertIn("after deterministic dedupe", rendered)
        self.assertIn("impact-mark bar-high", rendered)

    def test_zero_finding_report_keeps_accessible_topology_and_impact_visuals(self):
        review = {
            "inputCount": 0, "candidateCount": 0, "verifiedCount": 0, "droppedCount": 0,
            "findings": [], "dropped": [], "verdict": "approve",
        }
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "review.json"
            output = Path(tmp) / "review.html"
            source.write_text(json.dumps(review), encoding="utf-8")
            result = run_render(
                source, output, "--lenses", "correctness,tests",
                "--generated-at", "2026-08-28T06:40:00Z",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = output.read_text(encoding="utf-8")
        self.assertIn("2 selected lenses produced 0 observations", rendered)
        self.assertIn("No verified impact", rendered)
        self.assertIn("No files carry verified findings.", rendered)
        self.assertIn("The verdict is approve.", rendered)

    def test_render_is_deterministic_for_the_same_input(self):
        arguments = ["--repo", "acme/platform", "--generated-at", "2026-08-28T06:40:00Z"]
        outputs = []
        for run in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "review.html"
                result = run_render(EXAMPLES / "expected-review.json", output, *arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                outputs.append(output.read_text(encoding="utf-8"))
        self.assertEqual(outputs[0], outputs[1])

    def test_render_verdict_class_tracks_the_verdict(self):
        review = json.loads((EXAMPLES / "expected-review.json").read_text(encoding="utf-8"))
        cases = {"block": "verdict-block", "approve-with-nits": "verdict-nits", "approve": "verdict-approve"}
        for verdict, css_class in cases.items():
            payload = json.loads(json.dumps(review))
            payload["verdict"] = verdict
            if verdict == "approve":
                payload["findings"] = []
                payload["verifiedCount"] = 0
            with self.subTest(verdict=verdict), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / "review.json"
                output = Path(tmp) / "review.html"
                source.write_text(json.dumps(payload), encoding="utf-8")
                result = run_render(source, output, "--generated-at", "2026-08-28T06:40:00Z")
                self.assertEqual(result.returncode, 0, result.stderr)
                rendered = output.read_text(encoding="utf-8")
            self.assertIn(css_class, rendered)

    def test_render_rejects_input_that_did_not_come_from_the_pipeline(self):
        review = json.loads((EXAMPLES / "expected-review.json").read_text(encoding="utf-8"))
        cases = (
            (lambda value: value.update({"unexpected": True}), "unknown field"),
            (lambda value: value.pop("dropped"), "missing field"),
            (lambda value: value.update({"verdict": "lgtm"}), "verdict must be one of"),
            (lambda value: value.update({"verifiedCount": 9}), "verifiedcount does not match"),
            (lambda value: value["findings"][0].update({"severity": "blocker"}), "severity must be one of"),
            (lambda value: value["findings"][0].update({"lens": "style"}), "lens must be one of"),
            (lambda value: value["findings"][0]["verification"].pop("evidence"), "missing field"),
        )
        for mutate, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                payload = json.loads(json.dumps(review))
                mutate(payload)
                source = Path(tmp) / "review.json"
                output = Path(tmp) / "review.html"
                source.write_text(json.dumps(payload), encoding="utf-8")
                result = run_render(source, output, "--generated-at", "2026-08-28T06:40:00Z")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(message, result.stderr.lower())

    def test_render_confidence_meter_and_label_never_disagree(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import render_review

        for confidence in (0.0, 0.5, 0.71, 0.86, 0.97, 1.0):
            bars, label = render_review.confidence_band(confidence)
            self.assertEqual(render_review.meter_html(confidence).count('class="on"'), bars)
            self.assertEqual(render_review.confidence_label(confidence), label)
            self.assertGreaterEqual(bars, 1)
            self.assertLessEqual(bars, 4)

    def test_frontend_is_a_first_class_lens_end_to_end(self):
        """A frontend envelope must survive dedupe, verification, and render with no
        special-casing — that is the whole point of folding it into the pipeline."""
        source = {
            "lens": "frontend",
            "findings": [{
                "file": "src/components/Table.tsx", "line": 42, "severity": "high",
                "lens": "frontend", "claim": "Table overflows the viewport below 1280px",
                "failureScenario": "At 1280x800 the table forces 1418px of page scroll.",
                "confidence": 0.93,
            }],
        }
        verification = {"verifications": [{
            "file": "src/components/Table.tsx", "line": 42,
            "claim": "Table overflows the viewport below 1280px",
            "substantiated": True,
            "refutationAttempt": "Resized to every matrix row and measured scrollWidth against clientWidth.",
            "evidence": "scrollWidth 1418 exceeds clientWidth 1280 at laptop-sm; the last column is unreachable.",
        }]}
        with tempfile.TemporaryDirectory() as tmp:
            findings_path = Path(tmp) / "frontend.json"
            verification_path = Path(tmp) / "verification.json"
            review_path = Path(tmp) / "review.json"
            output = Path(tmp) / "review.html"
            findings_path.write_text(json.dumps(source), encoding="utf-8")
            verification_path.write_text(json.dumps(verification), encoding="utf-8")
            merged = run_helper("--verification", verification_path, findings_path)
            self.assertEqual(merged.returncode, 0, merged.stderr)
            review_path.write_text(merged.stdout, encoding="utf-8")
            rendered = run_render(review_path, output, "--generated-at", "2026-08-28T06:40:00Z")
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            html = output.read_text(encoding="utf-8")

        self.assertEqual(json.loads(merged.stdout)["verdict"], "block")
        self.assertIn('data-lens="frontend"', html)
        self.assertIn("Table overflows the viewport below 1280px", html)

    def test_frontend_lens_publishes_its_viewport_matrix_and_envelope(self):
        skill = (ROOT.parents[1] / "skills" / "code-reviewer-frontend-review" / "SKILL.md").read_text(encoding="utf-8")
        for viewport in (
            "3840 × 2160", "1920 × 2160", "2560 × 1440", "1920 × 1080",
            "1728 × 1117", "1512 × 982", "1440 × 900", "1280 × 800",
            "768 × 1024", "390 × 844",
        ):
            self.assertIn(viewport, skill, f"viewport matrix is missing {viewport}")
        for phrase in (
            "browser_resize", "browser_take_screenshot", "scrollWidth",
            '"lens": "frontend"', "never point at production", "no code changes",
        ):
            self.assertIn(phrase, skill)

        review = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "frontend applies when the change touches user-facing UI",
            "code-reviewer-frontend-review", "Playwright",
            "is not a frontend change",
        ):
            self.assertIn(phrase, review)

    def test_reconcile_files_issues_above_the_threshold_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.json"
            empty.write_text(json.dumps({"issues": []}), encoding="utf-8")
            result = run_reconcile(
                EXAMPLES / "expected-review.json", "--repo", "acme/platform",
                "--review-id", "pr-4821", "--subject", "PR #4821", "--snapshot", empty,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)

            low = run_reconcile(
                EXAMPLES / "expected-review.json", "--repo", "acme/platform",
                "--review-id", "pr-4821", "--min-severity", "low", "--snapshot", empty,
            )
            self.assertEqual(low.returncode, 0, low.stderr)

        # expected-review.json holds one high and one low finding.
        self.assertEqual(output["mode"], "preview")
        self.assertEqual([a["action"] for a in output["actions"]], ["create_issue"])
        payload = output["actions"][0]["payload"]
        self.assertEqual(payload["title"], "[high] Empty tokens bypass authentication")
        self.assertEqual(payload["labels"], ["code-review", "lens:security", "severity:high"])
        self.assertIn("Failure scenario", payload["body"])
        self.assertIn("Independent verification", payload["body"])
        self.assertIn("swarm-review reviewId=pr-4821 finding=", payload["body"])
        self.assertEqual(len(json.loads(low.stdout)["actions"]), 2)

    def test_reconcile_is_idempotent_and_closes_resolved_findings(self):
        """Re-running an unchanged review must be a no-op, and a finding that stops
        being reported must close its issue — otherwise the tracker only ever grows."""
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.json"
            empty.write_text(json.dumps({"issues": []}), encoding="utf-8")
            first = run_reconcile(
                EXAMPLES / "expected-review.json", "--repo", "acme/platform",
                "--review-id", "pr-4821", "--subject", "PR #4821", "--snapshot", empty,
            )
            self.assertEqual(first.returncode, 0, first.stderr)

            state = Path(tmp) / "state.json"
            state.write_text(json.dumps(snapshot_from(json.loads(first.stdout)["actions"])), encoding="utf-8")

            again = run_reconcile(
                EXAMPLES / "expected-review.json", "--repo", "acme/platform",
                "--review-id", "pr-4821", "--subject", "PR #4821", "--snapshot", state,
            )
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertEqual(json.loads(again.stdout)["actions"], [], "re-run was not idempotent")

            fixed = json.loads((EXAMPLES / "expected-review.json").read_text(encoding="utf-8"))
            fixed["findings"] = []
            fixed["verifiedCount"] = 0
            fixed["verdict"] = "approve"
            fixed_path = Path(tmp) / "fixed.json"
            fixed_path.write_text(json.dumps(fixed), encoding="utf-8")
            resolved = run_reconcile(
                fixed_path, "--repo", "acme/platform",
                "--review-id", "pr-4821", "--snapshot", state,
            )
            self.assertEqual(resolved.returncode, 0, resolved.stderr)

        actions = json.loads(resolved.stdout)["actions"]
        self.assertEqual([a["action"] for a in actions], ["close_resolved_issue"])
        self.assertEqual(actions[0]["payload"], {"state": "closed"})

    def test_finding_identity_survives_line_drift_but_not_a_different_claim(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import reconcile_findings

        base = {"file": "src/auth.py", "line": 42, "claim": "Empty tokens bypass authentication"}
        moved = dict(base, line=91)
        other_claim = dict(base, claim="Tokens are logged in plaintext")
        other_file = dict(base, file="src/session.py")

        self.assertEqual(reconcile_findings.finding_key(base), reconcile_findings.finding_key(moved))
        self.assertNotEqual(reconcile_findings.finding_key(base), reconcile_findings.finding_key(other_claim))
        self.assertNotEqual(reconcile_findings.finding_key(base), reconcile_findings.finding_key(other_file))

    def test_reconcile_apply_requires_an_approving_human(self):
        cases = (
            (["--apply"], "requires --approved-by"),
            (["--approved-by", "someone"], "only valid with --apply"),
            (["--apply", "--approved-by", "someone", "--snapshot", "x.json"], "cannot be combined"),
        )
        for extra, message in cases:
            with self.subTest(extra=extra):
                result = run_reconcile(
                    EXAMPLES / "expected-review.json", "--repo", "acme/platform",
                    "--review-id", "pr-4821", *extra,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr.lower())

        for bad, message in ((["--review-id", "PR 4821"], "stable lowercase slug"),
                             (["--review-id", "ok", "--repo", "not-a-repo"], "owner/name")):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as tmp:
                empty = Path(tmp) / "empty.json"
                empty.write_text(json.dumps({"issues": []}), encoding="utf-8")
                args = ["--repo", "acme/platform"] if "--repo" not in bad else []
                result = run_reconcile(
                    EXAMPLES / "expected-review.json", *args, *bad, "--snapshot", empty,
                )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(message, result.stderr.lower())

    def test_skill_documents_the_issue_approval_gate(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "reconcile_findings.py", "--review-id", "--approved-by",
            "Stop for explicit human approval", "swarm-review reviewId",
            "close_resolved_issue", "deliberately not the line",
            "Never run `--apply` merely to test the skill",
        ):
            self.assertIn(phrase, skill)

    def test_agent_and_skill_publish_required_role_and_orchestration_boundaries(self):
        agent = AGENT.read_text(encoding="utf-8")
        frontmatter = agent.split("---", 2)[1].strip().splitlines()
        self.assertEqual([line.split(":", 1)[0] for line in frontmatter], ["name", "description", "tools"])
        self.assertEqual(frontmatter[0], "name: code-reviewer")
        tools = [t.strip() for t in frontmatter[2].split(":", 1)[1].split(",")]
        self.assertEqual(tools[:5], ["Read", "Grep", "Glob", "Bash", "Skill"])
        for phrase in (
            "ONE review lens", "correctness | security | performance | tests | api-contract",
            "actively try to break or refute", "failureScenario", "confidence",
            "No edits, ever", "do not spawn", "overall completion",
        ):
            self.assertIn(phrase, agent)

        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\nname: code-review\n"))
        for phrase in (
            "correctness and tests are always selected", "trust boundaries", "hot paths",
            "public surface", "applicable lenses, never a fixed N", "in parallel",
            "(file, line, claim)", "independent adversarial", "tries to refute",
            "DROP", "block", "approve-with-nits", "approve", "sole synthesis",
        ):
            self.assertIn(phrase, skill)


if __name__ == "__main__":
    unittest.main()
