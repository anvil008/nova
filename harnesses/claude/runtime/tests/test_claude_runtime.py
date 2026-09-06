"""Acceptance tests for Claude-native runtime scripts and hooks (#156).

Tests that:
1. claude-runtime-is-self-contained (integration): Generated manifest, hooks, and
   wrappers resolve inside the family and stage with no symlink or repository dependency.
2. interactive-features-do-not-break-headless (unit): Interactive/experimental features
   are capability-guarded or noted as omitted, and headless eval loads contracts without them.
3. claude-hooks-preserve-gates (integration): Generated hook events invoke the shared
   guard at Pre/Post/Stop/SubagentStop gate points; missing required hook values fail closed.
"""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

TEST_FILE = Path(__file__).resolve()
RUNTIME_DIR = TEST_FILE.parents[1]
HARNESS_DIR = TEST_FILE.parents[2]
REPO_ROOT = TEST_FILE.parents[4]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class ClaudeRuntimeTests(unittest.TestCase):
    """Authoritative acceptance tests for GitHub issue #156 (ClaudeRuntime)."""

    def test_claude_runtime_is_self_contained(self) -> None:
        """claude-runtime-is-self-contained (integration):

        Generated manifest/hooks/wrappers resolve inside the family and stage
        with no symlink or repository dependency.
        """
        # 1. Manifest resolves inside the family and is valid JSON
        manifest_path = RUNTIME_DIR / ".claude-plugin" / "plugin.json"
        self.assertTrue(
            manifest_path.is_file(),
            f"Missing plugin manifest at {manifest_path}",
        )
        self.assertFalse(
            manifest_path.is_symlink(),
            f"Manifest {manifest_path} must not be a symlink",
        )
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest_data.get("name"), "workcell")
        self.assertTrue(
            manifest_data.get("version"),
            "Manifest must declare non-empty version",
        )
        self.assertTrue(
            manifest_data.get("description"),
            "Manifest must declare non-empty description",
        )

        # 2. Hooks resolve inside the family
        hooks_path = RUNTIME_DIR / "hooks" / "hooks.json"
        self.assertTrue(
            hooks_path.is_file(),
            f"Missing hooks manifest at {hooks_path}",
        )
        self.assertFalse(
            hooks_path.is_symlink(),
            f"Hooks manifest {hooks_path} must not be a symlink",
        )
        hooks_data = json.loads(hooks_path.read_text(encoding="utf-8"))
        self.assertIn("hooks", hooks_data)

        # All hook commands must use ${CLAUDE_PLUGIN_ROOT}/scripts/ and resolve to executable files in RUNTIME_DIR/scripts
        scripts_dir = RUNTIME_DIR / "scripts"
        self.assertTrue(
            scripts_dir.is_dir(),
            f"Missing scripts directory at {scripts_dir}",
        )
        for gate, event_list in hooks_data["hooks"].items():
            for entry in event_list:
                for hook in entry.get("hooks", []):
                    cmd = hook.get("command", "")
                    self.assertTrue(
                        cmd.startswith("${CLAUDE_PLUGIN_ROOT}/scripts/"),
                        f"Hook command {cmd!r} in {gate} must start with '${{CLAUDE_PLUGIN_ROOT}}/scripts/'",
                    )
                    self.assertNotIn(
                        "~/.local/bin",
                        cmd,
                        f"Hook command {cmd!r} must not reference ~/.local/bin",
                    )
                    self.assertNotIn(
                        "..",
                        cmd,
                        f"Hook command {cmd!r} must not use relative parent navigation",
                    )
                    rel_script = cmd.split()[0].replace(
                        "${CLAUDE_PLUGIN_ROOT}/", ""
                    )
                    script_file = RUNTIME_DIR / rel_script
                    self.assertTrue(
                        script_file.is_file(),
                        f"Hook script {script_file} referenced by command {cmd!r} does not exist",
                    )
                    self.assertTrue(
                        os.access(script_file, os.X_OK),
                        f"Hook script {script_file} must be executable",
                    )

        # 3. No symlinks anywhere in RUNTIME_DIR
        runtime_symlinks = [
            str(p.relative_to(RUNTIME_DIR))
            for p in RUNTIME_DIR.rglob("*")
            if p.is_symlink()
        ]
        self.assertEqual(
            runtime_symlinks,
            [],
            f"harnesses/claude/runtime must contain zero symlinks; found: {runtime_symlinks}",
        )

        # 4. Staging validation: build-claude-plugin.py stages with no symlinks or repo dependencies
        builder_script = REPO_ROOT / "scripts" / "build-claude-plugin.py"
        self.assertTrue(builder_script.is_file(), f"Missing {builder_script}")
        proc = subprocess.run(
            [sys.executable, str(builder_script)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"scripts/build-claude-plugin.py failed with exit code {proc.returncode}:\n{proc.stderr}",
        )

        staged_dir = REPO_ROOT / "dist" / "claude" / "workcell"
        self.assertTrue(
            staged_dir.is_dir(), f"Staged directory {staged_dir} was not created"
        )

        # Staged tree has zero symlinks
        staged_symlinks = [
            str(p.relative_to(staged_dir))
            for p in staged_dir.rglob("*")
            if p.is_symlink()
        ]
        self.assertEqual(
            staged_symlinks,
            [],
            f"Staged dist/claude/workcell contains symlinks: {staged_symlinks}",
        )

        # Stamp has sourceRoot == 'harnesses/claude'
        stamp_file = staged_dir / ".workcell-stamp.json"
        self.assertTrue(stamp_file.is_file(), f"Missing stamp {stamp_file}")
        stamp_data = json.loads(stamp_file.read_text(encoding="utf-8"))
        self.assertEqual(stamp_data.get("sourceRoot"), "harnesses/claude")
        self.assertEqual(stamp_data.get("name"), "workcell")

        # Staged hooks resolve internally
        staged_hooks = json.loads(
            (staged_dir / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )
        for gate, event_list in staged_hooks.get("hooks", {}).items():
            for entry in event_list:
                for hook in entry.get("hooks", []):
                    cmd = hook.get("command", "")
                    rel_script = cmd.split()[0].replace(
                        "${CLAUDE_PLUGIN_ROOT}/", ""
                    )
                    staged_script = staged_dir / rel_script
                    self.assertTrue(
                        staged_script.is_file(),
                        f"Staged script {staged_script} referenced by {cmd!r} in {gate} is missing",
                    )
                    self.assertTrue(
                        os.access(staged_script, os.X_OK),
                        f"Staged script {staged_script} must be executable",
                    )

        # Staged files must have no repo checkout path dependencies
        repo_root_str = str(REPO_ROOT)
        for path in staged_dir.rglob("*"):
            if path.is_file() and not path.name.endswith(".pyc"):
                try:
                    content = path.read_text(encoding="utf-8")
                    self.assertNotIn(
                        repo_root_str,
                        content,
                        f"Staged file {path.relative_to(staged_dir)} contains hardcoded repo path {repo_root_str}",
                    )
                except UnicodeDecodeError:
                    pass

        # 5. Ownership Seam: harnesses/claude/runtime owns its manifests/hooks;
        # scripts/harness_generation.py must not copy them from plugins/claude.
        # Desired runtime for claude should only copy shared guards from scripts/hooks and handoff.md.
        from scripts import harness_generation

        source_code = inspect.getsource(harness_generation.desired_runtime)
        self.assertNotIn(
            'root / "plugins/claude/.claude-plugin"',
            source_code,
            "scripts/harness_generation.py: desired_runtime must not copy .claude-plugin from plugins/claude; "
            "harnesses/claude/runtime must own its manifest directly (#156)",
        )
        self.assertNotIn(
            'root / "plugins/claude/hooks"',
            source_code,
            "scripts/harness_generation.py: desired_runtime must not copy hooks from plugins/claude; "
            "harnesses/claude/runtime must own its hooks directly (#156)",
        )

    def test_interactive_features_do_not_break_headless(self) -> None:
        """interactive-features-do-not-break-headless (unit):

        Interactive/experimental features are capability-guarded or noted as omitted,
        and headless eval loads contracts without them.
        """
        # 1. Capability evaluation metadata must exist under harnesses/claude/runtime
        capabilities_path = RUNTIME_DIR / "capabilities.json"
        self.assertTrue(
            capabilities_path.is_file(),
            f"Missing runtime capabilities metadata at {capabilities_path}: "
            "must evaluate interactive/experimental features against headless capability (#156)",
        )
        self.assertFalse(
            capabilities_path.is_symlink(),
            f"Capabilities file {capabilities_path} must not be a symlink",
        )

        caps = json.loads(capabilities_path.read_text(encoding="utf-8"))
        self.assertEqual(caps.get("harness"), "claude")
        features = caps.get("features", {})

        # The six evaluated features from issue #156:
        # skill isolation, forks, subagents, worktrees, Workflow surfaces, command hooks
        required_features = {
            "skill_isolation",
            "forks",
            "subagents",
            "worktrees",
            "workflow_surfaces",
            "command_hooks",
        }
        for feat in required_features:
            self.assertIn(
                feat,
                features,
                f"Capabilities metadata {capabilities_path} missing evaluation for feature {feat!r}",
            )

        # Interactive/experimental features must be marked as not supported in headless mode,
        # omitted or capability-guarded, and carry non-empty limitation notes.
        for feat in ("forks", "workflow_surfaces"):
            info = features[feat]
            self.assertFalse(
                info.get("supported", True) and info.get("headless", True),
                f"Interactive feature {feat!r} must not be declared as supported in headless mode",
            )
            note = (
                info.get("limitation_note")
                or info.get("omission_note")
                or info.get("note")
                or ""
            )
            self.assertTrue(
                len(note.strip()) > 0,
                f"Feature {feat!r} is omitted or guarded but lacks a non-empty limitation note",
            )

        # Worktrees and skill isolation: external/guarded in headless mode with limitation notes
        for feat in ("skill_isolation", "worktrees"):
            info = features[feat]
            note = (
                info.get("limitation_note")
                or info.get("omission_note")
                or info.get("note")
                or ""
            )
            self.assertTrue(
                len(note.strip()) > 0,
                f"Feature {feat!r} must document its headless status/limitation note",
            )

        # Supported headless capabilities
        for feat in ("subagents", "command_hooks"):
            info = features[feat]
            self.assertTrue(
                info.get("supported", False) or info.get("headless", False),
                f"Feature {feat!r} must be marked as supported in Claude headless mode",
            )

        # 2. Headless eval loads contracts without interactive features
        carrier = RUNTIME_DIR / "contracts.json"
        self.assertTrue(
            carrier.is_file(), f"Missing contracts carrier at {carrier}"
        )
        contracts_data = json.loads(carrier.read_text(encoding="utf-8"))
        contract = contracts_data.get("contract", {})

        # All 12 skills and 10 agents must load without interactive requirements
        skills = contract.get("skills", [])
        self.assertEqual(
            len(skills), 12, f"Expected 12 skills in contracts, got {len(skills)}"
        )
        for sk in skills:
            reqs = sk.get("requiredValues", {}).get("claude", [])
            # Must not require interactive features like forks or workflows
            self.assertNotIn(
                "forks",
                reqs,
                f"Skill {sk['name']} must not require forks in headless contract",
            )
            self.assertNotIn(
                "workflow_surfaces",
                reqs,
                f"Skill {sk['name']} must not require workflow_surfaces",
            )
            self.assertNotIn(
                "workflows",
                reqs,
                f"Skill {sk['name']} must not require workflows",
            )
            self.assertNotIn(
                "interactive",
                reqs,
                f"Skill {sk['name']} must not require interactive features",
            )

        agents = contract.get("agents", [])
        self.assertEqual(
            len(agents), 10, f"Expected 10 agents in contracts, got {len(agents)}"
        )
        for ag in agents:
            reqs = ag.get("requiredValues", {}).get("claude", [])
            self.assertNotIn(
                "forks",
                reqs,
                f"Agent {ag['name']} must not require forks in headless contract",
            )
            self.assertNotIn(
                "workflow_surfaces",
                reqs,
                f"Agent {ag['name']} must not require workflow_surfaces",
            )

        # Headless evaluator command must be headless (e.g. claude -p)
        headless_cmd = caps.get("headless_command", [])
        self.assertTrue(
            any("claude" in c for c in headless_cmd)
            and any("-p" in c for c in headless_cmd),
            f"Headless command in capabilities must specify claude -p; got {headless_cmd}",
        )

    def test_claude_hooks_preserve_gates(self) -> None:
        """claude-hooks-preserve-gates (integration):

        Generated hook events invoke the shared guard at the same
        Pre/Post/Stop/SubagentStop gate points; a missing required hook value fails.
        """
        # 1. hooks.json registers all four gate points
        hooks_path = RUNTIME_DIR / "hooks" / "hooks.json"
        self.assertTrue(
            hooks_path.is_file(), f"Missing hooks file at {hooks_path}"
        )
        hooks_data = json.loads(hooks_path.read_text(encoding="utf-8"))
        hooks_map = hooks_data.get("hooks", {})

        gate_points = {"PreToolUse", "PostToolUse", "Stop", "SubagentStop"}
        for gp in gate_points:
            self.assertIn(
                gp, hooks_map, f"hooks.json must register gate point {gp!r}"
            )

        # SubagentStop must be scoped to ^workcell:builder$
        subagent_stops = hooks_map.get("SubagentStop", [])
        self.assertTrue(
            any(
                entry.get("matcher") == "^workcell:builder$"
                for entry in subagent_stops
            ),
            "SubagentStop hook must include matcher '^workcell:builder$'",
        )

        # 2. Every hook entry declares required schema values
        for gp, entries in hooks_map.items():
            for entry in entries:
                for h in entry.get("hooks", []):
                    self.assertEqual(
                        h.get("type"),
                        "command",
                        f"Hook in {gp} must have type 'command'",
                    )
                    self.assertTrue(
                        h.get("command"),
                        f"Hook in {gp} must have non-empty command",
                    )
                    timeout = h.get("timeout")
                    self.assertIsInstance(
                        timeout, int, f"Hook timeout in {gp} must be integer"
                    )
                    self.assertGreater(
                        timeout, 0, f"Hook timeout in {gp} must be positive"
                    )

        # 3. Missing required hook values fail closed (exit code 2)
        guard_script = RUNTIME_DIR / "scripts" / "build-guard"
        hooks_script = RUNTIME_DIR / "scripts" / "build-hooks"
        self.assertTrue(
            os.access(guard_script, os.X_OK),
            f"{guard_script} must be executable",
        )
        self.assertTrue(
            os.access(hooks_script, os.X_OK),
            f"{hooks_script} must be executable",
        )

        # build-guard fails closed on missing command or empty payload
        proc_empty = subprocess.run(
            [str(guard_script), "claude"],
            input="",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            proc_empty.returncode,
            2,
            f"build-guard claude with empty payload must exit 2 (fail closed); got {proc_empty.returncode}",
        )

        # build-guard fails closed on non-JSON payload
        proc_invalid = subprocess.run(
            [str(guard_script), "claude"],
            input="not-json",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            proc_invalid.returncode,
            2,
            f"build-guard claude with non-JSON payload must exit 2; got {proc_invalid.returncode}",
        )

        # build-guard fails closed on payload missing command field
        proc_nocmd = subprocess.run(
            [str(guard_script), "claude"],
            input=json.dumps({"tool_input": {}}),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            proc_nocmd.returncode,
            2,
            f"build-guard claude with missing command must exit 2; got {proc_nocmd.returncode}",
        )

        # build-hooks fails closed on missing event argument
        proc_no_event = subprocess.run(
            [str(hooks_script), "claude"],
            input="",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            proc_no_event.returncode,
            2,
            f"build-hooks claude with missing event must exit 2; got {proc_no_event.returncode}",
        )

        # 4. Gate decisions: hook events invoke the shared guard and receive expected verdicts
        # Forbidden git push to main in PreToolUse
        deny_payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git push origin main"},
        }
        proc_deny = subprocess.run(
            [str(guard_script), "claude"],
            input=json.dumps(deny_payload),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            proc_deny.returncode,
            0,
            f"build-guard must exit 0 when emitting a deny decision; got {proc_deny.returncode}",
        )
        deny_output = json.loads(proc_deny.stdout)
        decision = (
            deny_output.get("hookSpecificOutput", {}).get("permissionDecision")
            or deny_output.get("decision")
        )
        self.assertEqual(
            decision,
            "deny",
            f"build-guard must deny 'git push origin main'; got {deny_output}",
        )

        # 5. Ownership Seam: hooks.json must be owned under harnesses/claude/runtime/hooks;
        # scripts/harness_generation.py must not copy it from plugins/claude/hooks.
        from scripts import harness_generation

        source_code = inspect.getsource(harness_generation.desired_runtime)
        self.assertNotIn(
            'root / "plugins/claude/hooks"',
            source_code,
            "Claude hooks must be owned directly under harnesses/claude/runtime/hooks; "
            "scripts/harness_generation.py must not copy hooks from plugins/claude (#156)",
        )


if __name__ == "__main__":
    unittest.main()
