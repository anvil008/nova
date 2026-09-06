"""Shared workflow references stay reachable after public skill consolidation."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


class SharedWorkflowReferences(unittest.TestCase):
    def test_local_references_resolve(self):
        paths = [ROOT / "SKILL.md", *sorted((ROOT / "references").glob("*.md")),
                 REPO / "skills/debug/SKILL.md", REPO / "skills/refactor/SKILL.md"]
        for source in paths:
            for target in re.findall(r"\]\(([^)]+)\)", source.read_text(encoding="utf-8")):
                if target.startswith(("https://", "http://", "#")):
                    continue
                with self.subTest(source=source.relative_to(REPO), target=target):
                    self.assertTrue((source.parent / target.split("#", 1)[0]).exists())

    def test_all_build_protocols_are_discoverable_from_entrypoint(self):
        body = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        targets = set(re.findall(r"\]\((references/[^)]+)\)", body))
        self.assertTrue({"references/single-change.md", "references/dependency-runs.md",
                         "references/finalization.md"}.issubset(targets))


if __name__ == "__main__":
    unittest.main()
