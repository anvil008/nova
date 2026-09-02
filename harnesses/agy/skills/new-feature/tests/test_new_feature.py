"""Contract tests for `skills/new-feature/SKILL.md`.

The feature these pin is the overlap of the documentation dispatch with the
wave's integration: doc authoring needs only the changed-file and PR list, so it
starts beside the `integrator`, while the *landing* of the docs branch still
waits for a combined GREEN that includes it.
"""

import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"
CANONICAL_BOUNDARY = (
    "You are the orchestrator ([ADR 0007](../../runtime/docs/adr/"
    "0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents, hold the human "
    "gates, run `git` / `jj` / `gh` for branch, merge, and issue-state operations, and read "
    "gate output and handoff records. You never read or edit the target project's code, run "
    "its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch "
    "is orchestration; reading a file's contents to judge it is not."
)
STEP = re.compile(r"^(\d+)\. ", re.MULTILINE)


def text():
    return SKILL.read_text(encoding="utf-8")


def procedure_steps(body):
    """The `## Procedure` section as an ordered list of (number, step text)."""
    section = body.split("\n## Procedure\n", 1)
    if len(section) != 2:
        raise AssertionError("SKILL.md has no `## Procedure` section")
    section = re.split(r"\n## ", section[1], maxsplit=1)[0]
    marks = list(STEP.finditer(section))
    if not marks:
        raise AssertionError("`## Procedure` has no numbered steps")
    steps = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(section)
        steps.append((int(mark.group(1)), section[mark.start() : end]))
    return steps


def dispatch_step(steps, agent):
    """The one numbered step that dispatches `agent`, as (number, text)."""
    hits = [(n, s) for n, s in steps if f"`{agent}`" in s]
    if len(hits) != 1:
        raise AssertionError(
            f"expected exactly one Procedure step to dispatch `{agent}`, "
            f"found {[n for n, _ in hits]}"
        )
    return hits[0]


class DocumenterOverlapTests(unittest.TestCase):
    def test_documenter_is_dispatched_with_the_integrator(self):
        steps = procedure_steps(text())
        number, step = dispatch_step(steps, "documenter")
        self.assertIn(
            "`integrator`",
            step,
            "the `documenter` dispatch must sit in the same numbered step as the "
            "`integrator` dispatch",
        )
        self.assertRegex(
            step,
            r"(?i)at the same time|alongside|in parallel|simultaneous|concurrent",
            "the step must say the two dispatches happen together, not in sequence",
        )
        self.assertRegex(
            step,
            r"(?i)own workspace|workcell-ws add",
            "each of the two dispatches needs its own workspace",
        )
        self.assertRegex(
            step,
            r"(?i)changed-file",
            "the documenter's brief carries the changed-file and PR list",
        )
        self.assertIn(
            "evidence",
            step,
            "the wave's code PRs still merge on the integrator's evidence",
        )
        for later_number, later in [(n, s) for n, s in steps if n > number]:
            with self.subTest(step=later_number):
                self.assertNotIn(
                    "`documenter`",
                    later,
                    "no step after the merge may dispatch the `documenter`",
                )

    def test_docs_land_only_inside_a_combined_green(self):
        steps = procedure_steps(text())
        _, step = dispatch_step(steps, "documenter")
        self.assertIn(
            "combined GREEN",
            step,
            "the docs branch lands only on a combined GREEN",
        )
        self.assertRegex(
            step,
            r"(?i)(docs|documentation)[^.\n]{0,120}merges? only",
            "the step must state that documentation merges only inside a combined "
            "GREEN that includes it",
        )
        self.assertRegex(
            step,
            r"(?i)(one more|another|an additional|an extra) `?integrator`?",
            "the step must name the extra integrator round for a documenter that "
            "returns after the wave's run",
        )
        self.assertRegex(
            step,
            r"(?i)before[^.\n]{0,160}merge",
            "the step must also cover the documenter that returns before the "
            "serial merge begins",
        )
        self.assertIn(
            "skills/docs/scripts/docs_check.py",
            step,
            "that round is also the docs gate",
        )

    def test_docs_ownership_is_disjoint_from_code_ownership(self):
        steps = procedure_steps(text())
        _, step = dispatch_step(steps, "documenter")
        self.assertIn("`ownership`", step)
        self.assertRegex(
            step,
            r"(?i)docs-only|documentation-only|docs only",
            "the documenter's ownership glob must be docs-only",
        )
        self.assertIn(
            "disjoint",
            step,
            "the docs ownership must be disjoint from every code issue's "
            "ownershipHint, so the branches can never collide",
        )
        self.assertIn("ownershipHint", step)
        self.assertIn(
            "agents/handoff.md",
            step,
            "cite agents/handoff.md as where the `ownership` field is defined",
        )

    def test_pinned_new_feature_contracts_survive(self):
        body = text()
        self.assertIn("single-PR mode", body)
        self.assertIn("at least five clarifying questions", body)
        self.assertIn(CANONICAL_BOUNDARY, body)
        after_title = body.split("\n# ", 1)[1].split("\n\n", 1)[1]
        self.assertEqual(
            after_title.split("\n\n")[1],
            CANONICAL_BOUNDARY,
            "the canonical ADR-0007 orchestrator paragraph must stay the second "
            "paragraph after the title",
        )


if __name__ == "__main__":
    unittest.main()
