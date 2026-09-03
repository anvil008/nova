"""Tests for scripts/check-harness-bodies.py.

Verifies:
  (a) lost-heading fires on missing headings and is suppressed by allowlist comment;
  (b) lost-command fires on missing script paths, tool invocations, and fenced command blocks;
  (c) lost-table fires on missing markdown tables;
  (d) broken-link and link-text-mismatch fire on broken and mismatched links;
  (e) missing-contract-string fires on missing required strings;
  (f) harness filtering, JSON output schema, and exit codes.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check-harness-bodies.py"


class CheckHarnessBodiesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temp_dir.name)
        # Create minimal structure
        (self.test_root / "contracts").mkdir(parents=True)
        (self.test_root / "skills" / "demo").mkdir(parents=True)
        (self.test_root / "agents" / "bodies").mkdir(parents=True)
        (self.test_root / "harnesses" / "claude" / "skills" / "demo").mkdir(
            parents=True
        )
        (self.test_root / "harnesses" / "claude" / "agents").mkdir(parents=True)

        contracts = {
            "schemaVersion": "1.0.0",
            "skills": [
                {
                    "name": "demo",
                    "invocation": "/workcell:demo",
                    "handoffSchema": "anvil.agent-handoff/v1",
                }
            ],
            "agents": [
                {
                    "name": "builder",
                    "handoffSchema": "anvil.agent-handoff/v1",
                }
            ],
        }
        (self.test_root / "contracts" / "harness-contracts.json").write_text(
            json.dumps(contracts), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_checker(self, *extra_args: str) -> tuple[int, list[dict] | str]:
        cmd = [sys.executable, str(CHECKER), "--root", str(self.test_root), *extra_args]
        res = subprocess.run(cmd, text=True, capture_output=True, check=False)
        if "--json" in extra_args:
            try:
                return res.returncode, json.loads(res.stdout)
            except json.JSONDecodeError:
                return res.returncode, res.stdout
        return res.returncode, res.stdout + res.stderr

    def test_lost_heading_fires_and_allowlist_suppresses(self) -> None:
        source = "# Demo\n\n## Procedure\n\nStep 1\n\n### Details\n\nDetailed info\n"
        (self.test_root / "skills" / "demo" / "SKILL.md").write_text(
            source, encoding="utf-8"
        )

        # Body missing ### Details
        body = (
            "# Demo\n\n"
            "Invocation: `/workcell:demo`\n\n"
            "Schema: `anvil.agent-handoff/v1`\n\n"
            "## Procedure\n\nStep 1\n"
        )
        body_file = (
            self.test_root / "harnesses" / "claude" / "skills" / "demo" / "SKILL.md"
        )
        body_file.write_text(body, encoding="utf-8")

        code, violations = self.run_checker("--json")
        self.assertEqual(code, 1)
        self.assertTrue(isinstance(violations, list))
        rules = [v["rule"] for v in violations]
        self.assertIn("lost-heading", rules)
        heading_v = next(v for v in violations if v["rule"] == "lost-heading")
        self.assertIn("### Details", heading_v["detail"])

        # Add allowlist comment
        body_suppressed = (
            "# Demo\n\n"
            "Invocation: `/workcell:demo`\n\n"
            "Schema: `anvil.agent-handoff/v1`\n\n"
            '<!-- body-check: drop-heading "### Details" intentionally simplified -->\n'
            "## Procedure\n\nStep 1\n"
        )
        body_file.write_text(body_suppressed, encoding="utf-8")

        code2, violations2 = self.run_checker("--json")
        self.assertEqual(code2, 0)
        self.assertEqual(violations2, [])

    def test_lost_command_script_path_and_invocation(self) -> None:
        source = (
            "# Demo\n\n"
            "Run python3 skills/demo/scripts/helper.py to generate data.\n\n"
            "Then execute `tdd-guard verify --all` and `jj git push`.\n"
        )
        (self.test_root / "skills" / "demo" / "SKILL.md").write_text(
            source, encoding="utf-8"
        )

        # Body missing script and tdd-guard verify
        body = (
            "# Demo\n\n"
            "Invocation: `/workcell:demo`\n\n"
            "Schema: `anvil.agent-handoff/v1`\n\n"
            "Then execute `jj git push`.\n"
        )
        body_file = (
            self.test_root / "harnesses" / "claude" / "skills" / "demo" / "SKILL.md"
        )
        body_file.write_text(body, encoding="utf-8")

        code, violations = self.run_checker("--json")
        self.assertEqual(code, 1)
        self.assertTrue(isinstance(violations, list))
        lost_cmds = [v for v in violations if v["rule"] == "lost-command"]
        details = " ".join(v["detail"] for v in lost_cmds)
        self.assertIn("skills/demo/scripts/helper.py", details)
        self.assertIn("tdd-guard verify", details)

    def test_tool_invocation_prose_vs_code(self) -> None:
        # Prose mentions like "gh issue", "jj repo", "jj improves" without backticks must NOT be extracted.
        # Backtick tokens and fenced command blocks MUST be extracted.
        source = (
            "# Demo\n\n"
            "We discussed gh issue tracking and how jj repo adoption jj improves workflow.\n\n"
            "Execute `tdd-guard verify --all` before pushing.\n\n"
            "```bash\njj status\n```\n"
        )
        (self.test_root / "skills" / "demo" / "SKILL.md").write_text(
            source, encoding="utf-8"
        )

        # Body satisfies backtick and fenced invocations, completely ignores prose tokens
        body = (
            "# Demo\n\n"
            "Invocation: `/workcell:demo`\n\n"
            "Schema: `anvil.agent-handoff/v1`\n\n"
            "Run `tdd-guard verify --all` and `jj status`.\n"
        )
        body_file = (
            self.test_root / "harnesses" / "claude" / "skills" / "demo" / "SKILL.md"
        )
        body_file.write_text(body, encoding="utf-8")

        code, violations = self.run_checker("--json")
        self.assertEqual(code, 0)
        self.assertEqual(violations, [])

        # If body omits the real backtick invocation, it fires
        body_missing = (
            "# Demo\n\n"
            "Invocation: `/workcell:demo`\n\n"
            "Schema: `anvil.agent-handoff/v1`\n\n"
            "Run `jj status`.\n"
        )
        body_file.write_text(body_missing, encoding="utf-8")
        code, violations = self.run_checker("--json")
        self.assertEqual(code, 1)
        self.assertTrue(any("tdd-guard verify" in v["detail"] for v in violations))
        self.assertFalse(any("gh issue" in v["detail"] for v in violations))
        self.assertFalse(any("jj repo" in v["detail"] for v in violations))

    def test_fenced_command_normalisation_and_comments_and_prompts(self) -> None:
        # Fenced command block with leading $ prompts and trailing # inline comments
        source = (
            "# Demo\n\n"
            "```bash\n"
            "$ ln -sf AGENTS.md CLAUDE.md      # and GEMINI.md where a harness wants its own name\n"
            "$ python3 skills/demo/scripts/helper.py --flag1   # trailing comment\n"
            "```\n"
        )
        (self.test_root / "skills" / "demo" / "SKILL.md").write_text(
            source, encoding="utf-8"
        )

        # Body matches normalized command / first token + script path without prompt or comment
        body = (
            "# Demo\n\n"
            "Invocation: `/workcell:demo`\n\n"
            "Schema: `anvil.agent-handoff/v1`\n\n"
            "Symlink instruction files: `ln -sf AGENTS.md CLAUDE.md`.\n"
            "Run helper: `python3 skills/demo/scripts/helper.py`.\n"
        )
        body_file = (
            self.test_root / "harnesses" / "claude" / "skills" / "demo" / "SKILL.md"
        )
        body_file.write_text(body, encoding="utf-8")

        code, violations = self.run_checker("--json")
        self.assertEqual(code, 0)
        self.assertEqual(violations, [])

    def test_lost_command_fenced_block(self) -> None:
        source = "# Demo\n\n```bash\nworkcell-ws setup-cluster --nodes 3\n```\n"
        (self.test_root / "skills" / "demo" / "SKILL.md").write_text(
            source, encoding="utf-8"
        )

        body = (
            "# Demo\n\n"
            "Invocation: `/workcell:demo`\n\n"
            "Schema: `anvil.agent-handoff/v1`\n\n"
            "Prose instructions without command.\n"
        )
        body_file = (
            self.test_root / "harnesses" / "claude" / "skills" / "demo" / "SKILL.md"
        )
        body_file.write_text(body, encoding="utf-8")

        code, violations = self.run_checker("--json")
        self.assertEqual(code, 1)
        self.assertTrue(isinstance(violations, list))
        lost_cmds = [v for v in violations if v["rule"] == "lost-command"]
        self.assertTrue(any("fenced command block" in v["detail"] for v in lost_cmds))

    def test_lost_table(self) -> None:
        source = (
            "# Demo\n\n| Option | Description |\n| --- | --- |\n| --fast | Run fast |\n"
        )
        (self.test_root / "skills" / "demo" / "SKILL.md").write_text(
            source, encoding="utf-8"
        )

        body = (
            "# Demo\n\n"
            "Invocation: `/workcell:demo`\n\n"
            "Schema: `anvil.agent-handoff/v1`\n\n"
            "No table here.\n"
        )
        body_file = (
            self.test_root / "harnesses" / "claude" / "skills" / "demo" / "SKILL.md"
        )
        body_file.write_text(body, encoding="utf-8")

        code, violations = self.run_checker("--json")
        self.assertEqual(code, 1)
        self.assertTrue(isinstance(violations, list))
        rules = [v["rule"] for v in violations]
        self.assertIn("lost-table", rules)

    def test_broken_link_and_link_text_mismatch(self) -> None:
        (self.test_root / "skills" / "demo" / "SKILL.md").write_text(
            "# Demo\n", encoding="utf-8"
        )

        # Create target existing file
        existing = (
            self.test_root / "harnesses" / "claude" / "skills" / "demo" / "target.md"
        )
        existing.write_text("# Target\n", encoding="utf-8")

        body = (
            "# Demo\n\n"
            "Invocation: `/workcell:demo`\n\n"
            "Schema: `anvil.agent-handoff/v1`\n\n"
            "- [Broken](nonexistent.md)\n"
            "- [other.md](target.md)\n"
        )
        body_file = (
            self.test_root / "harnesses" / "claude" / "skills" / "demo" / "SKILL.md"
        )
        body_file.write_text(body, encoding="utf-8")

        code, violations = self.run_checker("--json")
        self.assertEqual(code, 1)
        self.assertTrue(isinstance(violations, list))
        rules = [v["rule"] for v in violations]
        self.assertIn("broken-link", rules)
        self.assertIn("link-text-mismatch", rules)

    def test_missing_contract_string(self) -> None:
        # Agent builder missing required contract strings
        (self.test_root / "skills" / "demo" / "SKILL.md").write_text(
            "# Demo\n", encoding="utf-8"
        )
        (
            self.test_root / "harnesses" / "claude" / "skills" / "demo" / "SKILL.md"
        ).write_text(
            "# Demo\nInvocation: `/workcell:demo`\nSchema: `anvil.agent-handoff/v1`\n",
            encoding="utf-8",
        )

        (self.test_root / "agents" / "bodies" / "builder.md").write_text(
            "# Builder\n", encoding="utf-8"
        )
        body_file = self.test_root / "harnesses" / "claude" / "agents" / "builder.md"
        body_file.write_text("# Builder\nMissing contracts\n", encoding="utf-8")

        code, violations = self.run_checker("--json")
        self.assertEqual(code, 1)
        self.assertTrue(isinstance(violations, list))
        rules = [v["rule"] for v in violations]
        self.assertIn("missing-contract-string", rules)
        details = " ".join(v["detail"] for v in violations)
        self.assertIn("jj workspace list", details)
        self.assertIn("diff-review record", details)

    def test_harness_filter(self) -> None:
        (self.test_root / "skills" / "demo" / "SKILL.md").write_text(
            "# Demo\n", encoding="utf-8"
        )
        clean_body = (
            "# Demo\nInvocation: `/workcell:demo`\nSchema: `anvil.agent-handoff/v1`\n"
        )
        (
            self.test_root / "harnesses" / "claude" / "skills" / "demo" / "SKILL.md"
        ).write_text(clean_body, encoding="utf-8")

        (self.test_root / "harnesses" / "codex" / "skills" / "demo").mkdir(parents=True)
        bad_body = "# Demo\nMissing contracts\n"
        (
            self.test_root / "harnesses" / "codex" / "skills" / "demo" / "SKILL.md"
        ).write_text(bad_body, encoding="utf-8")

        # Filter claude -> clean
        code_claude, v_claude = self.run_checker("--harness", "claude", "--json")
        self.assertEqual(code_claude, 0)
        self.assertEqual(v_claude, [])

        # Filter codex -> violations
        code_codex, v_codex = self.run_checker("--harness", "codex", "--json")
        self.assertEqual(code_codex, 1)
        self.assertTrue(len(v_codex) > 0)


if __name__ == "__main__":
    unittest.main()
