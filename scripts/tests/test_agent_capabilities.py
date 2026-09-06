"""Acceptance tests for generated agent capability boundaries."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "agents"


def frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    _, block, _ = text.split("---", 2)
    values = {}
    for line in block.strip().splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            values[key] = value.strip()
    return values


class AgentCapabilityTests(unittest.TestCase):
    def test_read_only_agents_declare_disallowed_tools(self):
        for name in ("reviewer", "researcher"):
            with self.subTest(agent=name):
                values = frontmatter(AGENTS / "claude" / f"{name}.md")
                denied = {item.strip() for item in values["disallowedTools"].split(",")}
                self.assertTrue({"Edit", "Write", "NotebookEdit", "Task"} <= denied)
                self.assertNotIn("maxTurns", values)

    def test_write_capable_agents_keep_edit_and_write_available(self):
        manifest = json.loads((AGENTS / "agents.json").read_text(encoding="utf-8"))
        for name in ("builder", "specifier", "deployer", "documenter"):
            with self.subTest(agent=name):
                config = manifest["agents"][name]["claude"]
                denied = config.get("disallowedTools", "")
                self.assertNotIn("Edit", denied)
                self.assertNotIn("Write", denied)
                values = frontmatter(AGENTS / "claude" / f"{name}.md")
                self.assertNotIn("disallowedTools", values)

    def test_researcher_body_and_generated_agents_teach_stance(self):
        paths = [
            AGENTS / "bodies" / "researcher.md",
            AGENTS / "claude" / "researcher.md",
            AGENTS / "codex" / "researcher.md",
            AGENTS / "agy" / "researcher" / "agent.md",
        ]
        for path in paths:
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                self.assertIn('"stance": "neutral"', text)
                for stance in ("supports", "contradicts", "neutral"):
                    self.assertIn(f"`{stance}`", text)
                self.assertIn("conflicting evidence", text)

    def test_dead_codex_sandbox_mode_is_absent(self):
        searched = [AGENTS, ROOT / "scripts" / "sync-agents.py"]
        for path in searched:
            files = path.rglob("*") if path.is_dir() else (path,)
            for candidate in files:
                if candidate.is_file():
                    if "__pycache__" in candidate.parts or candidate.suffix in {
                        ".pyc",
                        ".pyo",
                    }:
                        continue
                    with self.subTest(path=candidate.relative_to(ROOT)):
                        self.assertNotIn(
                            "sandbox_mode", candidate.read_text(encoding="utf-8")
                        )
        comments = "\n".join(
            json.loads((AGENTS / "models.json").read_text())["_comment"]
        )
        self.assertIn("codex exec", comments)
        self.assertIn("-s read-only", comments)
        self.assertIn("workcell-<agent> profile", comments)

    def test_generated_agents_are_in_sync(self):
        result = subprocess.run(
            ["python3", "scripts/sync-agents.py", "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
