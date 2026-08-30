import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATES = ROOT / "agents" / "gates"
README = ROOT / "README.md"
ADRS = ROOT / "docs" / "adr"


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


if __name__ == "__main__":
    unittest.main()
