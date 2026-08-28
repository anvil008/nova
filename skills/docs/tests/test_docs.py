import json
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

    def test_agent_skills_parity(self):
        # 1. Docs agents (claude, codex, agy) must contain 'grill-with-docs' skill
        claude_docs = (ROOT.parents[1] / "agents" / "claude" / "docs.md").read_text(encoding="utf-8")
        codex_docs = (ROOT.parents[1] / "agents" / "codex" / "docs.md").read_text(encoding="utf-8")
        agy_docs = (ROOT.parents[1] / "agents" / "agy" / "docs" / "agent.md").read_text(encoding="utf-8")
        
        self.assertIn("grill-with-docs", claude_docs)
        self.assertIn("grill-with-docs", codex_docs)
        self.assertIn("grill-with-docs", agy_docs)

        # 2. Research agents (claude, codex, agy) must contain 'read-the-damn-docs' and 'find-docs'
        claude_res = (ROOT.parents[1] / "agents" / "claude" / "research.md").read_text(encoding="utf-8")
        codex_res = (ROOT.parents[1] / "agents" / "codex" / "research.md").read_text(encoding="utf-8")
        agy_res = (ROOT.parents[1] / "agents" / "agy" / "research" / "agent.md").read_text(encoding="utf-8")

        self.assertIn("read-the-damn-docs", claude_res)
        self.assertIn("find-docs", claude_res)
        self.assertIn("read-the-damn-docs", codex_res)
        self.assertIn("find-docs", codex_res)
        self.assertIn("read-the-damn-docs", agy_res)
        self.assertIn("find-docs", agy_res)

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


if __name__ == "__main__":
    unittest.main()
