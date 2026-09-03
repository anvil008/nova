"""Hermetic negative tests for the repository's agent/plugin generators."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(root: Path, script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", script, *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )


class GeneratorTests(unittest.TestCase):
    def copy_root(self, *paths: str) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        for relative in paths:
            source = ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
        return temporary, root

    def agent_variants(self, name: str) -> list[tuple[str, str]]:
        paths = {
            "body": ROOT / f"agents/bodies/{name}.md",
            "claude": ROOT / f"agents/claude/{name}.md",
            "codex": ROOT / f"agents/codex/{name}.md",
            "grok": ROOT / f"agents/grok/{name}.md",
            "agy": ROOT / f"agents/agy/{name}/agent.md",
        }
        return [
            (label, path.read_text(encoding="utf-8")) for label, path in paths.items()
        ]

    def assert_mode_section(self, text: str, mode: str) -> None:
        lines = text.splitlines()
        headings = [
            index
            for index, line in enumerate(lines)
            if line.startswith("### ") and mode in line
        ]
        self.assertEqual(len(headings), 1, f"expected one section heading for {mode!r}")
        start = headings[0] + 1
        end = next(
            (
                index
                for index in range(start, len(lines))
                if lines[index].startswith("## ")
            ),
            len(lines),
        )
        rules = [
            line
            for line in lines[start:end]
            if line.strip() and not line.startswith("#")
        ]
        self.assertTrue(rules, f"section {mode!r} has no rule line")

    def test_sync_agents_check_detects_real_drift(self):
        temporary, root = self.copy_root("agents", "scripts/sync-agents.py")
        with temporary:
            generated = run(root, "scripts/sync-agents.py")
            self.assertEqual(generated.returncode, 0, generated.stderr)
            path = root / "agents/claude/documenter.md"
            original = path.read_text(encoding="utf-8")
            path.write_text(original + "\ndrift\n", encoding="utf-8")
            drift = run(root, "scripts/sync-agents.py", "--check")
            self.assertEqual(drift.returncode, 1, drift.stderr)
            self.assertIn("agents/claude/documenter.md", drift.stdout)
            path.write_text(original, encoding="utf-8")
            clean = run(root, "scripts/sync-agents.py", "--check")
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)

    def test_sync_agents_rejects_malformed_inputs(self):
        mutations = {
            "nested only block": lambda root: (
                root / "agents/bodies/documenter.md"
            ).write_text(
                (root / "agents/bodies/documenter.md").read_text(encoding="utf-8")
                + "\n<!-- only:codex -->\n<!-- only:codex -->\n<!-- end -->\n<!-- end -->\n",
                encoding="utf-8",
            ),
            "unknown token": lambda root: (
                root / "agents/bodies/documenter.md"
            ).write_text(
                (root / "agents/bodies/documenter.md").read_text(encoding="utf-8")
                + "\n{{undefinedToken}}\n",
                encoding="utf-8",
            ),
            "missing gate": self._set_missing_gate,
            "empty agents": self._empty_agents,
        }
        for label, mutate in mutations.items():
            with self.subTest(case=label):
                temporary, root = self.copy_root("agents", "scripts/sync-agents.py")
                with temporary:
                    mutate(root)
                    result = run(root, "scripts/sync-agents.py", "--check")
                    self.assertEqual(
                        result.returncode, 2, result.stdout + result.stderr
                    )
                    self.assertRegex(result.stderr, r"documenter|agents\.json")

    @staticmethod
    def _set_missing_gate(root: Path) -> None:
        path = root / "agents/agents.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["agents"]["documenter"]["codex"]["gates"] = "does-not-exist"
        path.write_text(json.dumps(manifest), encoding="utf-8")

    @staticmethod
    def _empty_agents(root: Path) -> None:
        path = root / "agents/agents.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["agents"] = {}
        path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_sync_agent_models_rejects_invalid_manifest(self):
        mutations = {
            "claude effort": ("planner", "claude", "effort", "ultra"),
            "claude mode": ("builder", "claude", "mode", "invalid-mode"),
            "codex mode": ("builder", "codex", "mode", "de-prescribed"),
            "unknown harness": ("planner", "unknown-harness", "model", "x"),
            "agy model": ("planner", "agy", "model", "invalid"),
        }
        for label, (agent, harness, field, value) in mutations.items():
            with self.subTest(case=label):
                temporary, root = self.copy_root(
                    "agents", "scripts/sync-agent-models.py"
                )
                with temporary:
                    path = root / "agents/models.json"
                    manifest = json.loads(path.read_text(encoding="utf-8"))
                    manifest["agents"][agent].setdefault(harness, {})[field] = value
                    path.write_text(json.dumps(manifest), encoding="utf-8")
                    result = run(root, "scripts/sync-agent-models.py", "--check")
                    self.assertNotEqual(
                        result.returncode, 0, result.stdout + result.stderr
                    )
                    self.assertIn(f"{agent}/{harness}", result.stderr)

        temporary, root = self.copy_root("agents", "scripts/sync-agent-models.py")
        with temporary:
            clean = run(root, "scripts/sync-agent-models.py", "--check")
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)

    def test_sync_agent_models_mode_drift_and_sync(self):
        temporary, root = self.copy_root("agents", "scripts/sync-agent-models.py")
        with temporary:
            clean = run(root, "scripts/sync-agent-models.py", "--check")
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)

            # Mutate agents/models.json: remove mode from builder
            path = root / "agents/models.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("mode", manifest["agents"]["builder"]["claude"])
            del manifest["agents"]["builder"]["claude"]["mode"]
            path.write_text(json.dumps(manifest), encoding="utf-8")

            # Check detects drift because agents/claude/builder.md still has mode: de-prescribed
            drift = run(root, "scripts/sync-agent-models.py", "--check")
            self.assertEqual(drift.returncode, 1, drift.stdout + drift.stderr)
            self.assertIn("agents/claude/builder.md", drift.stdout)

            # Sync applies change and strips mode
            synced = run(root, "scripts/sync-agent-models.py")
            self.assertEqual(synced.returncode, 0, synced.stdout + synced.stderr)
            builder_md = (root / "agents/claude/builder.md").read_text(encoding="utf-8")
            frontmatter_stripped = builder_md.split("---", 2)[1]
            self.assertNotIn("mode:", frontmatter_stripped)

            # After sync, check passes cleanly
            clean2 = run(root, "scripts/sync-agent-models.py", "--check")
            self.assertEqual(clean2.returncode, 0, clean2.stdout + clean2.stderr)

            # Now restore mode: de-prescribed to models.json
            manifest["agents"]["builder"]["claude"]["mode"] = "de-prescribed"
            path.write_text(json.dumps(manifest), encoding="utf-8")

            # Check detects drift again (frontmatter is missing mode)
            drift2 = run(root, "scripts/sync-agent-models.py", "--check")
            self.assertEqual(drift2.returncode, 1, drift2.stdout + drift2.stderr)
            self.assertIn("agents/claude/builder.md", drift2.stdout)

            # Sync applies it back
            synced2 = run(root, "scripts/sync-agent-models.py")
            self.assertEqual(synced2.returncode, 0, synced2.stdout + synced2.stderr)
            builder_md2 = (root / "agents/claude/builder.md").read_text(
                encoding="utf-8"
            )
            frontmatter_restored = builder_md2.split("---", 2)[1]
            self.assertIn("mode: de-prescribed", frontmatter_restored)

            # Clean check
            clean3 = run(root, "scripts/sync-agent-models.py", "--check")
            self.assertEqual(clean3.returncode, 0, clean3.stdout + clean3.stderr)

    def test_handoff_contract_exists(self):
        contract = (ROOT / "agents/handoff.md").read_text(encoding="utf-8")
        for field in (
            "issue",
            "brief",
            "workspace",
            "branch",
            "base",
            "ownership",
            "mode",
            "sealedTests",
            "redCommand",
            "baselineCommand",
            "devServer",
            "approval",
        ):
            self.assertIn(f"`{field}`", contract)
        self.assertIn("`anvil.agent-handoff/v1`", contract)
        self.assertIn("exactly one of `done`, `blocked`, or `needs-decision`", contract)
        self.assertIn("`commands[]`", contract)
        self.assertIn("`commandId`", contract)
        self.assertIn("## Dispatch brief example", contract)
        self.assertIn("## Handoff record example", contract)

    def test_handoff_contract_carries_runtime_in_brief_and_record(self):
        contract = (ROOT / "agents/handoff.md").read_text(encoding="utf-8")
        brief, record = contract.split("## Handoff record", 1)
        self.assertIn("`runtime`", brief)
        self.assertIn("{launch, url, healthPath}", brief)
        self.assertIn("`evidence.runtime`", record)
        for field in (
            "surface",
            "commands",
            "observations",
            "consoleErrors",
            "screenshots",
        ):
            self.assertIn(field, record)
        self.assertIn('surface: "none"', record)

    def test_every_body_links_the_contract(self):
        bodies = sorted((ROOT / "agents/bodies").glob("*.md"))
        self.assertEqual(len(bodies), 10)
        for body in bodies:
            with self.subTest(body=body.name):
                text = body.read_text(encoding="utf-8")
                self.assertIn("anvil.agent-handoff/v1", text)
                self.assertIn("(../handoff.md)", text)
                name = body.stem
                for harness in ("claude", "codex", "grok"):
                    generated = (ROOT / f"agents/{harness}/{name}.md").read_text(
                        encoding="utf-8"
                    )
                    self.assertIn("(../handoff.md)", generated)
                agy = (ROOT / f"agents/agy/{name}/agent.md").read_text(encoding="utf-8")
                self.assertIn("(../../handoff.md)", agy)

    def test_builder_and_integrator_have_modes(self):
        for harness, text in self.agent_variants("builder"):
            with self.subTest(agent="builder", harness=harness):
                self.assert_mode_section(text, "mode: refactor")
                self.assert_mode_section(text, "mode: loop")
        for harness, text in self.agent_variants("integrator"):
            with self.subTest(agent="integrator", harness=harness):
                self.assert_mode_section(text, "mode: baseline")
        for name in ("builder", "specifier"):
            for harness, text in self.agent_variants(name):
                with self.subTest(agent=name, harness=harness, check="no-issue"):
                    self.assertIn("`issue` is `null`", text)
                    self.assertIn("instead of `Closes #<n>`", text)

    def test_reviewer_never_asks(self):
        for harness, reviewer in self.agent_variants("reviewer"):
            with self.subTest(harness=harness):
                self.assertIn("devServer", reviewer)
                self.assertNotIn("Ask before starting a dev server", reviewer)

    def test_planner_links_reference_contract(self):
        for harness, planner in self.agent_variants("planner"):
            with self.subTest(harness=harness):
                self.assertIn("skills/plan/references/sidecar-contract.md", planner)
                self.assertNotIn("skills/plan/SKILL.md", planner)

    def test_rationalization_tables_present(self):
        for name in ("builder", "specifier", "planner"):
            for harness, text in self.agent_variants(name):
                with self.subTest(agent=name, harness=harness):
                    section = text.split("## Rationalizations", 1)
                    self.assertEqual(len(section), 2)
                    table = section[1].split("\n## ", 1)[0]
                    rows = [line for line in table.splitlines() if line.startswith("|")]
                    self.assertGreaterEqual(len(rows), 6)
                    self.assertEqual(rows[0], "| Rationalization | Reality |")

    def test_every_builder_variant_verifies_runtime_between_green_and_review(self):
        """GREEN proves the tests pass; the review passes judge a change nobody has run
        unless runtime verification sits between them."""
        for harness, builder in self.agent_variants("builder"):
            with self.subTest(harness=harness):
                ordered = [
                    "tdd-guard verify",
                    "Prove it runs, not just passes",
                    "at most two passes",
                ]
                positions = []
                for phrase in ordered:
                    self.assertIn(phrase, builder, f"{harness}: missing {phrase!r}")
                    positions.append(builder.index(phrase))
                self.assertEqual(
                    positions,
                    sorted(positions),
                    f"{harness}: runtime step out of order",
                )
                self.assertIn("`evidence.runtime`", builder)

    def test_claude_builder_tool_is_agent(self):
        builder = (ROOT / "agents/claude/builder.md").read_text(encoding="utf-8")
        frontmatter = builder.split("---", 2)[1]
        tools = next(
            line.split(":", 1)[1]
            for line in frontmatter.splitlines()
            if line.startswith("tools:")
        )
        tool_names = [tool.strip() for tool in tools.split(",")]
        self.assertIn("Agent", tool_names)
        self.assertNotIn("Task", tool_names)
        # UI runtime verification runs through the agent-browser CLI (Bash), so no
        # MCP browser tool definitions may ride along and cost tokens per dispatch.
        self.assertIn("Bash", tool_names)
        self.assertNotIn("mcp__chrome-devtools__list_console_messages", tool_names)

    def test_no_agent_carries_mcp_browser_tools(self):
        # ADR 0012: every browser surface, including the debugger's diagnostics
        # (network waterfall, HAR, traces), runs through the agent-browser CLI.
        for name in ("builder", "reviewer", "debugger"):
            agent = (ROOT / f"agents/claude/{name}.md").read_text(encoding="utf-8")
            self.assertNotIn("mcp__", agent.split("---", 2)[1], name)

    def test_build_codex_plugin_rejects_malformed_sources_without_partial_output(self):
        for case in ("missing skill", "no frontmatter", "missing name"):
            with self.subTest(case=case):
                temporary, root = self.copy_root(
                    "contracts",
                    "harnesses/codex",
                    "scripts/build-codex-plugin.py",
                    "scripts/lib_dist.py",
                )
                with temporary:
                    if case == "missing skill":
                        (root / "harnesses/codex/skills/broken").mkdir()
                        expected = "harnesses/codex/skills/broken"
                    else:
                        path = root / "harnesses/codex/agents/builder.md"
                        text = path.read_text(encoding="utf-8")
                        if case == "no frontmatter":
                            path.write_text(
                                text.split("---\n", 2)[-1], encoding="utf-8"
                            )
                            expected = "harnesses/codex/agents/builder.md"
                        else:
                            path.write_text(
                                text.replace("name: builder\n", "", 1), encoding="utf-8"
                            )
                            expected = "harnesses/codex/agents/builder.md"
                    result = run(root, "scripts/build-codex-plugin.py")
                    self.assertNotEqual(
                        result.returncode, 0, result.stdout + result.stderr
                    )
                    self.assertIn(expected, result.stderr)
                    self.assertFalse((root / "dist/codex/plugins").exists())

    def test_codex_plugin_embeds_model_and_effort_routes(self):
        temporary, root = self.copy_root(
            "contracts",
            "harnesses/codex",
            "scripts/build-codex-plugin.py",
            "scripts/lib_dist.py",
        )
        with temporary:
            manifest_path = root / "harnesses/codex/runtime/models.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["agents"]["builder"]["codex"] = {
                "model": "gpt-test-builder",
                "effort": "xhigh",
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = run(root, "scripts/build-codex-plugin.py")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            staged = root / "dist/codex/plugins/workcell/skills"
            for relative in ("build/SKILL.md", "agent-builder/SKILL.md"):
                text = (staged / relative).read_text(encoding="utf-8")
                self.assertIn("Codex specialist routing (generated)", text)
                self.assertIn(
                    "`builder`: `model=gpt-test-builder`, `reasoning_effort=xhigh`",
                    text,
                )
                self.assertIn("do not silently fall back", text)
                self.assertIn("`fork_turns` to `none`", text)

    def test_codex_plugin_rejects_invalid_runtime_effort(self):
        temporary, root = self.copy_root(
            "contracts",
            "harnesses/codex",
            "scripts/build-codex-plugin.py",
            "scripts/lib_dist.py",
        )
        with temporary:
            manifest_path = root / "harnesses/codex/runtime/models.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["agents"]["builder"].setdefault("codex", {})["effort"] = "ultra"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = run(root, "scripts/build-codex-plugin.py")
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("builder/codex effort", result.stderr)
            self.assertFalse((root / "dist/codex/plugins").exists())


if __name__ == "__main__":
    unittest.main()
