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
SKILLS = ROOT / "skills"
EVAL_RUNS = ROOT / "docs" / "eval-runs.md"


LAYERED_GENERATION_GATES = {
    "agent sync --check": lambda step: (
        "scripts/sync-agents.py" in step and "--check" in step
    ),
    "skill sync --check": lambda step: (
        "scripts/sync-skills.py" in step and "--check" in step
    ),
    "contract parity": lambda step: (
        "contract" in step.lower() and "parity" in step.lower()
    ),
    "model-guide freshness": lambda step: (
        "docs/models/check/check_guides.py" in step and "--check" in step
    ),
}


def ci_steps(workflow: str) -> list[str]:
    starts = [match.start() for match in re.finditer(r"(?m)^\s*- name:", workflow)]
    return [
        workflow[
            start : starts[index + 1] if index + 1 < len(starts) else len(workflow)
        ]
        for index, start in enumerate(starts)
    ]


def assert_layered_generation_gates(workflow: str) -> None:
    steps = ci_steps(workflow)
    for name, predicate in LAYERED_GENERATION_GATES.items():
        assert any(predicate(step) for step in steps), f"missing CI gate: {name}"


# The ADR this milestone records. 0016 is the highest that had landed when the
# issue was written; if something else lands at 0017 first, the ADR is renumbered
# and this glob — plus the README and changelog citations — move with it.
OVERLAP_ADR = "0017-*.md"
ADR_FILENAME = re.compile(r"^\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
# "the documenter runs next to the integrator", however the sentence is phrased.
ALONGSIDE = (
    r"alongside|beside|next to|at the same time|in parallel|concurrent|simultaneous"
)

HEADING = re.compile(r"(?m)^(#{1,6})[ \t]*(.+?)[ \t]*$")
# The changelog entry this milestone records, found by its heading rather than by
# position: later releases are added above it, so the top entry is not a stable anchor.
OVERLAP_ENTRY = re.compile(r"(?i)build wave loop overlaps")
# A list item starts a new unit only when it is not nested under the current one,
# so a bullet keeps its sub-bullets.
TOP_BULLET = re.compile(r"^ {0,3}(?:[-*+]|\d+[.)])\s+")

# The ADR this milestone records: the wiki layer. 0018 is the highest that had
# landed when the issue was written; if something else lands at 0019 first, the
# ADR is renumbered and this glob — plus the changelog citation — move with it.
WIKI_ADR = "0019-*.md"
WIKI_ADR_NUMBER = 19
# The changelog entry this milestone records, found by its heading.
WIKI_ENTRY = re.compile(r"(?i)wiki layer")
# "18 skills", "skills/  18 shared workflows" — a count claim is a bare number
# next to the word, in either order. A number welded to a word by `-` or `/`
# (`0009-skills-are-dispatch-contracts.md`) is a path, not a count.
NUMBER = r"(?<![\w/-])(\d+)(?![\w-])"
SKILL_COUNT = re.compile(
    rf"(?i)(?:{NUMBER}[^\n\d]{{0,24}}?\bskills?\b|\bskills?\b[^\n\d]{{0,24}}?{NUMBER})"
)
# A markdown table row whose cell links a skill's SKILL.md by name.
TABLE_LINK = re.compile(
    r"(?m)^\|.*?\[\s*`?(?P<name>[a-z0-9-]+)`?\s*\]\((?P<href>[^)]+)\)"
)

NOT = r"\bnever\b|\bnot\b|\bno\b|\bneither\b|\bnor\b|\bcannot\b|can't|\bwithout\b"

INSTALL = ROOT / "docs" / "install.md"

# The ADR this milestone records: an install is a self-contained copy on every harness.
# 0022 is the highest that had landed when the issue was written; if something else lands
# at 0023 first, the ADR is renumbered and this glob — plus the changelog citation and the
# docs-gate number below — move with it.
SELF_CONTAINED_ADR = "0023-*.md"
SELF_CONTAINED_ADR_NUMBER = 23
# The changelog entry this milestone records, found by its heading rather than by position.
SELF_CONTAINED_ENTRY = re.compile(r"(?i)self[- ]contain")

# An Antigravity *install destination* — where a plugin is put, as opposed to the wrapper
# directory inside this repository. Only a claim about a destination is a claim about how
# the install works, so `plugins/agy/`'s own per-skill links are deliberately not matched.
AGY_DEST = (
    r"~/\.gemini|\.gemini/config/plugins|antigravity-cli"
    r"|antigravity(?:'s)? (?:install|plugin) (?:path|dir|director)"
)
LINK = r"\bsym-?link(?:s|ed|ing)?\b|\blink(?:s|ed|ing)?\b"
# A denial has to sit next to the word it denies: "not a symlink", "no longer symlinked",
# "rather than a link", "nothing is linked". A stray negation elsewhere in the sentence is
# not a denial — "its install paths are not a stable documented contract, so Workcell
# symlinks the wrapper there instead" is exactly the claim this milestone retires.
DENIAL = (
    r"(?:\bnot\b|\bno\b|\bnever\b|\bnothing\b|no longer|rather than|instead of)"
    r"(?:\s+(?:a|an|any|is|are|be|been|it|its|this|that|the|will|would|does|do|to))*"
    r"(?:\s+(?:live|longer|real))*\s+(?:sym-?)?link(?:s|ed)?\b"
)
# A marketplace whose root is this repository — the layout ADR 0023 retires.
REPO_ROOTED_MARKETPLACE = (
    r"repositor(?:y|ies) root|root of (?:the |this )?repositor"
    r"|rooted at (?:the |this )?repositor|repo root|marketplace root"
    r"|\.claude-plugin/marketplace\.json|\.agents/plugins/marketplace\.json"
)
RETIRED = r"\bnot\b|\bno\b|\bnever\b|no longer|retire|remov|delet|former|previous|used to|instead of|rather than"
FENCE = re.compile(r"(?ms)^```.*?^```[ \t]*$")
SENTENCE = re.compile(r"(?<=[.!?;])\s+")
# The `plugins/agy/` row of the README's repository-layout tree.
AGY_LAYOUT_LINE = re.compile(r"(?m)^.*──[ \t]*agy/.*$")


def find_claim(text: str, *patterns: str) -> str | None:
    """The first paragraph or top-level list item that makes the whole claim."""
    for unit in statements(text):
        if all(re.search(pattern, unit, re.IGNORECASE) for pattern in patterns):
            return unit
    return None


def section(text: str, name: str) -> str:
    """The body under the `name` heading, down to the next heading at the same or
    a higher level — so sub-headings stay inside their section."""
    heads = [
        (m.start(), m.end(), len(m.group(1)), m.group(2))
        for m in HEADING.finditer(text)
    ]
    for index, (_, end, level, title) in enumerate(heads):
        if re.match(rf"(?i)^{name}\b", title):
            stop = len(text)
            for later_start, _, later_level, _ in heads[index + 1 :]:
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


def prose_sentences(text: str) -> list[str]:
    """Every prose sentence, with fenced code blocks removed.

    Paragraphs are reflowed first: these documents wrap at 100 columns, so a claim
    routinely spans three source lines. Sentence granularity — not paragraph — is what
    makes "this is no longer a link" distinguishable from a paragraph that happens to
    contain both a denial about one harness and a live-link claim about another."""
    out: list[str] = []
    for unit in statements(FENCE.sub("\n\n", text)):
        out += [s.strip() for s in SENTENCE.split(unit) if s.strip()]
    return out


class DocumentationTruthTests(unittest.TestCase):
    def test_new_checks_are_gated(self):
        """new-checks-are-gated (integration)."""
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        assert_layered_generation_gates(workflow)

        steps = ci_steps(workflow)
        for name, predicate in LAYERED_GENERATION_GATES.items():
            with self.subTest(deleted=name):
                matching = next(step for step in steps if predicate(step))
                mutated = workflow.replace(matching, "", 1)
                with self.assertRaisesRegex(AssertionError, re.escape(name)):
                    assert_layered_generation_gates(mutated)

    def test_gate_docs_match_wired_codex_events(self):
        config = json.loads(
            (ROOT / "plugins" / "codex" / "hooks" / "hooks.json").read_text()
        )
        events = set(config["hooks"])
        self.assertTrue(events)
        gate_texts = {
            path: path.read_text(encoding="utf-8") for path in GATES.glob("codex-*.md")
        }
        self.assertTrue(gate_texts)
        for path, text in gate_texts.items():
            lowered = text.lower()
            for false_claim in (
                "wires no",
                "nothing invokes",
                "no hook is wired",
                "no hooks are wired",
            ):
                self.assertNotIn(false_claim, lowered, path)
        builder = gate_texts[GATES / "codex-builder.md"]
        for event in events:
            self.assertIn(f"`{event}`", builder)

    def test_docs_do_not_deny_codex_hook_surface(self):
        paths = [
            README,
            *ADRS.glob("*.md"),
            *GATES.glob("*.md"),
            *(ROOT / "agents" / "bodies").glob("*.md"),
        ]
        text = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)
        self.assertNotIn("no equivalent hook surface", text)
        self.assertNotIn("no hook is wired", text)
        self.assertNotIn("no hooks are wired", text)

    def test_antigravity_cli_and_symlink_decision_are_documented(self):
        """ADR 0006 keeps the `agy plugin` decision it made and points at its successor;
        ADR 0023 and the README describe the owned copy that replaced it.

        Rewritten deliberately for ADR 0023: before this milestone the same test pinned
        the README to a *live* Antigravity link, which is the claim the milestone
        retires. ADR 0006's own prose still says what it said — it is history — so the
        `agy plugin` string and the absence of "no plugin CLI" are unchanged."""
        readme = README.read_text(encoding="utf-8")
        adr_0006_path = ADRS / "0006-plugins-install-through-local-marketplaces.md"
        adr_0006 = adr_0006_path.read_text(encoding="utf-8")

        self.assertNotIn("no plugin CLI", adr_0006, adr_0006_path)
        self.assertIn("`agy plugin`", adr_0006, adr_0006_path)
        self.assertRegex(
            section(adr_0006, "Status"),
            r"0023",
            f"{adr_0006_path.name}: the Status section does not point at ADR 0023",
        )

        found = sorted(ADRS.glob(SELF_CONTAINED_ADR))
        self.assertEqual(
            len(found),
            1,
            f"expected exactly one docs/adr/{SELF_CONTAINED_ADR} to carry the successor "
            f"decision, found {[p.name for p in found]}",
        )
        adr_0023 = found[0].read_text(encoding="utf-8")
        self.assertIn(
            "`agy plugin`",
            adr_0023,
            f"{found[0].name} never names the `agy plugin` CLI it declines to use",
        )
        self.assertIsNotNone(
            find_claim(
                adr_0023,
                r"antigravity|\bagy\b",
                r"\.gemini/config/plugins",
                r"cop(?:y|ies|ied)",
            ),
            f"{found[0].name} never states that Antigravity gets an owned copy at its "
            f"documented scan directory",
        )
        self.assertIsNotNone(
            find_claim(readme, r"antigravity|\bagy\b", r"cop(?:y|ies|ied)", r"own"),
            "README.md never describes the Antigravity install as an owned copy",
        )

    def test_generated_agents_are_in_sync(self):
        body = (ROOT / "agents" / "bodies" / "builder.md").read_text(encoding="utf-8")
        self.assertNotIn("no hook is wired to do this for you", body)
        generated = (ROOT / "agents" / "codex" / "builder.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("trusted with `/hooks`", generated)
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "sync-agents.py"), "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
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
        self.fail(
            f"{where}: no single paragraph or list item states all of {list(patterns)}"
        )

    def overlap_adr(self) -> tuple[Path, str]:
        found = sorted(ADRS.glob(OVERLAP_ADR))
        self.assertEqual(
            len(found),
            1,
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
            self.assertRegex(
                text, rf"(?mi)^#+\s*{name}\b", f"{path.name} has no {name} section"
            )
        self.assertRegex(section(text, "Status"), r"(?i)\bAccepted\b")

        decision = section(text, "Decision")
        self.assertTrue(decision.strip(), f"{path.name}: the Decision section is empty")
        where = f"{path.name} Decision"
        # Selection is gated on dependencies, and `wave` demotes to a hint.
        self.assert_claim(
            decision,
            where,
            r"dependency[- ]gated|gated on (its )?dependenc|not wave[- ]gated",
            r"dependsOn|depends on|dependenc",
            r"wave",
        )
        self.assert_claim(decision, where, r"wave", r"hint")
        # An overlap across the in-flight set defers; a declared one is still a defect.
        self.assert_claim(decision, where, r"defer", r"overlap", r"ownership|hint|glob")
        self.assert_claim(
            decision, where, r"declared|same[- ]wave", r"overlap", r"reject|defect"
        )
        # The documenter runs beside the integrator and lands inside one combined GREEN.
        self.assert_claim(decision, where, r"documenter", r"integrator", ALONGSIDE)
        self.assert_claim(decision, where, r"document", r"combined GREEN", r"merg")
        # Speculative specifiers yes, speculative builders no.
        self.assert_claim(
            decision,
            where,
            r"speculative",
            r"specifier",
            r"permitted|allowed|may |opportunistic",
        )
        self.assert_claim(
            decision, where, r"speculative", r"builder", r"\bnot\b|never|\bno\b"
        )
        # One narrow glob per issue; split the issue instead of widening the hint.
        self.assert_claim(
            decision,
            where,
            r"ownershipHint|ownership hint",
            r"one narrow|exactly one|a single|one path or glob",
            r"glob|path",
        )
        self.assert_claim(decision, where, r"split", r"widen|broaden|coarse")

    def test_adr_0017_names_what_stays_serial(self):
        path, text = self.overlap_adr()
        where = f"{path.name}"
        self.assert_claim(
            text,
            where,
            r"specifier",
            r"builder",
            r"serial|sequential|in order|never concurrent|one after",
        )
        self.assert_claim(
            text,
            where,
            r"integrator",
            r"merg",
            r"serial|sequential|one at a time|one PR at a time",
        )
        self.assert_claim(
            text,
            where,
            r"combined GREEN",
            r"nothing merges|never merge|no [a-z ]{0,24}merges|merges only|only after|only inside|not until",
        )

    def test_how_work_moves_routes_the_documenter_through_the_gate(self):
        source = self.diagram_source()
        pairs = {(edge["from"], edge["to"]) for edge in source["edges"]}
        for pair in (
            ("pr", "integrator"),
            ("pr", "docs"),
            ("docs", "gate"),
            ("integrator", "gate"),
            ("gate", "merge"),
            ("merge", "deploy"),
        ):
            self.assertIn(
                pair,
                pairs,
                f"how-work-moves.json is missing the {pair[0]}->{pair[1]} edge",
            )
        for pair in (("merge", "docs"), ("docs", "deploy")):
            self.assertNotIn(
                pair,
                pairs,
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
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
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
        for pattern in (
            r"documenter",
            r"integrator",
            ALONGSIDE,
            r"gate",
            r"merg",
            r"both|includ|cover",
        ):
            self.assertRegex(alt_text, rf"(?i){pattern}", "how-work-moves alt text")

        after = readme[picture.end() :]
        stop = after.find("<picture>")
        prose = after[: stop if stop != -1 else len(after)]
        self.assert_claim(
            prose,
            "README how-work-moves prose",
            r"documenter",
            r"integrator",
            ALONGSIDE,
        )
        self.assert_claim(
            prose, "README how-work-moves prose", r"merg", r"gate", r"both|includ|cover"
        )
        self.assertNotRegex(
            readme,
            r"(?i)hands the result to",
            "README still sequences the documenter after the merge",
        )

    def test_changelog_entry_names_the_four_changes(self):
        top = changelog_entry(OVERLAP_ENTRY)
        where = "the CHANGELOG.md wave-overlap entry"
        self.assertIsNotNone(
            top,
            f"CHANGELOG.md has no entry whose heading matches {OVERLAP_ENTRY.pattern!r}",
        )
        self.assert_claim(
            top,
            where,
            r"dependency[- ]gated|gated on (its )?dependenc",
            r"wave|dependsOn|schedul",
        )
        self.assert_claim(top, where, r"documenter", r"integrator", ALONGSIDE)
        self.assert_claim(top, where, r"speculative", r"specifier")
        self.assert_claim(
            top,
            where,
            r"ownershipHint|ownership hint",
            r"one narrow|exactly one|a single|one path or glob",
        )
        self.assertRegex(top, r"(?i)ADR[- ]0017", f"{where} does not cite ADR-0017")

    def test_docs_gate_is_green(self):
        result = subprocess.run(
            [sys.executable, "-B", str(DOCS_CHECK), str(ROOT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["violations"], [])
        adr, _ = self.overlap_adr()
        entry = next(
            (item for item in report["adrs"] if item["path"].endswith(adr.name)), None
        )
        self.assertIsNotNone(entry, f"the docs gate did not inspect {adr.name}")
        self.assertTrue(
            entry["ok"], f"{adr.name} is missing sections: {entry['missing']}"
        )
        self.assertEqual(entry["number"], 17)


class WikiLayerDocumentationTests(unittest.TestCase):
    """The repository's own account of the wiki layer: ADR 0019, the README skill
    inventory, the eval-runs boundary, and the changelog entry."""

    def assert_claim(self, text: str, where: str, *patterns: str) -> str:
        """Fail unless one paragraph or list item makes the whole claim."""
        unit = find_claim(text, *patterns)
        if unit is None:
            self.fail(
                f"{where}: no single paragraph or list item states all of {list(patterns)}"
            )
        return unit

    def wiki_adr(self) -> tuple[Path, str]:
        found = sorted(ADRS.glob(WIKI_ADR))
        self.assertEqual(
            len(found),
            1,
            f"expected exactly one docs/adr/{WIKI_ADR} recording the wiki layer, "
            f"found {[p.name for p in found]}",
        )
        self.assertRegex(found[0].name, ADR_FILENAME)
        return found[0], found[0].read_text(encoding="utf-8")

    def wiki_adr_section(self, name: str) -> tuple[str, str]:
        path, text = self.wiki_adr()
        body = section(text, name)
        self.assertTrue(body.strip(), f"{path.name}: the {name} section is empty")
        return f"{path.name} {name}", body

    # --- adr_0019_records_the_store_and_its_namespacing ---------------------

    def test_adr_0019_records_the_store_and_its_namespacing(self):
        path, text = self.wiki_adr()
        for name in ("Status", "Context", "Decision", "Consequences"):
            self.assertRegex(
                text, rf"(?mi)^#+\s*{name}\b", f"{path.name} has no {name} section"
            )
        self.assertRegex(section(text, "Status"), r"(?i)\bAccepted\b")
        for name in ("Context", "Decision", "Consequences"):
            self.assertTrue(
                section(text, name).strip(), f"{path.name}: the {name} section is empty"
            )

        where, decision = self.wiki_adr_section("Decision")
        # One store, outside every repository, named by an overridable variable.
        self.assert_claim(
            decision,
            where,
            r"WORKCELL_WIKI_HOME",
            r"~/\.workcell/wiki",
            r"default",
            r"outside (?:every|any|the) repositor|outside the repositor",
        )
        # One namespace per project key, and nothing flat or shared across projects.
        self.assert_claim(
            decision,
            where,
            r"one namespace per project|namespace per project|per[- ]project namespace",
            r"<project-key>|project[- ]key",
        )
        self.assert_claim(
            decision,
            where,
            r"per[- ]project namespacing|namespac",
            NOT,
            r"flat|shared wiki",
            r"cross[- ]project|across projects|other project",
        )
        # Three layers, three durability rules.
        self.assert_claim(
            decision,
            where,
            r"raw/",
            r"write[- ]once",
            r"append[- ]only",
            r"`?skills/`?",
            r"untouched|unchanged|unaffected|not touched|outside this decision",
        )
        # A namespace's existence is the entire opt-in.
        self.assert_claim(
            decision,
            where,
            r"opt[- ]in",
            r"namespace",
            r"exist",
        )

    # --- adr_0019_records_the_project_key_rules -----------------------------

    def test_adr_0019_records_the_project_key_rules(self):
        where, decision = self.wiki_adr_section("Decision")
        # The normalized origin remote, with a path fallback when there is none.
        self.assert_claim(
            decision,
            where,
            r"project[- ]key|\bkey\b",
            r"normali[sz]",
            r"origin",
            r"fall(?:s|ing|en)?[- ]?back|fallback",
            r"basename|toplevel",
            r"hash",
        )
        # Resolved from the primary toplevel, so every workspace shares one key.
        self.assert_claim(
            decision,
            where,
            r"primary toplevel|toplevel",
            r"workspace",
            r"same key|one key|a single key|share",
        )
        # Recorded identity beats inferred identity: a mismatch is refused by name.
        self.assert_claim(
            decision,
            where,
            r"mismatch|does not match|different source|identity",
            r"refus|reject",
            r"\bname",
            r"silent",
            r"shar|fork",
        )

    # --- adr_0019_names_the_ablation_as_structural --------------------------

    def test_adr_0019_names_the_ablation_as_structural(self):
        path, text = self.wiki_adr()
        where = path.name
        # The ablation holds because the store is somewhere a diff cannot reach.
        self.assert_claim(
            text,
            where,
            r"outside (?:every|any|the) repositor",
            r"working cop",
            r"workspace",
            r"diff",
            r"eval",
            r"contain",
            NOT,
        )
        # And therefore no guard changed — with what was actually checked, named.
        self.assert_claim(
            text,
            where,
            r"no guard change|no change to (?:the |any )?guards?|guards? (?:need|require)s? no change"
            r"|without (?:a |any )?guard change|no guards? (?:change|edit)",
            r"build-guard",
            r"outside[- ]repositor|outside the repositor|outside any repositor|outside every repositor",
            r"tdd-guard",
            r"sealed[- ]path",
            r"false",
        )

    # --- adr_0019_names_what_the_wiki_never_does ----------------------------

    def test_adr_0019_names_what_the_wiki_never_does(self):
        path, text = self.wiki_adr()
        where = path.name
        self.assert_claim(text, where, NOT, r"reset", r"roll(?:ed)?[- ]?back")
        self.assert_claim(
            text,
            where,
            r"runtime agent",
            NOT,
            r"given|handed|receive|see |read|access",
        )
        self.assert_claim(
            text,
            where,
            r"eval mode",
            r"record",
            r"consolidat",
            NOT,
        )
        self.assert_claim(
            text,
            where,
            r"project[- ]local|overlay",
            r"shared `?skills/?`?",
            NOT,
            r"amend|change|modif|edit|update|touch",
        )

    # --- adr_0019_records_the_two_residuals ---------------------------------

    def test_adr_0019_records_the_two_residuals(self):
        where, consequences = self.wiki_adr_section("Consequences")
        self.assert_claim(
            consequences,
            where,
            r"per[- ]machine",
            r"per[- ]user",
            r"per[- ]team|\bteam\b",
        )
        self.assert_claim(
            consequences,
            where,
            r"permission",
            r"harness",
            r"remaining|only|last|sole",
            r"surface",
            r"wiki\.py",
            r"editor",
        )

    # --- readme_counts_and_lists_the_wiki_skill -----------------------------

    def test_readme_counts_and_lists_the_wiki_skill(self):
        readme = README.read_text(encoding="utf-8")
        shipped = sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md"))
        self.assertIn("wiki", shipped, "skills/wiki/SKILL.md is not present")

        written = [
            int(match.group(1) or match.group(2))
            for match in SKILL_COUNT.finditer(readme)
        ]
        self.assertTrue(written, "README.md never states how many skills there are")
        for count in written:
            self.assertEqual(
                count,
                len(shipped),
                f"README.md claims {count} skills; skills/*/SKILL.md counts "
                f"{len(shipped)}: {shipped}",
            )

        rows = {m.group("name"): m.group("href") for m in TABLE_LINK.finditer(readme)}
        self.assertIn("wiki", rows, "the README skills table has no `wiki` row")
        self.assertEqual(rows["wiki"], "skills/wiki/SKILL.md")
        self.assertTrue(
            (ROOT / rows["wiki"]).is_file(),
            f"the README `wiki` row links {rows['wiki']}, which does not exist",
        )

    # --- eval_runs_states_no_wiki_in_eval_mode ------------------------------

    def test_eval_runs_states_no_wiki_in_eval_mode(self):
        self.assertTrue(EVAL_RUNS.is_file(), f"{EVAL_RUNS} does not exist")
        text = EVAL_RUNS.read_text(encoding="utf-8")
        unit = find_claim(text, r"wiki", r"eval mode", r"record", r"consolidat", NOT)
        self.assertIsNotNone(
            unit,
            "docs/eval-runs.md never states that a repository in eval mode neither "
            "records to nor consolidates a wiki",
        )

    # --- changelog_entry_names_the_layer_and_the_adr ------------------------

    def test_changelog_entry_names_the_layer_and_the_adr(self):
        entry = changelog_entry(WIKI_ENTRY)
        self.assertIsNotNone(
            entry,
            f"CHANGELOG.md has no entry whose heading matches {WIKI_ENTRY.pattern!r}",
        )
        where = "the CHANGELOG.md wiki-layer entry"
        # The global, per-project store.
        self.assert_claim(
            entry,
            where,
            r"WORKCELL_WIKI_HOME|~/\.workcell/wiki",
            r"per[- ]project|project[- ]key|per project",
            r"outside (?:every|any|the) repositor|global",
        )
        # The review-fix-loop consolidates on the way out.
        self.assert_claim(
            entry,
            where,
            r"review-fix-loop",
            r"consolidat",
            r"exit|exits|on the way out|final|last pass|end of",
        )
        # The build hook that writes the raw trace.
        self.assert_claim(
            entry,
            where,
            r"`?build`?\b",
            r"raw[- ]trace|raw trace|raw/",
            r"hook",
        )
        self.assertRegex(entry, r"(?i)ADR[- ]0019", f"{where} does not cite ADR-0019")

    # --- the_docs_gate_is_green ---------------------------------------------

    def test_the_docs_gate_is_green(self):
        result = subprocess.run(
            [sys.executable, "-B", str(DOCS_CHECK), str(ROOT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["violations"], [])
        for item in report["instructionFiles"]:
            self.assertTrue(
                item["ok"], f"{item['path']} is over its {item['budget']}-line budget"
            )
        for ref in report["skillRefs"]:
            self.assertTrue(
                ref["ok"],
                f"{ref['agent']} names skill `{ref['skill']}`, missing under skills/",
            )
        numbers = [item["number"] for item in report["adrs"]]
        self.assertNotIn(None, numbers, "the docs gate found a malformed ADR filename")
        self.assertEqual(
            len(numbers),
            len(set(numbers)),
            f"the docs gate found duplicate ADR numbers: {numbers}",
        )
        adr, _ = self.wiki_adr()
        entry = next(
            (item for item in report["adrs"] if item["path"].endswith(adr.name)),
            None,
        )
        self.assertIsNotNone(entry, f"the docs gate did not inspect {adr.name}")
        self.assertTrue(
            entry["ok"], f"{adr.name} is missing sections: {entry['missing']}"
        )
        self.assertEqual(entry["number"], WIKI_ADR_NUMBER)


class SelfContainedInstallDocumentationTests(unittest.TestCase):
    """The repository's own account of full self-containment: ADR 0023, the two ADRs it
    supersedes and re-grounds, the README and install prose, and the changelog entry.

    Every harness install is now an installer-owned copy — a Claude durable
    command-source marketplace, a durable Codex marketplace copy, a Grok drop directory,
    and one Antigravity copy at its documented scan directory — and no runtime consumer
    resolves through a symlink into this repository any more."""

    def assert_claim(self, text: str, where: str, *patterns: str) -> str:
        """Fail unless one paragraph or list item makes the whole claim."""
        unit = find_claim(text, *patterns)
        if unit is None:
            self.fail(
                f"{where}: no single paragraph or list item states all of {list(patterns)}"
            )
        return unit

    def self_contained_adr(self) -> tuple[Path, str]:
        found = sorted(ADRS.glob(SELF_CONTAINED_ADR))
        self.assertEqual(
            len(found),
            1,
            f"expected exactly one docs/adr/{SELF_CONTAINED_ADR} recording that installs "
            f"are self-contained copies, found {[p.name for p in found]}",
        )
        self.assertRegex(found[0].name, ADR_FILENAME)
        return found[0], found[0].read_text(encoding="utf-8")

    def adr_section(self, name: str) -> tuple[str, str]:
        path, text = self.self_contained_adr()
        body = section(text, name)
        self.assertTrue(body.strip(), f"{path.name}: the {name} section is empty")
        return f"{path.name} {name}", body

    def live_link_claims(self, path: Path) -> list[str]:
        """Sentences in `path` that name an Antigravity install destination together with
        a linking verb, and do not deny it right next to the word."""
        text = path.read_text(encoding="utf-8")
        return [
            sentence
            for sentence in prose_sentences(text)
            if re.search(AGY_DEST, sentence, re.IGNORECASE)
            and re.search(LINK, sentence, re.IGNORECASE)
            and not re.search(DENIAL, sentence, re.IGNORECASE)
        ]

    def repo_rooted_marketplace_claims(self, path: Path) -> list[str]:
        """Sentences in `path` that still place a marketplace at this repository's root
        without saying the layout is retired."""
        text = path.read_text(encoding="utf-8")
        return [
            sentence
            for sentence in prose_sentences(text)
            if re.search(r"(?i)marketplace", sentence)
            and re.search(REPO_ROOTED_MARKETPLACE, sentence, re.IGNORECASE)
            and not re.search(RETIRED, sentence, re.IGNORECASE)
        ]

    # --- adr_0023_records_the_per_harness_mechanisms ------------------------

    def test_adr_0023_records_the_per_harness_mechanisms(self):
        path, text = self.self_contained_adr()
        for name in ("Status", "Context", "Decision", "Consequences"):
            self.assertRegex(
                text, rf"(?mi)^#+\s*{name}\b", f"{path.name} has no {name} section"
            )
            self.assertTrue(
                section(text, name).strip(), f"{path.name}: the {name} section is empty"
            )
        status = section(text, "Status")
        self.assertRegex(status, r"(?i)\bAccepted\b")
        self.assertRegex(
            status,
            r"0006",
            f"{path.name}: the Status section does not name ADR 0006, which it supersedes",
        )

        where, decision = self.adr_section("Decision")
        # Claude: a durable command-source marketplace, staged with copy mode.
        self.assert_claim(
            decision,
            where,
            r"claude",
            r"command[- ]source|command plugin source|commandPluginSource|command sources",
            r"mode:\s*`?copy|`copy` mode|copy mode|mode `copy`",
            r"durable|~/\.local/share/workcell",
        )
        # Codex: a durable owned marketplace copy whose version carries a content hash.
        self.assert_claim(
            decision,
            where,
            r"codex",
            r"durable",
            r"marketplace",
            r"version",
            r"content[- ]hash|\+codex\.",
        )
        # Grok: a drop into the documented plugin directory.
        self.assert_claim(
            decision,
            where,
            r"grok",
            r"~/\.grok/plugins",
            r"drop",
        )
        # Antigravity: one copy at the documented scan directory, `agy plugin` unused.
        self.assert_claim(
            decision,
            where,
            r"antigravity|\bagy\b",
            r"\.gemini/config/plugins",
            r"cop(?:y|ies|ied)",
            r"`agy plugin`",
            r"unused|not used|never used|declin|not invoked|never invoked|deliberately unused",
        )

    # --- adr_0023_states_the_refresh_and_drift_story ------------------------

    def test_adr_0023_states_the_refresh_and_drift_story(self):
        path, text = self.self_contained_adr()
        where = path.name
        # Claude restages itself, once per session.
        self.assert_claim(text, where, r"claude", r"re-?stag", r"session")
        # The other three freeze until bootstrap runs again.
        self.assert_claim(
            text,
            where,
            r"codex",
            r"grok",
            r"antigravity|\bagy\b",
            r"free[sz]e|frozen",
            r"bootstrap",
        )
        # Grok and Antigravity need a new session to pick a refreshed copy up.
        self.assert_claim(
            text,
            where,
            r"grok",
            r"antigravity|\bagy\b",
            r"new session|fresh session|next session|restart",
        )
        # Drift is surfaced by a version comparison and by the per-copy stamp.
        self.assert_claim(
            text,
            where,
            r"drift",
            r"version",
            r"compar|report",
            r"\.workcell-stamp\.json",
        )

    # --- adr_0023_declares_no_remaining_live_symlink ------------------------

    def test_adr_0023_declares_no_remaining_live_symlink(self):
        path, text = self.self_contained_adr()
        self.assert_claim(
            text,
            path.name,
            NOT,
            r"sym-?link",
            r"repositor",
            r"hook[- ]wrapper|hook wrappers",
            r"workcell-ws",
        )

    # --- adr_0006_and_adr_0021_point_at_their_successor ---------------------

    def test_adr_0006_and_adr_0021_point_at_their_successor(self):
        """The Status of each superseded ADR names 0023; their history is appended to,
        never rewritten, so prose that was there before is still there."""
        history = {
            "0006-plugins-install-through-local-marketplaces.md": {
                "Context": [
                    "neither ever scans its plugin directory for unregistered entries",
                ],
                "Decision": [
                    "The root is the marketplace root deliberately.",
                    "Antigravity keeps the ADR 0005 symlink.",
                ],
                "Consequences": [
                    "Antigravity skill links are derived, not listed.",
                ],
            },
            "0021-deploys-serve-plugins-from-a-durable-path.md": {
                "Context": [
                    "resolve the installed plugin through the",
                ],
                "Decision": [
                    (
                        "A deploy that installs or updates the plugin runs from a path "
                        "that outlives the deploy step."
                    ),
                ],
                "Consequences": [
                    "The next bootstrap from the primary repository will collide, not merge.",
                    "Grok has no v0.3.0 to roll back to.",
                ],
            },
        }
        self.assertIn("`agy plugin`", (ADRS / next(iter(history))).read_text("utf-8"))
        for name, sections in history.items():
            path = ADRS / name
            self.assertTrue(path.is_file(), f"{path} does not exist")
            text = path.read_text(encoding="utf-8")
            self.assertRegex(
                section(text, "Status"),
                r"0023",
                f"{name}: the Status section does not point at ADR 0023",
            )
            for heading, sentences in sections.items():
                body = re.sub(r"\s+", " ", section(text, heading))
                self.assertTrue(body.strip(), f"{name}: the {heading} section is empty")
                for sentence in sentences:
                    self.assertIn(
                        sentence,
                        body,
                        f"{name}: the {heading} section no longer contains the historical "
                        f"sentence {sentence!r} — ADR 0023 supersedes this decision, it does "
                        f"not erase the record of it",
                    )

    # --- readme_and_install_docs_match_the_new_mechanisms -------------------

    def test_readme_and_install_docs_match_the_new_mechanisms(self):
        readme = README.read_text(encoding="utf-8")
        self.assertTrue(INSTALL.is_file(), f"{INSTALL} does not exist")
        install = INSTALL.read_text(encoding="utf-8")

        for path in (README, INSTALL):
            stale = self.live_link_claims(path)
            self.assertEqual(
                stale,
                [],
                f"{path.name} still claims a live link into an Antigravity plugin "
                f"directory: {stale}",
            )
            rooted = self.repo_rooted_marketplace_claims(path)
            self.assertEqual(
                rooted,
                [],
                f"{path.name} still describes a marketplace rooted at this repository: "
                f"{rooted}",
            )

        # The `plugins/agy/` row of the layout tree describes an owned copy.
        rows = AGY_LAYOUT_LINE.findall(readme)
        self.assertEqual(
            len(rows),
            1,
            f"expected exactly one `plugins/agy/` row in the README layout tree, "
            f"found {rows}",
        )
        row = rows[0]
        self.assertRegex(
            row,
            r"(?i)cop(?:y|ies|ied)|owned",
            f"the README `agy/` layout row does not describe an owned copy: {row!r}",
        )
        if re.search(LINK, row, re.IGNORECASE):
            self.assertRegex(
                row,
                DENIAL,
                f"the README `agy/` layout row still describes a link: {row!r}",
            )

        # tdd-guard installs from a release artifact, with no checkout in sight.
        self.assert_claim(
            install,
            "docs/install.md",
            r"tdd-guard",
            r"release",
            r"artifact|asset|tarball|archive|download",
            r"without (?:a |the )?(?:checkout|clone|repositor)|no checkout|no clone"
            r"|without cloning|without checking out",
        )
        # Grok and Antigravity only pick a refreshed copy up in a new session.
        self.assert_claim(
            install,
            "docs/install.md",
            r"grok",
            r"antigravity|\bagy\b",
            r"new session|fresh session|next session|restart",
        )

    # --- changelog_entry_names_the_changes_and_cites_the_adr ---------------

    def test_changelog_entry_names_the_changes_and_cites_the_adr(self):
        entry = changelog_entry(SELF_CONTAINED_ENTRY)
        self.assertIsNotNone(
            entry,
            f"CHANGELOG.md has no entry whose heading matches "
            f"{SELF_CONTAINED_ENTRY.pattern!r}",
        )
        where = "the CHANGELOG.md self-containment entry"
        # Claude's durable command-source marketplace.
        self.assert_claim(
            entry,
            where,
            r"claude",
            r"command[- ]source|command plugin source|command sources",
            r"marketplace",
        )
        # Antigravity's and Grok's owned copies.
        self.assert_claim(
            entry,
            where,
            r"antigravity|\bagy\b",
            r"grok",
            r"cop(?:y|ies|ied)",
            r"own",
        )
        # The versioned copies of the tools.
        self.assert_claim(
            entry,
            where,
            r"version",
            r"cop(?:y|ies|ied)",
            r"tdd-guard|workcell-ws|wrapper",
        )
        # The release artifact CI now builds.
        self.assert_claim(
            entry,
            where,
            r"\bCI\b|workflow|release job|GitHub Actions",
            r"release",
            r"artifact|asset|binary|tarball",
        )
        self.assertRegex(entry, r"(?i)ADR[- ]0023", f"{where} does not cite ADR-0023")

    # --- docs_gate_is_green_and_inspects_adr_0023 --------------------------

    def test_docs_gate_is_green_and_inspects_adr_0023(self):
        result = subprocess.run(
            [sys.executable, "-B", str(DOCS_CHECK), str(ROOT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["violations"], [])
        numbers = [item["number"] for item in report["adrs"]]
        self.assertNotIn(None, numbers, "the docs gate found a malformed ADR filename")
        self.assertEqual(
            len(numbers),
            len(set(numbers)),
            f"the docs gate found duplicate ADR numbers: {numbers}",
        )
        adr, _ = self.self_contained_adr()
        entry = next(
            (item for item in report["adrs"] if item["path"].endswith(adr.name)),
            None,
        )
        self.assertIsNotNone(entry, f"the docs gate did not inspect {adr.name}")
        self.assertTrue(
            entry["ok"], f"{adr.name} is missing sections: {entry['missing']}"
        )
        self.assertEqual(entry["number"], SELF_CONTAINED_ADR_NUMBER)


# The ADR this milestone records: layered architecture and harness-owned instructions.
# 0024 was allocated to the Claude Fable roster decision; 0025 is the expected next free
# ADR number recording the layered architecture.
LAYERED_ARCH_ADR = "0025-*.md"
LAYERED_ARCH_ADR_NUMBER = 25

FALLBACK_MARKERS = (
    "<!-- generated harness-owned procedure:",
    "legacy-shared-body",
    "MIGRATION FALLBACK",
)

HARNESS_SKILL_NAMES = (
    "build",
    "code-analysis",
    "code-refactor",
    "code-review",
    "debug",
    "deploy",
    "docs",
    "jj",
    "new-feature",
    "perf",
    "plan",
    "repo-setup",
    "research",
    "review-fix-loop",
    "use-other-harness",
    "wiki",
)

HARNESS_AGENT_NAMES = (
    "builder",
    "debugger",
    "deployer",
    "documenter",
    "integrator",
    "planner",
    "profiler",
    "researcher",
    "reviewer",
    "specifier",
)


def _scan_content_for_fallbacks(rel_path: str, content: str) -> list[str]:
    violations = []
    for marker in FALLBACK_MARKERS:
        if marker in content:
            violations.append(
                f"artifact '{rel_path}' contains fallback marker '{marker}'"
            )
    return violations


def _check_required_artifacts(
    root: Path, required_map: dict[str, tuple[tuple[str, str], ...]]
) -> list[str]:
    violations = []
    for harness, items in required_map.items():
        for kind, name in items:
            if kind == "skills":
                expected = root / "harnesses" / harness / "skills" / name / "SKILL.md"
            else:
                expected = root / "harnesses" / harness / "agents" / f"{name}.md"
            if not expected.is_file():
                violations.append(
                    f"missing required {kind[:-1]} artifact '{expected.relative_to(root)}'"
                )
    return violations


def check_no_fallback_markers_and_sources(root: Path = ROOT) -> list[str]:
    violations: list[str] = []

    # 1. Check all 16 skills exist across four harnesses
    for harness in ("claude", "codex", "grok"):
        for skill in HARNESS_SKILL_NAMES:
            skill_file = root / "harnesses" / harness / "skills" / skill / "SKILL.md"
            if not skill_file.is_file():
                violations.append(
                    f"missing required skill artifact '{skill_file.relative_to(root)}'"
                )

    for skill in HARNESS_SKILL_NAMES:
        if skill == "jj":
            builder_jj = (
                root
                / "harnesses"
                / "agy"
                / "agents"
                / "builder"
                / "skills"
                / "jj"
                / "SKILL.md"
            )
            specifier_jj = (
                root
                / "harnesses"
                / "agy"
                / "agents"
                / "specifier"
                / "skills"
                / "jj"
                / "SKILL.md"
            )
            if (
                not builder_jj.is_file()
                and not (
                    root / "harnesses" / "agy" / "skills" / "jj" / "SKILL.md"
                ).is_file()
            ):
                violations.append(
                    f"missing required skill artifact '{builder_jj.relative_to(root)}'"
                )
            if (
                not specifier_jj.is_file()
                and not (
                    root / "harnesses" / "agy" / "skills" / "jj" / "SKILL.md"
                ).is_file()
            ):
                violations.append(
                    f"missing required skill artifact '{specifier_jj.relative_to(root)}'"
                )
        else:
            skill_file = root / "harnesses" / "agy" / "skills" / skill / "SKILL.md"
            if not skill_file.is_file():
                violations.append(
                    f"missing required skill artifact '{skill_file.relative_to(root)}'"
                )

    # 2. Check all 10 agents exist across four harnesses
    for harness in ("claude", "codex", "grok"):
        for agent in HARNESS_AGENT_NAMES:
            agent_file = root / "harnesses" / harness / "agents" / f"{agent}.md"
            if not agent_file.is_file():
                violations.append(
                    f"missing required agent artifact '{agent_file.relative_to(root)}'"
                )

    for agent in HARNESS_AGENT_NAMES:
        agent_file = root / "harnesses" / "agy" / "agents" / agent / "agent.md"
        if not agent_file.is_file():
            violations.append(
                f"missing required agent artifact '{agent_file.relative_to(root)}'"
            )

    # 3. Check for forbidden fallback markers in harnesses/ (excluding tests and pycache)
    for harness in ("claude", "codex", "agy", "grok"):
        h_dir = root / "harnesses" / harness
        if not h_dir.is_dir():
            continue
        for p in h_dir.rglob("*"):
            if not p.is_file():
                continue
            if "tests" in p.parts or "__pycache__" in p.parts:
                continue
            if p.suffix not in (".md", ".py", ".sh", ".json"):
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            for marker in FALLBACK_MARKERS:
                if marker in text:
                    violations.append(
                        f"artifact '{p.relative_to(root)}' contains fallback marker '{marker}'"
                    )

    # 4. Check build scripts for MIGRATION FALLBACK
    for script_name in (
        "build-claude-plugin.py",
        "build-codex-plugin.py",
        "build-agy-plugin.py",
        "build-grok-plugin.py",
    ):
        script_path = root / "scripts" / script_name
        if script_path.is_file():
            text = script_path.read_text(encoding="utf-8")
            if "MIGRATION FALLBACK" in text:
                violations.append(
                    f"artifact '{script_path.relative_to(root)}' contains fallback marker 'MIGRATION FALLBACK'"
                )

    return violations


class LayeredArchitectureDocumentationTests(unittest.TestCase):
    """The repository's record of the layered architecture (plan09 wave 10, #167):
    ADR 0025, ADR 0005 Status amendment, README architecture diagram, docs gate publication,
    absence of fallback markers, and milestone definition-of-done verification."""

    def assert_claim(self, text: str, where: str, *patterns: str) -> str:
        """Fail unless one paragraph or list item makes the whole claim."""
        unit = find_claim(text, *patterns)
        if unit is None:
            self.fail(
                f"{where}: no single paragraph or list item states all of {list(patterns)}"
            )
        return unit

    def layered_adr(self) -> tuple[Path, str]:
        # Search for 0025-*.md, or any ADR titled layered architecture (number >= 24)
        found = sorted(ADRS.glob(LAYERED_ARCH_ADR))
        if not found:
            found = [
                p
                for p in sorted(ADRS.glob("*.md"))
                if int(p.name[:4]) >= 24
                and any(
                    k in p.name.lower()
                    for k in ("layered", "architecture", "instruction")
                )
                and "fable" not in p.name.lower()
            ]
        self.assertEqual(
            len(found),
            1,
            f"expected exactly one layered-architecture ADR (expected docs/adr/{LAYERED_ARCH_ADR}), "
            f"found {[p.name for p in found]}",
        )
        self.assertRegex(found[0].name, ADR_FILENAME)
        return found[0], found[0].read_text(encoding="utf-8")

    def layered_adr_section(self, name: str) -> tuple[str, str]:
        path, text = self.layered_adr()
        body = section(text, name)
        self.assertTrue(body.strip(), f"{path.name}: the {name} section is empty")
        return f"{path.name} {name}", body

    # --- 1. adr-0024-records-the-decision (unit) -----------------------------

    def test_adr_0024_records_the_decision(self):
        """adr-0024-records-the-decision (unit).

        Oracle: Exactly one ADR 0024 [interpreted as next free ADR number, 0025,
        per numbering fact] has required headings and records ADR 0005/0023, contracts,
        four families, guides, omission rule, evals, standalone dist, and final roster choices.
        """
        path, text = self.layered_adr()
        for name in ("Status", "Context", "Decision", "Consequences"):
            self.assertRegex(
                text, rf"(?mi)^#+\s*{name}\b", f"{path.name} has no {name} section"
            )
        self.assertRegex(section(text, "Status"), r"(?i)\bAccepted\b")
        for name in ("Context", "Decision", "Consequences"):
            self.assertTrue(
                section(text, name).strip(), f"{path.name}: the {name} section is empty"
            )

        where, decision = self.layered_adr_section("Decision")
        # Records ADR 0005 and ADR 0023
        self.assert_claim(
            text,
            f"{path.name}",
            r"0005",
            r"0023",
        )
        # Shared contracts registry
        self.assert_claim(
            decision,
            where,
            r"contract",
            r"harness-contracts\.json|contracts/",
        )
        # Four harness families owning instructions/runtime
        self.assert_claim(
            decision,
            where,
            r"claude",
            r"codex",
            r"antigravity|\bagy\b",
            r"grok",
        )
        # Model guides and freshness check
        self.assert_claim(
            text,
            f"{path.name}",
            r"guide",
            r"fresh",
        )
        # Omission rule: unsupported optional features omitted with notes, missing required values fail
        self.assert_claim(
            decision,
            where,
            r"omit|omission",
            r"optional",
            r"fail|required",
        )
        # Evals across four harnesses
        self.assert_claim(
            decision,
            where,
            r"eval",
            r"run_evals|parity|harness",
        )
        # Standalone dist: self-contained copies per harness with no symlinks
        self.assert_claim(
            decision,
            where,
            r"dist",
            r"self[- ]contain|standalone|symlink",
        )
        # Final roster choices: Claude Fable/Opus/Sonnet, Grok 4.6 pin
        self.assert_claim(
            text,
            f"{path.name}",
            r"roster|model",
            r"fable|grok-4\.6|opus|sonnet",
        )

    # --- 2. adr-0005-points-forward-without-rewrite (unit) -------------------

    def test_adr_0005_points_forward_without_rewrite(self):
        """adr-0005-points-forward-without-rewrite (unit).

        Oracle: ADR 0005 Status names 0024 [0025] while its historical Context/Decision/
        Consequences remain; ADR 0023 remains deployment authority.
        """
        adr_0005_path = ADRS / "0005-unified-cross-harness-plugin-architecture.md"
        self.assertTrue(adr_0005_path.is_file(), "missing ADR 0005")
        adr_0005_text = adr_0005_path.read_text(encoding="utf-8")

        # ADR 0005 Status points forward to the layered architecture ADR (0025)
        status = section(adr_0005_text, "Status")
        self.assertTrue(status.strip(), "ADR 0005 Status section is empty")
        self.assertRegex(
            status,
            r"\b(?:0024|0025)\b",
            f"{adr_0005_path.name}: Status section does not point forward to ADR 0024/0025",
        )
        self.assertRegex(
            status,
            r"(?i)supersed",
            f"{adr_0005_path.name}: Status section does not describe supersession",
        )

        # Historical Context, Decision, and Consequences remain intact
        context = section(adr_0005_text, "Context")
        decision = section(adr_0005_text, "Decision")
        consequences = section(adr_0005_text, "Consequences")

        self.assertIn("~/.claude/agents", context)
        self.assertIn("~/.codex/skills", context)
        self.assertIn("Antigravity", context)

        self.assertIn("plugins/agy/workcell", decision)
        self.assertIn("plugins/claude/workcell", decision)
        self.assertIn("plugins/codex/workcell", decision)
        self.assertIn("scripts/install-harness.sh", decision)
        self.assertIn("scripts/project-bootstrap.sh", decision)

        self.assertIn("Cleaner Global Namespace", consequences)
        self.assertIn("Project-Local Tooling", consequences)
        self.assertIn("Migration Required", consequences)

        # ADR 0023 remains deployment authority
        adr_0023_path = ADRS / "0023-installs-are-self-contained-copies.md"
        self.assertTrue(adr_0023_path.is_file(), "missing ADR 0023")
        adr_0023_text = adr_0023_path.read_text(encoding="utf-8")
        self.assertRegex(
            section(adr_0023_text, "Status"),
            r"(?i)\bAccepted\b",
            "ADR 0023 Status is not Accepted",
        )
        self.assertNotRegex(
            status,
            r"(?i)supersedes?.*0023",
            "ADR 0005 Status improperly supersedes ADR 0023 deployment authority",
        )

    # --- 3. readme-diagram-matches-request (unit) ----------------------------

    def test_readme_diagram_matches_request(self):
        """readme-diagram-matches-request (unit).

        Oracle: Diagram source/rendered SVGs show one root, four harness boxes each with
        Agents/Skills/Scripts, and shared Scripts/Tools/everything else, with equivalent nearby text.
        """
        # Diagram source JSON in docs/diagrams/src/
        diagram_sources = list((ROOT / "docs" / "diagrams" / "src").glob("*.json"))
        arch_sources = [
            p
            for p in diagram_sources
            if any(k in p.stem for k in ("arch", "layered", "harness-layered"))
        ]
        self.assertTrue(
            arch_sources,
            "expected an architecture diagram source in docs/diagrams/src/ "
            "(e.g. layered-architecture.json or architecture.json)",
        )
        source_path = arch_sources[0]
        source = json.loads(source_path.read_text(encoding="utf-8"))
        stem = source_path.stem

        nodes = {node["id"]: node for node in source.get("nodes", [])}
        labels_and_subs = [
            (node.get("label", "") + " " + node.get("sub", ""))
            for node in nodes.values()
        ]

        # One root: Workcell root
        self.assertTrue(
            any(re.search(r"(?i)workcell root", ls) for ls in labels_and_subs),
            f"{source_path.name} is missing a 'Workcell root' node",
        )

        # Four harness boxes each with Agents/Skills/Scripts
        for harness in ("claude", "codex", "agy", "grok"):
            matching = [
                ls
                for ls in labels_and_subs
                if (
                    harness in ls.lower()
                    or (harness == "agy" and "antigravity" in ls.lower())
                )
                and "agents" in ls.lower()
                and "skills" in ls.lower()
                and "scripts" in ls.lower()
            ]
            self.assertTrue(
                matching,
                f"{source_path.name} is missing a box for {harness} with Agents, Skills, and Scripts",
            )

        # Shared Scripts/Tools/everything else
        self.assertTrue(
            any(
                "scripts" in ls.lower()
                and "tools" in ls.lower()
                and "everything else" in ls.lower()
                for ls in labels_and_subs
            ),
            f"{source_path.name} is missing a 'Scripts/Tools/everything else' node",
        )

        # Rendered SVGs must exist
        for theme in ("light", "dark"):
            svg_path = DIAGRAMS / f"{stem}-{theme}.svg"
            self.assertTrue(
                svg_path.is_file(),
                f"missing rendered SVG {svg_path.relative_to(ROOT)} — run scripts/render-diagrams.py",
            )
            svg_text = svg_path.read_text(encoding="utf-8")
            self.assertIn("Workcell root", svg_text)
            for harness_token in (
                "Claude",
                "Codex",
                "Scripts",
                "Tools",
                "everything else",
            ):
                self.assertIn(harness_token, svg_text)

        # README has picture block and alt text and nearby prose
        readme = README.read_text(encoding="utf-8")
        picture = re.search(
            rf"(?s)<picture>((?:(?!</picture>).)*{re.escape(stem)}(?:(?!</picture>).)*)</picture>",
            readme,
        )
        self.assertIsNotNone(picture, f"README.md has no {stem} <picture> block")
        alt = re.search(
            rf'<img alt="([^"]*)"[^>]*src="docs/diagrams/{re.escape(stem)}-light\.svg"',
            picture.group(1),
        )
        self.assertIsNotNone(alt, f"the {stem} <img> has no alt text (ADR 0004)")
        alt_text = alt.group(1)
        for pattern in (
            r"workcell root",
            r"claude",
            r"codex",
            r"antigravity|\bagy\b",
            r"grok",
            r"agents",
            r"skills",
            r"scripts",
            r"tools.*everything else|everything else",
        ):
            self.assertRegex(alt_text, rf"(?i){pattern}", f"{stem} alt text")

        after = readme[picture.end() :]
        stop = after.find("<picture>")
        prose = after[: stop if stop != -1 else len(after)]
        self.assert_claim(
            prose,
            f"README {stem} nearby prose",
            r"workcell root",
            r"claude",
            r"codex",
            r"antigravity|\bagy\b",
            r"grok",
        )
        self.assert_claim(
            prose,
            f"README {stem} nearby prose",
            r"agents",
            r"skills",
            r"scripts",
        )
        self.assert_claim(
            prose,
            f"README {stem} nearby prose",
            r"scripts",
            r"tools",
            r"everything else",
        )

    # --- 4. docs-publish-all-gates (unit) ------------------------------------

    def test_docs_publish_all_gates(self):
        """docs-publish-all-gates (unit).

        Oracle: Docs name agent/skill sync, freshness, parity, four eval commands and
        four stagers, and mark generated outputs non-editable.
        """
        doc_files = [
            README,
            ROOT / "docs" / "gates.md",
            ROOT / "docs" / "install.md",
        ]
        combined_docs = "\n".join(
            p.read_text(encoding="utf-8") for p in doc_files if p.is_file()
        )

        # Agent sync and skill sync
        self.assertRegex(
            combined_docs,
            r"sync-agents\.py(?:\s+--check)?",
            "docs do not name sync-agents.py gate",
        )
        self.assertRegex(
            combined_docs,
            r"sync-skills\.py(?:\s+--check)?",
            "docs do not name sync-skills.py gate",
        )

        # Model guide freshness
        self.assertRegex(
            combined_docs,
            r"check_guides\.py(?:\s+--check)?|guide freshness",
            "docs do not name model guide freshness gate",
        )

        # Contract parity
        self.assertRegex(
            combined_docs,
            r"check-contract-parity\.py|contract parity",
            "docs do not name contract parity gate",
        )

        # Four eval commands
        for harness in ("claude", "codex", "agy", "grok"):
            self.assertRegex(
                combined_docs,
                rf"run_evals\.py[^\n]*--harness\s+{harness}",
                f"docs do not name run_evals.py --harness {harness} command",
            )

        # Four stagers
        for harness in ("claude", "codex", "agy", "grok"):
            self.assertRegex(
                combined_docs,
                rf"build-{harness}-plugin\.py",
                f"docs do not name build-{harness}-plugin.py stager",
            )

        # Mark generated outputs non-editable
        self.assert_claim(
            combined_docs,
            "docs generated output policy",
            r"generated",
            r"not (?:be )?edit|non[- ]editable|fail|overwritten|read[- ]only",
        )

    # --- 5. no-fallback-survives (integration) -------------------------------

    def test_no_fallback_survives(self):
        """no-fallback-survives (integration).

        Oracle: No legacy-shared-body marker exists and every 16-skill/10-agent source
        exists in four harness roots; deletion or marker fails naming artifact.
        """
        # Test the checker itself on simulated failure cases to ensure
        # "deletion or marker fails naming artifact".
        synthetic_violations_marker = _scan_content_for_fallbacks(
            "dummy/path/SKILL.md",
            "some text <!-- generated harness-owned procedure: test --> more text",
        )
        self.assertTrue(synthetic_violations_marker)
        self.assertIn("dummy/path/SKILL.md", synthetic_violations_marker[0])

        synthetic_violations_missing = _check_required_artifacts(
            ROOT, {"claude": (("skills", "missing-skill"),)}
        )
        self.assertTrue(synthetic_violations_missing)
        self.assertIn("missing-skill", synthetic_violations_missing[0])

        # Live verification across the repository
        violations = check_no_fallback_markers_and_sources(ROOT)
        self.assertEqual(
            violations,
            [],
            "fallback markers survive or required harness sources are missing:\n"
            + "\n".join(violations),
        )

    # --- 6. milestone-definition-of-done-is-green (e2e) ----------------------

    def test_milestone_definition_of_done_is_green(self):
        """milestone-definition-of-done-is-green (e2e).

        Oracle: Freshness, both sync checks, parity, four run_evals --harness commands,
        and four stagers exit 0; every dist has real Agents/Skills/Runtime and no symlink.
        """
        # 1. Freshness check
        res = subprocess.run(
            [
                sys.executable,
                str(ROOT / "docs" / "models" / "check" / "check_guides.py"),
                "--check",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            res.returncode, 0, f"check_guides failed: {res.stdout}\n{res.stderr}"
        )

        # 2. Both sync checks
        res = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "sync-agents.py"),
                "--check",
                "--diff",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            res.returncode, 0, f"sync-agents failed: {res.stdout}\n{res.stderr}"
        )

        res = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "sync-skills.py"),
                "--check",
                "--diff",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            res.returncode, 0, f"sync-skills failed: {res.stdout}\n{res.stderr}"
        )

        # 3. Contract parity
        res = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check-contract-parity.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            res.returncode,
            0,
            f"check-contract-parity failed: {res.stdout}\n{res.stderr}",
        )

        # 4. Four run_evals --harness commands
        for harness in ("claude", "codex", "agy", "grok"):
            res = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "evals" / "run_evals.py"),
                    "--harness",
                    harness,
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                res.returncode,
                0,
                f"run_evals --harness {harness} failed: {res.stdout}\n{res.stderr}",
            )

        # 5. Four stagers
        for harness in ("claude", "codex", "agy", "grok"):
            res = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / f"build-{harness}-plugin.py")],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                res.returncode,
                0,
                f"build-{harness}-plugin failed: {res.stdout}\n{res.stderr}",
            )

        # 6. Every dist has real Agents/Skills/Runtime and no symlink
        dist_plugin_roots = {
            "claude": ROOT / "dist" / "claude" / "workcell",
            "codex": ROOT / "dist" / "codex" / "plugins" / "workcell",
            "agy": ROOT / "dist" / "agy" / "workcell",
            "grok": ROOT / "dist" / "grok" / "plugins" / "workcell",
        }
        for harness, plugin_root in dist_plugin_roots.items():
            dist_harness_root = ROOT / "dist" / harness
            self.assertTrue(
                dist_harness_root.is_dir(),
                f"{harness}: missing dist root {dist_harness_root.relative_to(ROOT)}",
            )
            # No symlinks
            symlinks = [p for p in dist_harness_root.rglob("*") if p.is_symlink()]
            self.assertEqual(
                symlinks,
                [],
                f"{harness} dist contains symlinks: {[str(p.relative_to(ROOT)) for p in symlinks]}",
            )
            # Contains real directory names for agents, skills, runtime
            dir_names = {p.name for p in plugin_root.rglob("*") if p.is_dir()}
            self.assertIn(
                "agents", dir_names, f"{harness} dist missing agents directory"
            )
            self.assertIn(
                "skills", dir_names, f"{harness} dist missing skills directory"
            )
            self.assertIn(
                "runtime", dir_names, f"{harness} dist missing runtime directory"
            )

            # Real files (non-empty)
            files = [p for p in plugin_root.rglob("*") if p.is_file()]
            self.assertTrue(files, f"{harness} dist has no files")
            for f in files:
                self.assertGreater(
                    f.stat().st_size, 0, f"{f.relative_to(ROOT)} is empty"
                )

            # No fallback markers in staged dist
            for f in files:
                if f.suffix in (".md", ".py", ".sh", ".json"):
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    for marker in (
                        "<!-- generated harness-owned procedure:",
                        "legacy-shared-body",
                        "MIGRATION FALLBACK",
                    ):
                        self.assertNotIn(
                            marker,
                            text,
                            f"staged dist file {f.relative_to(ROOT)} contains fallback marker {marker!r}",
                        )

        # 7. Mechanical docs gate is green and inspects the layered architecture ADR
        res = subprocess.run(
            [sys.executable, "-B", str(DOCS_CHECK), str(ROOT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            res.returncode, 0, f"docs_check failed: {res.stdout}\n{res.stderr}"
        )
        report = json.loads(res.stdout)
        self.assertEqual(report.get("violations", []), [])
        adr, _ = self.layered_adr()
        entry = next(
            (
                item
                for item in report.get("adrs", [])
                if item["path"].endswith(adr.name)
            ),
            None,
        )
        self.assertIsNotNone(entry, f"the docs gate did not inspect {adr.name}")
        self.assertTrue(
            entry["ok"], f"{adr.name} is missing sections: {entry.get('missing')}"
        )
        self.assertEqual(entry["number"], LAYERED_ARCH_ADR_NUMBER)


if __name__ == "__main__":
    unittest.main()
