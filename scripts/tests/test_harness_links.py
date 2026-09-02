"""Staged harness trees resolve their own Markdown links (#152, ADR 0023).

An install is a self-contained copy, so a link inside a staged tree that points
at a file the tree does not carry is a broken install: the reader follows it to
nothing. Generation rewrites the shared bodies' repository-relative links into
each harness's own boundary, and this proves that every stager's output — the
geometry that actually ships — has no link the shared source did not already
carry broken.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import harness_generation

STAGED_ROOTS = {
    "claude": Path("dist/claude/workcell"),
    "codex": Path("dist/codex/plugins/workcell"),
    "agy": Path("dist/agy/workcell"),
    "grok": Path("dist/grok/plugins/workcell"),
}


class StagedTreesResolveTheirLinks(unittest.TestCase):
    """One staging run per harness, shared by every case: staging is deterministic."""

    staged: ClassVar[dict[str, subprocess.CompletedProcess[str]]] = {}

    @classmethod
    def setUpClass(cls) -> None:
        cls.inherited = harness_generation.inherited_link_breaks(ROOT)
        for harness in STAGED_ROOTS:
            cls.staged[harness] = subprocess.run(
                [sys.executable, f"scripts/build-{harness}-plugin.py"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

    def test_every_staged_tree_resolves_its_own_links(self) -> None:
        for harness, relative in STAGED_ROOTS.items():
            with self.subTest(harness=harness):
                result = self.staged[harness]
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                tree = ROOT / relative
                self.assertTrue(tree.is_dir(), f"{relative} was not staged")
                failures = [
                    failure.replace(f"{ROOT}/", "", 1)
                    for failure in harness_generation.link_failures(
                        tree, self.inherited
                    )
                ]
                self.assertEqual(
                    failures,
                    [],
                    f"{harness}: staged tree links leave the install (ADR 0023); "
                    "package the target or rewrite the link:\n" + "\n".join(failures),
                )

    def test_inherited_breaks_are_only_vendored_reference_material(self) -> None:
        """The exemption covers upstream documents we copy, and nothing else.

        Without this, repairing a real break by breaking it at the source would
        pass the check above.
        """
        strays = sorted(
            failure.replace(f"{ROOT}/", "", 1)
            for base in (ROOT / "skills", ROOT / "agents", ROOT / "docs")
            for failure in harness_generation.link_failures(base, set())
            if "/references/" not in failure and "/bodies/" not in failure
        )
        self.assertEqual(
            strays,
            [],
            "shared sources must not carry broken links outside vendored "
            "references/ material:\n" + "\n".join(strays),
        )


if __name__ == "__main__":
    unittest.main()
