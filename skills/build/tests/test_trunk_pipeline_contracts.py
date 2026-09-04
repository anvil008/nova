"""Acceptance tests for Jujutsu trunk pipeline contracts in build skill (#216)."""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILL_MD = REPO / "skills" / "build" / "SKILL.md"

CANONICAL_BOUNDARY = (
    "You are the orchestrator ([ADR 0007](../../docs/adr/"
    "0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents, hold the human "
    "gates, run `git` / `jj` / `gh` for branch, merge, and issue-state operations, and read "
    "gate output and handoff records. You never read or edit the target project's code, run "
    "its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch "
    "is orchestration; reading a file's contents to judge it is not."
)

REQUIRED_WAVE_INVARIANTS = (
    # the build-wave trace landed in skills/build/SKILL.md
    "wiki.py record",
    "--kind build-wave",
    "wiki.py status --repo .",
    # the one done definition, agreed with reconcile_github.py
    "closed **and** (`status:done` or `state_reason == completed`)",
    # the selector
    "skills/build/scripts/waves.py",
    "waves.py",
    # single-PR mode
    "## Single-PR mode",
    "<planId>-integration",
    "agents/handoff.md",
    "`base`",
    "final PR from the integration branch to `main`",
    # the speculative-specifier allowance and its limits
    "Speculative specifiers",
    "Never a speculative builder",
    "tdd-guard reseal --reason",
    # the refactor mode
    "`mode: refactor`",
    "`mode: baseline`",
    # the gates
    "combined GREEN",
    "never dispatch a builder for an issue with no seal",
    "sole completion authority",
)

RETIRED_PARAPHRASES = (
    "never the code",
    "not the contents of the files",
    "read the file list and the manifests",
    "Nothing here has you read the target project",
    "without closing it yet",
)


class TestTrunkPipelineContracts(unittest.TestCase):
    """Acceptance tests for issue #216: transition build skill to Jujutsu trunk-based pipeline."""

    def test_build_skill_eliminates_intermediate_prs(self) -> None:
        """Verify skills/build/SKILL.md eliminates intermediate PR creation
        (no gh pr create per builder, no gh pr checks --watch) and documents
        local jj rebase wave integration onto <planId>-integration with local changeId handoff."""
        self.assertTrue(SKILL_MD.is_file(), f"{SKILL_MD} does not exist")
        skill_text = SKILL_MD.read_text(encoding="utf-8")

        # 1. Eliminates gh pr create per builder and gh pr checks --watch
        self.assertFalse(
            "gh pr create" in skill_text,
            "skills/build/SKILL.md must eliminate 'gh pr create' per builder",
        )
        self.assertFalse(
            "gh pr checks --watch" in skill_text,
            "skills/build/SKILL.md must eliminate 'gh pr checks --watch'",
        )

        # 2. Builder phase must eliminate intermediate PR creation / opening PRs
        self.assertFalse(
            "opens the PR" in skill_text,
            "skills/build/SKILL.md must eliminate builder opening intermediate PRs ('opens the PR')",
        )
        self.assertFalse(
            bool(re.search(r"builders?\s+open\s+(?:their\s+)?(?:per-issue\s+)?prs?", skill_text, re.IGNORECASE)),
            "skills/build/SKILL.md must not instruct builders to open per-issue or intermediate PRs",
        )

        # 3. Documents local jj rebase wave integration onto <planId>-integration
        self.assertTrue(
            "jj rebase" in skill_text,
            "skills/build/SKILL.md must document 'jj rebase'",
        )
        self.assertTrue(
            "<planId>-integration" in skill_text,
            "skills/build/SKILL.md must document '<planId>-integration'",
        )
        has_jj_rebase_integration = (
            "jj rebase -s <changeId> -d <planId>-integration" in skill_text
            or re.search(r"jj\s+rebase.*?<planId>-integration", skill_text, re.DOTALL) is not None
        )
        self.assertTrue(
            has_jj_rebase_integration,
            "skills/build/SKILL.md must document jj rebase wave integration onto <planId>-integration",
        )

        # 4. Documents local changeId handoff
        self.assertTrue(
            "changeId" in skill_text,
            "skills/build/SKILL.md must document 'changeId'",
        )
        has_change_id_handoff = (
            re.search(
                r"changeId.*?(?:handoff|hand-off|return|commit)|(?:local|trunk).*?changeId",
                skill_text,
                re.IGNORECASE,
            )
            is not None
        )
        self.assertTrue(
            has_change_id_handoff,
            "skills/build/SKILL.md must document local changeId handoff",
        )

    def test_build_skill_scopes_builder_testing(self) -> None:
        """Verify skills/build/SKILL.md instructs builders to verify ONLY sealed acceptance tests
        and reserves full project test suite (scripts/run-tests.sh) for integrator."""
        self.assertTrue(SKILL_MD.is_file(), f"{SKILL_MD} does not exist")
        skill_text = SKILL_MD.read_text(encoding="utf-8")

        # 1. Instructs builders to verify ONLY sealed acceptance tests
        has_only_sealed = (
            re.search(
                r"(?:verify|run)\s+(?:only|ONLY)\s+(?:the\s+)?sealed\s+(?:acceptance\s+)?tests?",
                skill_text,
                re.IGNORECASE,
            )
            is not None
            or "only the sealed acceptance test" in skill_text.lower()
            or "only sealed acceptance test" in skill_text.lower()
            or "only the sealed test" in skill_text.lower()
            or "only sealed test" in skill_text.lower()
        )
        self.assertTrue(
            has_only_sealed,
            "skills/build/SKILL.md must instruct builders to verify ONLY sealed acceptance tests",
        )

        # 2. Forbids broad test suites or discovery suites for builders
        forbids_broad = (
            re.search(
                r"(?:forbid|never|prohibit|do not run).*?(?:broad|whole-project|discovery).*?(?:suite|runner|tests?)",
                skill_text,
                re.IGNORECASE,
            )
            is not None
            or re.search(
                r"(?:broad|whole-project|discovery).*?(?:suite|runner|tests?).*?(?:forbid|never|prohibit)",
                skill_text,
                re.IGNORECASE,
            )
            is not None
            or ("broad" in skill_text.lower() and ("forbid" in skill_text.lower() or "never" in skill_text.lower()))
        )
        self.assertTrue(
            forbids_broad,
            "skills/build/SKILL.md must forbid broad or discovery test suites for builders",
        )

        # 3. Reserves full project test suite (scripts/run-tests.sh) for integrator
        self.assertTrue(
            "scripts/run-tests.sh" in skill_text,
            "skills/build/SKILL.md must reference 'scripts/run-tests.sh'",
        )
        has_integrator_full_suite = (
            re.search(
                r"integrator.*?(?:full\s+(?:project\s+)?(?:test\s+)?suite|scripts/run-tests\.sh)",
                skill_text,
                re.IGNORECASE | re.DOTALL,
            )
            is not None
            or re.search(
                r"(?:full\s+(?:project\s+)?(?:test\s+)?suite|scripts/run-tests\.sh).*?integrator",
                skill_text,
                re.IGNORECASE | re.DOTALL,
            )
            is not None
        )
        self.assertTrue(
            has_integrator_full_suite,
            "skills/build/SKILL.md must reserve full project test suite (scripts/run-tests.sh) for integrator",
        )

    def test_build_skill_contract_invariants_pass(self) -> None:
        """Verify that all contract phrases required by test_skill_contracts.py
        are preserved in skills/build/SKILL.md."""
        self.assertTrue(SKILL_MD.is_file(), f"{SKILL_MD} does not exist")
        skill_text = SKILL_MD.read_text(encoding="utf-8")

        # Canonical boundary
        self.assertTrue(
            CANONICAL_BOUNDARY in skill_text,
            "skills/build/SKILL.md must preserve canonical orchestrator boundary",
        )

        # Retired phrases must not be present
        for phrase in RETIRED_PARAPHRASES:
            self.assertFalse(
                phrase in skill_text,
                f"Retired paraphrase found in skills/build/SKILL.md: {phrase!r}",
            )

        # Wave loop and single-PR invariants required by test_skill_contracts.py
        for phrase in REQUIRED_WAVE_INVARIANTS:
            self.assertTrue(
                phrase in skill_text,
                f"Contract invariant required by test_skill_contracts.py missing: {phrase!r}",
            )

        # Run test_skill_contracts.py to verify all contracts pass cleanly
        cmd = [sys.executable, "-m", "unittest", "skills/build/tests/test_skill_contracts.py"]
        res = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, check=False)
        self.assertEqual(
            res.returncode,
            0,
            f"test_skill_contracts.py failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
