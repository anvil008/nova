import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "docs_check.py"
EXAMPLES = ROOT / "examples"
VISUAL_README = EXAMPLES / "visual-readme.md"
GOOD_ADR = "## Status\nAccepted\n## Context\nx\n## Decision\ny\n## Consequences\nz\n"


def run(root, *args):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(root), *map(str, args)],
        text=True,
        capture_output=True,
        check=False,
    )


class DocsCheckTests(unittest.TestCase):
    def test_clean_sample_passes(self):
        r = run(EXAMPLES / "sample-repo")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertTrue(out["ok"])
        self.assertEqual(out["violations"], [])

    def test_oversized_instruction_file_flagged(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "CLAUDE.md").write_text(
                "\n".join(f"line {i}" for i in range(200)), encoding="utf-8"
            )
            r = run(t, "--max-instruction-lines", "120")
            self.assertNotEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertFalse(out["ok"])
            self.assertTrue(
                any("CLAUDE.md" in v and "budget" in v for v in out["violations"])
            )

    def test_malformed_adr_missing_section(self):
        with tempfile.TemporaryDirectory() as t:
            adr = Path(t, "docs", "adr")
            adr.mkdir(parents=True)
            (adr / "0001-thing.md").write_text(
                "# 1. Thing\n## Status\nA\n## Context\nx\n## Decision\ny\n",
                encoding="utf-8",
            )
            r = run(t)
            self.assertNotEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertTrue(
                any(
                    "0001-thing.md" in v and "Consequences" in v
                    for v in out["violations"]
                )
            )

    def test_duplicate_adr_number(self):
        with tempfile.TemporaryDirectory() as t:
            adr = Path(t, "docs", "adr")
            adr.mkdir(parents=True)
            (adr / "0001-a.md").write_text("# 1. A\n" + GOOD_ADR, encoding="utf-8")
            (adr / "0001-b.md").write_text("# 1. B\n" + GOOD_ADR, encoding="utf-8")
            r = run(t)
            self.assertNotEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertTrue(
                any("duplicate" in v.lower() and "1" in v for v in out["violations"])
            )

    def test_bad_adr_filename_flagged(self):
        with tempfile.TemporaryDirectory() as t:
            adr = Path(t, "docs", "adr")
            adr.mkdir(parents=True)
            (adr / "my-decision.md").write_text(GOOD_ADR, encoding="utf-8")
            r = run(t)
            self.assertNotEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertTrue(any("my-decision.md" in v for v in out["violations"]))

    def test_documenter_agent_and_docs_skill_declare_the_standard(self):
        agent = (ROOT.parents[1] / "agents" / "claude" / "documenter.md").read_text(
            encoding="utf-8"
        )
        self.assertTrue(agent.startswith("---\nname: documenter\n"))
        for phrase in ("Update, don't duplicate", "lean", "ADR", "docs_check"):
            self.assertIn(phrase, agent)
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\nname: docs\n"))
        self.assertIn("docs_check", skill)

    def test_no_dangling_skill_refs(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "skills", "real").mkdir(parents=True)
            agents = Path(t, "agents", "x")
            agents.mkdir(parents=True)
            (agents / "a.md").write_text(
                "---\nname: a\nskills:\n  - skills/real\n  - skills/ghost\n---\n# A\n\n## Skills\n\n"
                "- **`real`** — ok.\n- **`missing-one`** / **`real`** — gone.\n- **`real`**, **`comma-ghost`** — see `docs_check`.\n",
                encoding="utf-8",
            )
            (agents / "b.md").write_text(
                "---\nname: b\nskills: [skills/real, inline-ghost]\n---\n# B\n",
                encoding="utf-8",
            )
            (agents / "c.md").write_text(
                "---\nname: c\nskills:\n  - real # known skill\n---\n# C\n\n## Skills\n\n"
                "  - **`indented-ghost`** — gone.\n\n## Skills\n\n- **`second-ghost`** — gone.\n",
                encoding="utf-8",
            )
            r = run(t)
            self.assertNotEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertFalse(out["ok"])
            self.assertTrue(
                any(
                    "agents/x/a.md" in v and "`missing-one`" in v
                    for v in out["violations"]
                )
            )
            self.assertTrue(
                any("agents/x/a.md" in v and "`ghost`" in v for v in out["violations"])
            )
            self.assertTrue(
                any(
                    "agents/x/a.md" in v and "`comma-ghost`" in v
                    for v in out["violations"]
                )
            )
            self.assertTrue(
                any(
                    "agents/x/b.md" in v and "`inline-ghost`" in v
                    for v in out["violations"]
                )
            )
            self.assertTrue(
                any(
                    "agents/x/c.md" in v and "`indented-ghost`" in v
                    for v in out["violations"]
                )
            )
            self.assertTrue(
                any(
                    "agents/x/c.md" in v and "`second-ghost`" in v
                    for v in out["violations"]
                )
            )
            self.assertEqual(len(out["violations"]), 6)
        out = json.loads(run(ROOT.parents[1]).stdout)
        self.assertGreaterEqual(len(out["skillRefs"]), 9)
        self.assertEqual([s for s in out["skillRefs"] if not s["ok"]], [])
        agent_dir = ROOT.parents[1] / "agents"
        for name in (
            "read-the-damn-docs",
            "find-docs",
            "grill-with-docs",
            "full-output-enforcement",
        ):
            for path in agent_dir.rglob("*.md"):
                self.assertNotIn(
                    name,
                    path.read_text(encoding="utf-8"),
                    f"{path} still references {name}",
                )

    def test_agy_builder_has_stop_gate_or_manual_verify(self):
        agy = ROOT.parents[1] / "agents" / "agy" / "builder"
        cfg = json.loads((agy / "hooks.json").read_text(encoding="utf-8"))
        stop_hooks = cfg["workcell-guard"].get("Stop", [])
        has_stop_hook = any(
            "build-hooks agy Stop" in h.get("command", "") for h in stop_hooks
        )
        agent = (agy / "agent.md").read_text(encoding="utf-8")
        has_manual = (
            "Stop-time verify gate is manual" in agent
            and "run `tdd-guard verify" in agent
        )
        self.assertTrue(
            has_stop_hook != has_manual,
            f"stop hook={has_stop_hook}, manual={has_manual}",
        )

    def test_model_tiers_aligned(self):
        """agents/models.json is the single source for model and thinking level.
        Every agent file must agree with it, on every harness."""
        repo = ROOT.parents[1]
        manifest = json.loads(
            (repo / "agents" / "models.json").read_text(encoding="utf-8")
        )
        defaults = manifest["defaults"]
        keys = {
            "claude": {"model": "model", "effort": "effort"},
            "codex": {"model": "model", "effort": "model_reasoning_effort"},
            "agy": {"model": "model"},
        }
        for agent, spec in manifest["agents"].items():
            if agent.startswith("_"):
                continue
            for harness, fields in keys.items():
                path = (
                    repo / "agents" / "agy" / agent / "agent.md"
                    if harness == "agy"
                    else repo / "agents" / harness / f"{agent}.md"
                )
                with self.subTest(agent=agent, harness=harness):
                    self.assertTrue(path.exists(), path)
                    front = path.read_text(encoding="utf-8").split("---")[1]
                    merged = dict(defaults.get(harness, {}))
                    merged.update(
                        {
                            k: v
                            for k, v in spec.get(harness, {}).items()
                            if not k.startswith("_")
                        }
                    )
                    for knob, key in fields.items():
                        if knob not in merged:
                            continue
                        found = re.search(rf"(?m)^{key}:\s*(\S+)$", front)
                        self.assertIsNotNone(found, f"{path}: no {key}")
                        self.assertEqual(found.group(1), merged[knob], f"{path}: {key}")

        agy = repo / "agents" / "agy"
        main_agents = set()
        for path in sorted(agy.glob("*/agent.md")):
            front = path.read_text(encoding="utf-8").split("---")[1]
            if "mainAgent: true" in front:
                main_agents.add(path.parent.name)
        self.assertEqual(
            main_agents,
            {
                "builder",
                "reviewer",
                "documenter",
                "researcher",
                "planner",
                "specifier",
                "integrator",
                "deployer",
                "debugger",
                "profiler",
            },
        )

    def test_every_skill_declares_itself(self):
        """A skill is discovered by directory, so its frontmatter name must match the
        directory or the harness and the docs disagree about what it is called."""
        skills = ROOT.parents[1] / "skills"
        found = sorted(p for p in skills.glob("*/SKILL.md"))
        self.assertTrue(found, "no skills found")
        for path in found:
            with self.subTest(skill=path.parent.name):
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"), f"{path}: no frontmatter")
                end = text.find("\n---\n", 3)
                self.assertNotEqual(end, -1, f"{path}: unterminated frontmatter")
                front = text[4:end]
                name = re.search(r"(?m)^name:\s*(\S+)$", front)
                self.assertIsNotNone(name, f"{path}: no name")
                self.assertEqual(
                    name.group(1), path.parent.name, f"{path}: name/dir mismatch"
                )
                description = re.search(r"(?m)^description:\s*(\S.*)$", front)
                self.assertIsNotNone(description, f"{path}: no description")

    def test_entry_point_skills_publish_their_distinguishing_contract(self):
        """The four entry points differ by what they refuse to do. If those clauses
        drift out, they collapse into four names for the same pipeline."""
        skills = ROOT.parents[1] / "skills"
        required = {
            "code-refactor": (
                "Behaviour does not change",
                "no test file is modified",
                "same `tdd-guard` state machine",
                "`kind: baseline` seal",
                "code-analysis",
            ),
            "code-analysis": (
                "failure scenario",
                "specifier",
                "refute",
                "code-refactor",
            ),
            "new-feature": (
                "at least five clarifying questions",
                "Skip this only when the user explicitly says to skip",
                "needs-decision",
            ),
            "repo-setup": (
                "AGENTS.md",
                "bootstrap-project.sh",
                "jj git init --colocate",
            ),
            "debug": (
                # Reproduction is the gate: without it a "fix" is a guess that shipped.
                "No reproduction, no fix",
                "debugger",
                "specifier",
                "code-analysis",
            ),
            "perf": (
                # A benchmark harness is a precondition, not a nice-to-have.
                "No harness, no run",
                "outside the baseline's spread",
                "profiler",
                "no write tools",
            ),
        }
        for skill, phrases in required.items():
            path = skills / skill / "SKILL.md"
            with self.subTest(skill=skill):
                self.assertTrue(path.exists(), path)
                text = path.read_text(encoding="utf-8")
                for phrase in phrases:
                    self.assertIn(phrase, text, f"{skill}: missing {phrase!r}")
                # Every entry point is orchestration: it dispatches, it does not do.
                self.assertIn("You are the orchestrator", text)
                self.assertIn("0007-primary-agent-is-a-pure-orchestrator", text)

    def test_gemini_instruction_file_budget(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "GEMINI.md").write_text(
                "\n".join(f"line {i}" for i in range(200)), encoding="utf-8"
            )
            r = run(t, "--max-instruction-lines", "120")
            self.assertNotEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertTrue(
                any("GEMINI.md" in v and "budget" in v for v in out["violations"])
            )

    def test_linked_instruction_file_is_counted_once(self):
        """`repo-setup` keeps one real `AGENTS.md` and links the other harnesses' names
        at it. A link is the same file, so it is reported once, under the real path."""
        with tempfile.TemporaryDirectory() as t:
            Path(t, "AGENTS.md").write_text("# Project\n", encoding="utf-8")
            Path(t, "CLAUDE.md").symlink_to("AGENTS.md")
            r = run(t)
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout)
            self.assertEqual(
                [f["path"] for f in out["instructionFiles"]], ["AGENTS.md"]
            )
            self.assertEqual(out["violations"], [])

    def test_readme_contract_parity(self):
        agents = [
            ROOT.parents[1] / "agents" / "claude" / "documenter.md",
            ROOT.parents[1] / "agents" / "codex" / "documenter.md",
            ROOT.parents[1] / "agents" / "agy" / "documenter" / "agent.md",
        ]
        required = (
            "what the repository does",
            "why it exists",
            "shortest viable quickstart",
            "compact visual",
            "nearby textual explanation",
            "meaningful labels",
            "concise, plain-language prose",
        )
        contracts = []
        for path in agents:
            with self.subTest(path=path):
                content = path.read_text(encoding="utf-8")
                for phrase in required:
                    self.assertIn(phrase, content)
                contracts.append(
                    content.split("## README contract\n\n", 1)[1].split("\n\n", 1)[0]
                )
        self.assertTrue(all(contract == contracts[0] for contract in contracts[1:]))
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("## README contract", skill)
        self.assertIn("agents/documenter/agent.md", skill)

    def test_visual_readme_has_textual_equivalent(self):
        content = VISUAL_README.read_text(encoding="utf-8")
        self.assertIn("```mermaid", content)
        self.assertIn("flowchart LR", content)
        self.assertIn("In words:", content)
        explanation = content.split("In words:", 1)[1].lower()
        for label in ("contributor", "test", "package", "user"):
            self.assertIn(label, explanation)

    def test_docs_gate_does_not_semantically_lint_readmes(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "README.md").write_text("# Tiny\n", encoding="utf-8")
            r = run(t)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(json.loads(r.stdout)["ok"])

    def test_antigravity_builder_hooks_json(self):
        import json

        hooks_file = ROOT.parents[1] / "agents" / "agy" / "builder" / "hooks.json"
        self.assertTrue(hooks_file.exists())
        with open(hooks_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        self.assertIn("workcell-guard", cfg)
        guard_cfg = cfg["workcell-guard"]
        self.assertTrue(guard_cfg.get("enabled", False))

        self.assertIn("PreToolUse", guard_cfg)
        self.assertIn("PostToolUse", guard_cfg)

        pre_hooks = guard_cfg["PreToolUse"]
        post_hooks = guard_cfg["PostToolUse"]

        # Verify build-guard, build-format, build-lint and build-hooks are defined correctly
        pre_matchers = {
            h.get("matcher"): h.get("hooks") for h in pre_hooks if "matcher" in h
        }
        post_matchers = {
            h.get("matcher"): h.get("hooks") for h in post_hooks if "matcher" in h
        }

        # 1. PreToolUse must contain run_command matching build-guard
        self.assertIn("run_command", pre_matchers)
        guard_hook_cmd = [
            hk.get("command")
            for hk in pre_matchers["run_command"]
            if hk.get("type") == "command"
        ]
        self.assertTrue(any("build-guard" in cmd for cmd in guard_hook_cmd))

        # 2. PreToolUse must contain edit matcher matching build-hooks
        edit_matcher = "write_to_file|replace_file_content|multi_replace_file_content"
        self.assertIn(edit_matcher, pre_matchers)
        edit_hook_cmd = [
            hk.get("command")
            for hk in pre_matchers[edit_matcher]
            if hk.get("type") == "command"
        ]
        self.assertTrue(
            any("build-hooks" in cmd and "PreToolUse" in cmd for cmd in edit_hook_cmd)
        )

        # 3. PostToolUse must contain run_command matcher matching build-hooks PostToolUse
        self.assertIn("run_command", post_matchers)
        cmd_hook_cmd = [
            hk.get("command")
            for hk in post_matchers["run_command"]
            if hk.get("type") == "command"
        ]
        self.assertTrue(
            any("build-hooks" in cmd and "PostToolUse" in cmd for cmd in cmd_hook_cmd)
        )

        # 4. PostToolUse must contain edit matcher matching build-format and build-lint
        self.assertIn(edit_matcher, post_matchers)
        edit_post_cmds = [
            hk.get("command")
            for hk in post_matchers[edit_matcher]
            if hk.get("type") == "command"
        ]
        self.assertTrue(any("build-format" in cmd for cmd in edit_post_cmds))
        self.assertTrue(any("build-lint" in cmd for cmd in edit_post_cmds))

    def test_docs_check_adr_compliance(self):
        # Verifies docs_check.py passes on all ADRs in the real repository.
        repo_root = ROOT.parents[1]
        r = run(repo_root)
        self.assertEqual(
            r.returncode,
            0,
            f"docs_check failed with stdout:\n{r.stdout}\nstderr:\n{r.stderr}",
        )
        out = json.loads(r.stdout)
        self.assertTrue(out["ok"])
        self.assertEqual(out["violations"], [])

    def test_ci_workflow_lint_steps(self):
        # Verifies .github/workflows/ci.yml contains the required lint and doc checks.
        ci_yaml_path = ROOT.parents[1] / ".github" / "workflows" / "ci.yml"
        self.assertTrue(ci_yaml_path.exists(), "ci.yml does not exist")
        content = ci_yaml_path.read_text(encoding="utf-8")

        # Check for go vet
        self.assertIn("go vet ./...", content)

        # Check for uncached race-enabled Go tests and glob-discovered shell coverage.
        self.assertIn("go test -count=1 -race ./...", content)
        self.assertIn("scripts/hooks/tests/test_*.sh scripts/tests/test_*.sh", content)
        self.assertIn('bash "$test_script"', content)
        self.assertIn(
            "python3 -m unittest discover -s scripts/tests -p 'test_*.py'", content
        )

        # Every present and future skill suite is discovered; none is hard-coded.
        self.assertIn("for d in skills/*/tests; do", content)
        self.assertIn("python3 -m unittest discover -s \"$d\" -p 'test_*.py'", content)
        self.assertNotRegex(
            content, r"python3 -m unittest discover -s skills/[^\s]+/tests"
        )

        # Python and lint tooling are explicit CI gates.
        self.assertIn("actions/setup-python@v5", content)
        self.assertRegex(content, r"python-version:\s*[\"']?3\.13[\"']?")
        self.assertIn("ruff check skills/", content)
        self.assertIn(
            "shellcheck -S warning scripts/*.sh scripts/hooks/build-*", content
        )

        # Check for docs check
        self.assertIn("skills/docs/scripts/docs_check.py", content)

    def test_readme_documents_plugin_architecture(self):
        # The layout section, the one wrapper path per harness it has to name, and both
        # bootstrap commands. Bare ".claude"/".codex" would match anywhere and never fail.
        readme = (ROOT.parents[1] / "README.md").read_text(encoding="utf-8")
        self.assertIn("## How the repository is laid out", readme)
        for phrase in (
            "plugins/agy/",
            "plugins/claude/",
            "plugins/codex/",
            "antigravity-cli",
            "scripts/bootstrap-tools.sh --install",
            "scripts/bootstrap-plugins.sh --uninstall",
        ):
            self.assertIn(phrase, readme)

    def test_readme_diagrams_are_generated_svg_with_text_equivalents(self):
        # The README's visuals are rendered files, not Mermaid fences (ADR 0010), and
        # each one keeps the adjacent text equivalent ADR 0004 requires.
        repo = ROOT.parents[1]
        readme = (repo / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("```mermaid", readme)
        blocks = re.findall(r"<picture>.*?</picture>", readme, re.DOTALL)
        self.assertTrue(blocks, "README has no diagram")
        self.assertEqual(len(blocks), readme.count("<picture>"))
        for block in blocks:
            dark = re.search(
                r'<source media="\(prefers-color-scheme: dark\)" srcset="(\S+)">', block
            )
            light = re.search(r'<img alt="([^"]+)" src="(\S+)"', block)
            self.assertIsNotNone(dark, block)
            self.assertIsNotNone(light, block)
            self.assertTrue(dark.group(1).endswith("-dark.svg"), block)
            self.assertTrue(light.group(2).endswith("-light.svg"), block)
            self.assertTrue(light.group(1).strip(), "empty alt text")
            for reference in (dark.group(1), light.group(2)):
                self.assertTrue((repo / reference).is_file(), reference)
            following = readme[readme.index(block) + len(block) :].split("\n")[:11]
            self.assertTrue(
                any("In words" in line for line in following),
                f"no text equivalent near {light.group(2)}",
            )

    def test_every_diagram_svg_is_titled_and_described(self):
        svgs = sorted((ROOT.parents[1] / "docs" / "diagrams").glob("*.svg"))
        self.assertTrue(svgs, "no rendered diagrams")
        for path in svgs:
            with self.subTest(diagram=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertRegex(text, r"<title[^>]*>[^<]+</title>")
                self.assertRegex(text, r"<desc[^>]*>[^<]+</desc>")

    def test_render_diagrams_check_catches_a_hand_edited_svg(self):
        # A gate only means something if it fails: copy the renderer and its output,
        # change one byte, and the --check that passes on the tree must name the file.
        repo = ROOT.parents[1]
        script = repo / "scripts" / "render-diagrams.py"
        clean = subprocess.run(
            [sys.executable, "-B", str(script), "--check"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "scripts").mkdir()
            shutil.copy(script, root / "scripts" / "render-diagrams.py")
            shutil.copytree(repo / "docs" / "diagrams", root / "docs" / "diagrams")
            # The renderer reads its layout engine out of the plan skill (ADR 0022),
            # so the copied tree has to carry that too.
            shutil.copytree(
                repo / "skills" / "plan" / "scripts",
                root / "skills" / "plan" / "scripts",
                ignore=shutil.ignore_patterns("__pycache__"),
            )
            edited = root / "docs" / "diagrams" / "how-work-moves-light.svg"
            edited.write_text(
                edited.read_text(encoding="utf-8").replace(
                    "</svg>", "<!-- edit --></svg>"
                ),
                encoding="utf-8",
            )
            drifted = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(root / "scripts" / "render-diagrams.py"),
                    "--check",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(drifted.returncode, 1, drifted.stdout + drifted.stderr)
            self.assertIn("how-work-moves-light.svg", drifted.stderr)


if __name__ == "__main__":
    unittest.main()
