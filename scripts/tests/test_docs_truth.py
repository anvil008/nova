import html
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATES = ROOT / "agents" / "gates"
README = ROOT / "README.md"
ADRS = ROOT / "docs" / "adr"
CHANGELOG = ROOT / "CHANGELOG.md"
DIAGRAMS = ROOT / "docs" / "diagrams"
DIAGRAM_SRC = DIAGRAMS / "src" / "how-work-moves.json"
RENDER = ROOT / "scripts" / "render-diagrams.py"
DOCS_CHECK = ROOT / "skills" / "docs" / "scripts" / "docs_check.py"

# The ADR this milestone records. 0016 is the highest that had landed when the
# issue was written; if something else lands at 0017 first, the ADR is renumbered
# and this glob — plus the README and changelog citations — move with it.
OVERLAP_ADR = "0017-*.md"
ADR_FILENAME = re.compile(r"^\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
# "the documenter runs next to the integrator", however the sentence is phrased.
ALONGSIDE = r"alongside|beside|next to|at the same time|in parallel|concurrent|simultaneous"

HEADING = re.compile(r"(?m)^(#{1,6})[ \t]*(.+?)[ \t]*$")
# The changelog entry this milestone records, found by its heading rather than by
# position: later releases are added above it, so the top entry is not a stable anchor.
OVERLAP_ENTRY = re.compile(r"(?i)build wave loop overlaps")
# A list item starts a new unit only when it is not nested under the current one,
# so a bullet keeps its sub-bullets.
TOP_BULLET = re.compile(r"^ {0,3}(?:[-*+]|\d+[.)])\s+")


def section(text: str, name: str) -> str:
    """The body under the `name` heading, down to the next heading at the same or
    a higher level — so sub-headings stay inside their section."""
    heads = [(m.start(), m.end(), len(m.group(1)), m.group(2)) for m in HEADING.finditer(text)]
    for index, (_, end, level, title) in enumerate(heads):
        if re.match(rf"(?i)^{name}\b", title):
            stop = len(text)
            for later_start, _, later_level, _ in heads[index + 1:]:
                if later_level <= level:
                    stop = later_start
                    break
            return text[end:stop]
    return ""


def statements(text: str) -> list[str]:
    """Every paragraph and every top-level list item, whitespace-collapsed. A
    claim has to fit inside one of these: three unrelated mentions of a word
    scattered through a document do not add up to a sentence that makes it."""
    units: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        current: list[str] = []
        for line in block.splitlines():
            if TOP_BULLET.match(line) and current:
                units.append(" ".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            units.append(" ".join(current))
    return [unit for unit in (re.sub(r"\s+", " ", u).strip() for u in units) if unit]


def changelog_entry(pattern: re.Pattern) -> str | None:
    """The body of the `## ` CHANGELOG.md entry whose heading matches `pattern`,
    down to the next entry — entries are found by title, not by position."""
    text = CHANGELOG.read_text(encoding="utf-8")
    starts = [m.start() for m in re.finditer(r"(?m)^## ", text)]
    for index, start in enumerate(starts):
        stop = starts[index + 1] if index + 1 < len(starts) else len(text)
        entry = text[start:stop]
        if pattern.search(entry.splitlines()[0]):
            return entry
    return None


class DocumentationTruthTests(unittest.TestCase):
    def test_gate_docs_match_wired_codex_events(self):
        config = json.loads((ROOT / "plugins" / "codex" / "hooks" / "hooks.json").read_text())
        events = set(config["hooks"])
        self.assertTrue(events)
        gate_texts = {
            path: path.read_text(encoding="utf-8")
            for path in GATES.glob("codex-*.md")
        }
        self.assertTrue(gate_texts)
        for path, text in gate_texts.items():
            lowered = text.lower()
            for false_claim in ("wires no", "nothing invokes", "no hook is wired", "no hooks are wired"):
                self.assertNotIn(false_claim, lowered, path)
        builder = gate_texts[GATES / "codex-builder.md"]
        for event in events:
            self.assertIn(f"`{event}`", builder)

    def test_docs_do_not_deny_codex_hook_surface(self):
        paths = [README, *ADRS.glob("*.md"), *GATES.glob("*.md"),
                 *(ROOT / "agents" / "bodies").glob("*.md")]
        text = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)
        self.assertNotIn("no equivalent hook surface", text)
        self.assertNotIn("no hook is wired", text)
        self.assertNotIn("no hooks are wired", text)

    def test_antigravity_cli_and_symlink_decision_are_documented(self):
        readme = README.read_text(encoding="utf-8")
        adr = (ADRS / "0006-plugins-install-through-local-marketplaces.md").read_text(
            encoding="utf-8"
        )
        for path, text in ((README, readme), (ADRS / "0006-plugins-install-through-local-marketplaces.md", adr)):
            self.assertNotIn("no plugin CLI", text, path)
            self.assertIn("`agy plugin`", text, path)
            self.assertRegex(text.lower(), r"symlink|explicit links")

    def test_generated_agents_are_in_sync(self):
        body = (ROOT / "agents" / "bodies" / "builder.md").read_text(encoding="utf-8")
        self.assertNotIn("no hook is wired to do this for you", body)
        generated = (ROOT / "agents" / "codex" / "builder.md").read_text(encoding="utf-8")
        self.assertIn("trusted with `/hooks`", generated)
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "sync-agents.py"), "--check"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class OverlapPolicyDocumentationTests(unittest.TestCase):
    """The repository's own account of the build loop, after the wave-loop-overlap
    milestone changed it: ADR, generated diagram, README prose, changelog."""

    def assert_claim(self, text: str, where: str, *patterns: str) -> str:
        """Fail unless one paragraph or list item makes the whole claim."""
        for unit in statements(text):
            if all(re.search(pattern, unit, re.IGNORECASE) for pattern in patterns):
                return unit
        self.fail(f"{where}: no single paragraph or list item states all of {list(patterns)}")

    def overlap_adr(self) -> tuple[Path, str]:
        found = sorted(ADRS.glob(OVERLAP_ADR))
        self.assertEqual(
            len(found), 1,
            f"expected exactly one docs/adr/{OVERLAP_ADR} recording the overlap policy, "
            f"found {[p.name for p in found]}",
        )
        self.assertRegex(found[0].name, ADR_FILENAME)
        return found[0], found[0].read_text(encoding="utf-8")

    def diagram_source(self) -> dict:
        return json.loads(DIAGRAM_SRC.read_text(encoding="utf-8"))

    def test_adr_0017_records_the_overlap_policy(self):
        path, text = self.overlap_adr()
        for name in ("Status", "Context", "Decision", "Consequences"):
            self.assertRegex(text, rf"(?mi)^#+\s*{name}\b", f"{path.name} has no {name} section")
        self.assertRegex(section(text, "Status"), r"(?i)\bAccepted\b")

        decision = section(text, "Decision")
        self.assertTrue(decision.strip(), f"{path.name}: the Decision section is empty")
        where = f"{path.name} Decision"
        # Selection is gated on dependencies, and `wave` demotes to a hint.
        self.assert_claim(
            decision, where,
            r"dependency[- ]gated|gated on (its )?dependenc|not wave[- ]gated",
            r"dependsOn|depends on|dependenc",
            r"wave",
        )
        self.assert_claim(decision, where, r"wave", r"hint")
        # An overlap across the in-flight set defers; a declared one is still a defect.
        self.assert_claim(decision, where, r"defer", r"overlap", r"ownership|hint|glob")
        self.assert_claim(decision, where, r"declared|same[- ]wave", r"overlap", r"reject|defect")
        # The documenter runs beside the integrator and lands inside one combined GREEN.
        self.assert_claim(decision, where, r"documenter", r"integrator", ALONGSIDE)
        self.assert_claim(decision, where, r"document", r"combined GREEN", r"merg")
        # Speculative specifiers yes, speculative builders no.
        self.assert_claim(
            decision, where,
            r"speculative", r"specifier", r"permitted|allowed|may |opportunistic",
        )
        self.assert_claim(decision, where, r"speculative", r"builder", r"\bnot\b|never|\bno\b")
        # One narrow glob per issue; split the issue instead of widening the hint.
        self.assert_claim(
            decision, where,
            r"ownershipHint|ownership hint",
            r"one narrow|exactly one|a single|one path or glob",
            r"glob|path",
        )
        self.assert_claim(decision, where, r"split", r"widen|broaden|coarse")

    def test_adr_0017_names_what_stays_serial(self):
        path, text = self.overlap_adr()
        where = f"{path.name}"
        self.assert_claim(
            text, where,
            r"specifier", r"builder", r"serial|sequential|in order|never concurrent|one after",
        )
        self.assert_claim(
            text, where,
            r"integrator", r"merg", r"serial|sequential|one at a time|one PR at a time",
        )
        self.assert_claim(
            text, where,
            r"combined GREEN",
            r"nothing merges|never merge|no [a-z ]{0,24}merges|merges only|only after|only inside|not until",
        )

    def test_how_work_moves_routes_the_documenter_through_the_gate(self):
        source = self.diagram_source()
        pairs = {(edge["from"], edge["to"]) for edge in source["edges"]}
        for pair in (
            ("pr", "integrator"), ("pr", "docs"), ("docs", "gate"),
            ("integrator", "gate"), ("gate", "merge"), ("merge", "deploy"),
        ):
            self.assertIn(pair, pairs, f"how-work-moves.json is missing the {pair[0]}->{pair[1]} edge")
        for pair in (("merge", "docs"), ("docs", "deploy")):
            self.assertNotIn(
                pair, pairs,
                f"how-work-moves.json still routes {pair[0]}->{pair[1]}: documentation after the merge",
            )
        nodes = {node["id"]: node for node in source["nodes"]}
        docs = nodes["docs"]
        self.assertEqual(docs["kind"], "agent")
        self.assertEqual(docs["label"], "documenter")
        self.assertRegex(docs["sub"], rf"(?i){ALONGSIDE}")
        self.assertRegex(docs["sub"], r"(?i)integrator")
        self.assertEqual(source["direction"], "TB")
        group = source["groups"][0]
        self.assertEqual(group["kind"], "orchestrator")
        self.assertIn("docs", group["nodes"])

    def test_generated_diagrams_match_their_source(self):
        result = subprocess.run(
            [sys.executable, str(RENDER), "--check"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        source = self.diagram_source()
        docs_sub = {node["id"]: node for node in source["nodes"]}["docs"]["sub"]
        labels = (
            [node["label"] for node in source["nodes"]]
            + [node["sub"] for node in source["nodes"] if node.get("sub")]
            + [edge["label"] for edge in source["edges"] if edge.get("label")]
        )
        for theme in ("light", "dark"):
            svg = (DIAGRAMS / f"how-work-moves-{theme}.svg").read_text(encoding="utf-8")
            for label in labels:
                self.assertTrue(
                    label in svg or html.escape(label, quote=False) in svg,
                    f"how-work-moves-{theme}.svg does not carry the source label {label!r}",
                )
            self.assertTrue(
                docs_sub in svg,
                f"how-work-moves-{theme}.svg does not carry the documenter sub-label "
                f"{docs_sub!r} — regenerate with scripts/render-diagrams.py",
            )
            self.assertIsNotNone(
                re.search(rf"(?i){ALONGSIDE}", svg),
                f"how-work-moves-{theme}.svg never says the documenter runs "
                f"alongside the integrator",
            )

    def test_readme_prose_and_alt_text_match_the_diagram(self):
        readme = README.read_text(encoding="utf-8")
        picture = re.search(
            r"(?s)<picture>((?:(?!</picture>).)*how-work-moves(?:(?!</picture>).)*)</picture>",
            readme,
        )
        self.assertIsNotNone(picture, "README.md has no how-work-moves <picture> block")
        alt = re.search(
            r'<img alt="([^"]*)"[^>]*src="docs/diagrams/how-work-moves-light\.svg"',
            picture.group(1),
        )
        self.assertIsNotNone(alt, "the how-work-moves <img> has no alt text (ADR 0004)")
        alt_text = alt.group(1)
        for pattern in (r"documenter", r"integrator", ALONGSIDE, r"gate", r"merg",
                        r"both|includ|cover"):
            self.assertRegex(alt_text, rf"(?i){pattern}", "how-work-moves alt text")

        after = readme[picture.end():]
        stop = after.find("<picture>")
        prose = after[: stop if stop != -1 else len(after)]
        self.assert_claim(prose, "README how-work-moves prose", r"documenter", r"integrator", ALONGSIDE)
        self.assert_claim(prose, "README how-work-moves prose", r"merg", r"gate", r"both|includ|cover")
        self.assertNotRegex(
            readme, r"(?i)hands the result to",
            "README still sequences the documenter after the merge",
        )

    def test_changelog_entry_names_the_four_changes(self):
        top = changelog_entry(OVERLAP_ENTRY)
        where = "the CHANGELOG.md wave-overlap entry"
        self.assertIsNotNone(top, f"CHANGELOG.md has no entry whose heading matches {OVERLAP_ENTRY.pattern!r}")
        self.assert_claim(top, where, r"dependency[- ]gated|gated on (its )?dependenc", r"wave|dependsOn|schedul")
        self.assert_claim(top, where, r"documenter", r"integrator", ALONGSIDE)
        self.assert_claim(top, where, r"speculative", r"specifier")
        self.assert_claim(top, where, r"ownershipHint|ownership hint", r"one narrow|exactly one|a single|one path or glob")
        self.assertRegex(top, r"(?i)ADR[- ]0017", f"{where} does not cite ADR-0017")

    def test_docs_gate_is_green(self):
        result = subprocess.run(
            [sys.executable, "-B", str(DOCS_CHECK), str(ROOT)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["violations"], [])
        adr, _ = self.overlap_adr()
        entry = next(
            (item for item in report["adrs"] if item["path"].endswith(adr.name)), None
        )
        self.assertIsNotNone(entry, f"the docs gate did not inspect {adr.name}")
        self.assertTrue(entry["ok"], f"{adr.name} is missing sections: {entry['missing']}")
        self.assertEqual(entry["number"], 17)


if __name__ == "__main__":
    unittest.main()
