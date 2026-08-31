import json
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILLS = REPO / "skills"
WAVES = SKILLS / "build" / "scripts" / "waves.py"
DEMOS = (
    SKILLS / "build" / "examples",
    SKILLS / "build" / "examples" / "pull-forward",
)
CANONICAL_BOUNDARY = (
    "You are the orchestrator ([ADR 0007](../../docs/adr/"
    "0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents, hold the human "
    "gates, run `git` / `jj` / `gh` for branch, merge, and issue-state operations, and read "
    "gate output and handoff records. You never read or edit the target project's code, run "
    "its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch "
    "is orchestration; reading a file's contents to judge it is not."
)
ORCHESTRATION_SKILLS = (
    "build",
    "planner",
    "code-review",
    "research",
    "docs",
    "deploy",
    "new-feature",
    "code-analysis",
    "code-refactor",
    "debug",
    "perf",
    "repo-setup",
    "review-fix-loop",
)


def skill(name):
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


class SkillContractTests(unittest.TestCase):
    def test_orchestrator_boundary_is_canonical(self):
        retired = (
            "never the code",
            "not the contents of the files",
            "read the file list and the manifests",
            "Nothing here has you read the target project",
        )
        for name in ORCHESTRATION_SKILLS:
            with self.subTest(skill=name):
                text = skill(name)
                self.assertIn(CANONICAL_BOUNDARY, text)
                after_title = text.split("\n# ", 1)[1].split("\n\n", 1)[1]
                self.assertEqual(after_title.split("\n\n")[1], CANONICAL_BOUNDARY)
        for path in SKILLS.glob("*/SKILL.md"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(skill=path.parent.name, check="retired-paraphrases"):
                for phrase in retired:
                    self.assertNotIn(phrase, text)

    def test_build_defines_single_pr_mode(self):
        build = skill("build")
        self.assertIn("## Single-PR mode", build)
        for phrase in (
            "<planId>-integration",
            "agents/handoff.md",
            "`base`",
            "final PR from the integration branch to `main`",
        ):
            self.assertIn(phrase, build)
        for name in ("new-feature", "code-analysis", "code-refactor", "debug", "perf"):
            with self.subTest(skill=name):
                self.assertIn("single-PR mode", skill(name))

    def test_perf_uses_the_green_baseline_seal(self):
        text = skill("perf")
        for phrase in (
            "`mode: refactor`",
            "`mode: baseline`",
            "no `specifier`",
            "profiler baseline",
            "`baselineCommand`",
            "`sealedTests`",
            "`kind: baseline`",
            "same `tdd-guard` state machine",
            "Stop hook and `status --json` work unchanged",
        ):
            self.assertIn(phrase, text)

    def test_debug_specifies_the_no_issue_brief(self):
        text = skill("debug")
        for phrase in (
            "`issue: null`",
            "single acceptance test",
            "reproduction command",
            "names the symptom and the reproduction instead of `Closes #<n>`",
        ):
            self.assertIn(phrase, text)

    def test_modes_named_in_dispatch_steps(self):
        cases = {
            "code-refactor": ("`mode: refactor`", "`mode: baseline`"),
            "review-fix-loop": ("`mode: loop`",),
            "code-analysis": ("`mode: baseline`",),
            "repo-setup": ("`mode: baseline`",),
        }
        for name, phrases in cases.items():
            with self.subTest(skill=name):
                text = skill(name)
                self.assertIn("agents/handoff.md", text)
                for phrase in phrases:
                    self.assertIn(phrase, text)

    def test_reviewer_dev_server_is_a_brief_field(self):
        for name in ("code-review", "reviewer-frontend-review"):
            with self.subTest(skill=name):
                text = skill(name)
                self.assertIn("`devServer`", text)
                self.assertNotIn("ask before starting a dev server", text.lower())

    def test_build_done_definition_single_reading(self):
        text = skill("build")
        self.assertNotIn("without closing it yet", text)
        self.assertIn(
            "closed **and** (`status:done` or `state_reason == completed`)", text
        )
        self.assertIn("waves.py", text)

    def test_the_wave_loop_invariants_survive(self):
        """The wiki trace is an addition to `build`, not a rewrite of it.

        The edit has to be in the file for this to prove anything, so it is checked first;
        then everything the issue promised not to touch is checked in place — the one done
        definition, `waves.py` as the selector, single-PR mode, the speculative-specifier
        allowance, and `mode: refactor` — and both shipped offline demonstrations are run
        against their recorded expectations, because a selector that still *reads* right
        while selecting differently is the failure this guards.
        """
        build = skill("build")
        for landed in (
            "wiki.py record",
            "--kind build-wave",
            "wiki.py status --repo .",
        ):
            self.assertTrue(
                landed in build,
                f"the build-wave trace has not landed in skills/build/SKILL.md: {landed!r}",
            )

        for phrase in (
            # the one done definition, agreed with reconcile_github.py
            "closed **and** (`status:done` or `state_reason == completed`)",
            # the selector
            "skills/build/scripts/waves.py",
            "waves.py",
            # single-PR mode
            "## Single-PR mode",
            "<planId>-integration",
            "final PR from the integration branch to `main`",
            # the speculative-specifier allowance and its limits
            "Speculative specifiers",
            "Never a speculative builder",
            "tdd-guard reseal --reason",
            # the refactor mode
            "`mode: refactor`",
            "`mode: baseline`",
            # the gates the recording must not have softened
            "combined GREEN",
            "never dispatch a builder for an issue with no seal",
            "sole completion authority",
        ):
            # assertIn would dump the whole SKILL.md into the failure report.
            self.assertTrue(
                phrase in build, f"wave-loop invariant lost to the edit: {phrase!r}"
            )

        for demo in DEMOS:
            with self.subTest(demo=demo.name):
                run = subprocess.run(
                    [
                        "python3",
                        "-B",
                        str(WAVES),
                        str(demo / "plan.sidecar.json"),
                        str(demo / "issue-state.json"),
                    ],
                    cwd=REPO,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(run.returncode, 0, run.stderr)
                expected = json.loads(
                    (demo / "expected-waves.json").read_text(encoding="utf-8")
                )
                self.assertEqual(json.loads(run.stdout), expected)

        shipped, pull_forward = (
            json.loads((demo / "expected-waves.json").read_text(encoding="utf-8"))
            for demo in DEMOS
        )
        self.assertEqual([item["key"] for item in shipped["unblocked"]], ["API", "UI"])
        self.assertEqual(shipped["deferred"], [])
        self.assertEqual(shipped["currentWave"], 2)
        self.assertEqual(
            [item["key"] for item in pull_forward["unblocked"]], ["Core", "Docs"]
        )
        self.assertEqual([item["key"] for item in pull_forward["deferred"]], ["Sweep"])

    def test_jj_description_triggers_for_owners(self):
        text = skill("jj")
        frontmatter = text.split("---", 2)[1]
        self.assertNotIn("Activate ONLY when", frontmatter)
        self.assertNotIn("Do NOT activate for plain git repos", frontmatter)
        self.assertIn("adopting a git repo with `jj git init --colocate`", frontmatter)


if __name__ == "__main__":
    unittest.main()
