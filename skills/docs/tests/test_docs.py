import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "docs_check.py"
EXAMPLES = ROOT / "examples"
GOOD_ADR = "## Status\nAccepted\n## Context\nx\n## Decision\ny\n## Consequences\nz\n"


def run(root, *args):
    return subprocess.run([sys.executable, "-B", str(SCRIPT), str(root), *map(str, args)],
                          text=True, capture_output=True)


class DocsCheckTests(unittest.TestCase):
    def test_clean_sample_passes(self):
        r = run(EXAMPLES / "sample-repo")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertTrue(out["ok"])
        self.assertEqual(out["violations"], [])

    def test_oversized_instruction_file_flagged(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "CLAUDE.md").write_text("\n".join(f"line {i}" for i in range(200)), encoding="utf-8")
            r = run(t, "--max-instruction-lines", "120")
            self.assertNotEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertFalse(out["ok"])
            self.assertTrue(any("CLAUDE.md" in v and "budget" in v for v in out["violations"]))

    def test_malformed_adr_missing_section(self):
        with tempfile.TemporaryDirectory() as t:
            adr = Path(t, "docs", "adr"); adr.mkdir(parents=True)
            (adr / "0001-thing.md").write_text("# 1. Thing\n## Status\nA\n## Context\nx\n## Decision\ny\n", encoding="utf-8")
            r = run(t)
            self.assertNotEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertTrue(any("0001-thing.md" in v and "Consequences" in v for v in out["violations"]))

    def test_duplicate_adr_number(self):
        with tempfile.TemporaryDirectory() as t:
            adr = Path(t, "docs", "adr"); adr.mkdir(parents=True)
            (adr / "0001-a.md").write_text("# 1. A\n" + GOOD_ADR, encoding="utf-8")
            (adr / "0001-b.md").write_text("# 1. B\n" + GOOD_ADR, encoding="utf-8")
            r = run(t)
            self.assertNotEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertTrue(any("duplicate" in v.lower() and "1" in v for v in out["violations"]))

    def test_bad_adr_filename_flagged(self):
        with tempfile.TemporaryDirectory() as t:
            adr = Path(t, "docs", "adr"); adr.mkdir(parents=True)
            (adr / "my-decision.md").write_text(GOOD_ADR, encoding="utf-8")
            r = run(t)
            self.assertNotEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertTrue(any("my-decision.md" in v for v in out["violations"]))

    def test_docs_agent_and_skill_declare_the_standard(self):
        agent = (ROOT.parents[1] / "agents" / "claude" / "docs.md").read_text(encoding="utf-8")
        self.assertTrue(agent.startswith("---\nname: docs\n"))
        for phrase in ("Update, don't duplicate", "lean", "ADR", "docs_check"):
            self.assertIn(phrase, agent)
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\nname: docs\n"))
        self.assertIn("docs_check", skill)

    def test_no_dangling_skill_refs(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "skills", "real").mkdir(parents=True)
            agents = Path(t, "agents", "x"); agents.mkdir(parents=True)
            (agents / "a.md").write_text(
                "---\nname: a\nskills:\n  - skills/real\n  - skills/ghost\n---\n# A\n\n## Skills\n\n"
                "- **`real`** — ok.\n- **`missing-one`** / **`real`** — gone.\n- **`real`**, **`comma-ghost`** — see `docs_check`.\n", encoding="utf-8")
            (agents / "b.md").write_text("---\nname: b\nskills: [skills/real, inline-ghost]\n---\n# B\n", encoding="utf-8")
            (agents / "c.md").write_text(
                "---\nname: c\nskills:\n  - real # known skill\n---\n# C\n\n## Skills\n\n"
                "  - **`indented-ghost`** — gone.\n\n## Skills\n\n- **`second-ghost`** — gone.\n",
                encoding="utf-8",
            )
            r = run(t)
            self.assertNotEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertFalse(out["ok"])
            self.assertTrue(any("agents/x/a.md" in v and "`missing-one`" in v for v in out["violations"]))
            self.assertTrue(any("agents/x/a.md" in v and "`ghost`" in v for v in out["violations"]))
            self.assertTrue(any("agents/x/a.md" in v and "`comma-ghost`" in v for v in out["violations"]))
            self.assertTrue(any("agents/x/b.md" in v and "`inline-ghost`" in v for v in out["violations"]))
            self.assertTrue(any("agents/x/c.md" in v and "`indented-ghost`" in v for v in out["violations"]))
            self.assertTrue(any("agents/x/c.md" in v and "`second-ghost`" in v for v in out["violations"]))
            self.assertEqual(len(out["violations"]), 6)
        out = json.loads(run(ROOT.parents[1]).stdout)
        self.assertGreaterEqual(len(out["skillRefs"]), 9)
        self.assertEqual([s for s in out["skillRefs"] if not s["ok"]], [])
        agent_dir = ROOT.parents[1] / "agents"
        for name in ("read-the-damn-docs", "find-docs", "grill-with-docs", "full-output-enforcement"):
            for path in agent_dir.rglob("*.md"):
                self.assertNotIn(name, path.read_text(encoding="utf-8"), f"{path} still references {name}")

    def test_agy_builder_has_stop_gate_or_manual_verify(self):
        agy = ROOT.parents[1] / "agents" / "agy" / "builder"
        cfg = json.loads((agy / "hooks.json").read_text(encoding="utf-8"))
        stop_hooks = cfg["swarm-guard"].get("Stop", [])
        has_stop_hook = any("build-hooks agy Stop" in h.get("command", "") for h in stop_hooks)
        agent = (agy / "agent.md").read_text(encoding="utf-8")
        has_manual = "Stop-time verify gate is manual" in agent and "run `tdd-guard verify" in agent
        self.assertTrue(has_stop_hook != has_manual, f"stop hook={has_stop_hook}, manual={has_manual}")

    def test_model_tiers_aligned(self):
        agy = ROOT.parents[1] / "agents" / "agy"
        main_agents = set()
        for path in sorted(agy.glob("*/agent.md")):
            front = path.read_text(encoding="utf-8").split("---")[1]
            if path.parent.name == "builder":
                self.assertEqual(re.search(r"(?m)^model:\s*(\S+)$", front).group(1), "pro")
            elif path.parent.name in {"code-reviewer", "docs"}:
                self.assertEqual(re.search(r"(?m)^model:\s*(\S+)$", front).group(1), "flash")
            if "mainAgent: true" in front:
                main_agents.add(path.parent.name)
        self.assertEqual(main_agents, {"builder", "docs"})

    def test_gemini_instruction_file_budget(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "GEMINI.md").write_text("\n".join(f"line {i}" for i in range(200)), encoding="utf-8")
            r = run(t, "--max-instruction-lines", "120")
            self.assertNotEqual(r.returncode, 0)
            out = json.loads(r.stdout)
            self.assertTrue(any("GEMINI.md" in v and "budget" in v for v in out["violations"]))

    def test_antigravity_builder_hooks_json(self):
        import json
        hooks_file = ROOT.parents[1] / "agents" / "agy" / "builder" / "hooks.json"
        self.assertTrue(hooks_file.exists())
        with open(hooks_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        
        self.assertIn("swarm-guard", cfg)
        guard_cfg = cfg["swarm-guard"]
        self.assertTrue(guard_cfg.get("enabled", False))
        
        self.assertIn("PreToolUse", guard_cfg)
        self.assertIn("PostToolUse", guard_cfg)

        pre_hooks = guard_cfg["PreToolUse"]
        post_hooks = guard_cfg["PostToolUse"]

        # Verify build-guard, build-format, build-lint and build-hooks are defined correctly
        pre_matchers = {h.get("matcher"): h.get("hooks") for h in pre_hooks if "matcher" in h}
        post_matchers = {h.get("matcher"): h.get("hooks") for h in post_hooks if "matcher" in h}

        # 1. PreToolUse must contain run_command matching build-guard
        self.assertIn("run_command", pre_matchers)
        guard_hook_cmd = [hk.get("command") for hk in pre_matchers["run_command"] if hk.get("type") == "command"]
        self.assertTrue(any("build-guard" in cmd for cmd in guard_hook_cmd))

        # 2. PreToolUse must contain edit matcher matching build-hooks
        edit_matcher = "write_to_file|replace_file_content|multi_replace_file_content"
        self.assertIn(edit_matcher, pre_matchers)
        edit_hook_cmd = [hk.get("command") for hk in pre_matchers[edit_matcher] if hk.get("type") == "command"]
        self.assertTrue(any("build-hooks" in cmd and "PreToolUse" in cmd for cmd in edit_hook_cmd))

        # 3. PostToolUse must contain run_command matcher matching build-hooks PostToolUse
        self.assertIn("run_command", post_matchers)
        cmd_hook_cmd = [hk.get("command") for hk in post_matchers["run_command"] if hk.get("type") == "command"]
        self.assertTrue(any("build-hooks" in cmd and "PostToolUse" in cmd for cmd in cmd_hook_cmd))

        # 4. PostToolUse must contain edit matcher matching build-format and build-lint
        self.assertIn(edit_matcher, post_matchers)
        edit_post_cmds = [hk.get("command") for hk in post_matchers[edit_matcher] if hk.get("type") == "command"]
        self.assertTrue(any("build-format" in cmd for cmd in edit_post_cmds))
        self.assertTrue(any("build-lint" in cmd for cmd in edit_post_cmds))

    def test_docs_check_adr_compliance(self):
        # Verifies docs_check.py passes on all ADRs in the real repository.
        repo_root = ROOT.parents[1]
        r = run(repo_root)
        self.assertEqual(r.returncode, 0, f"docs_check failed with stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
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
        
        # Check for go test -v ./...
        self.assertIn("go test -v ./...", content)
        
        # Check for hook tests
        self.assertIn("bash scripts/hooks/tests/test_hooks.sh", content)
        
        # Check for skill unit tests
        for skill in ("planner", "build", "code-review", "docs", "research"):
            expected_pattern = f"python3 -m unittest discover -s skills/{skill}/tests -p \"test_*.py\""
            self.assertIn(expected_pattern, content)
            
        # Check for docs check
        self.assertIn("skills/docs/scripts/docs_check.py", content)


if __name__ == "__main__":
    unittest.main()
