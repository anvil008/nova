"""Acceptance tests for Antigravity (agy) runtime ownership and staging (issue #163).

Covers the three Definition of Done acceptance criteria for AgyRuntime:
1. agy-runtime-stages-one-family (integration):
   Stage contains manifest/hooks/rules/ten agents/16 skills/shared runtime/stamp
   as real files with no other harness.
2. teamwork-capability-is-generated (unit):
   Metadata marks Teamwork paid/interactive and names fallback;
   unavailable fixture omits Teamwork fields with note.
3. agy-hooks-preserve-gates (integration):
   Fixture events reach the same shared guard decisions;
   a missing required hook command fails staging.
"""

from __future__ import annotations

import inspect
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = TEST_DIR.parent
HARNESS_DIR = RUNTIME_DIR.parent
REPO_ROOT = HARNESS_DIR.parent.parent
DIST_DIR = REPO_ROOT / "dist" / "agy"
STAGED_PLUGIN = DIST_DIR / "workcell"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build-agy-plugin.py"
GUARD_SCRIPT = REPO_ROOT / "scripts" / "hooks" / "build-guard"
HOOKS_SCRIPT = REPO_ROOT / "scripts" / "hooks" / "build-hooks"

EXPECTED_AGENTS = {
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
}

EXPECTED_SKILLS = {
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
}

REQUIRED_HOOK_COMMANDS = (
    "build-guard agy",
    "build-hooks agy PreToolUse",
    "build-hooks agy PostToolUse",
    "build-format agy",
    "build-lint agy",
    "build-hooks agy Stop",
)


class AgyRuntimeTests(unittest.TestCase):
    """Test suite validating Antigravity runtime contracts, capabilities, and staging."""

    def test_agy_runtime_stages_one_family(self) -> None:
        """agy-runtime-stages-one-family (integration):

        Stage contains manifest/hooks/rules/ten agents/16 skills/shared runtime/stamp
        as real files with no other harness.
        """
        # 1. Manifest, hooks, rules exist directly under harnesses/agy/runtime as real files
        manifest_path = RUNTIME_DIR / "plugin.json"
        self.assertTrue(manifest_path.is_file(), f"Manifest missing at {manifest_path}")
        self.assertFalse(
            manifest_path.is_symlink(),
            f"Manifest must not be a symlink: {manifest_path}",
        )
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest_data.get("name"), "workcell")
        self.assertTrue(
            bool(manifest_data.get("version")),
            "Manifest must declare non-empty version",
        )
        self.assertTrue(
            bool(manifest_data.get("description")),
            "Manifest must declare non-empty description",
        )

        hooks_path = RUNTIME_DIR / "hooks.json"
        self.assertTrue(hooks_path.is_file(), f"Hooks file missing at {hooks_path}")
        self.assertFalse(
            hooks_path.is_symlink(),
            f"Hooks file must not be a symlink: {hooks_path}",
        )
        hooks_data = json.loads(hooks_path.read_text(encoding="utf-8"))
        self.assertIn(
            "workcell-guard", hooks_data, "hooks.json must declare workcell-guard"
        )

        rules_path = RUNTIME_DIR / "rules" / "AGENTS.md"
        self.assertTrue(rules_path.is_file(), f"Rules file missing at {rules_path}")
        self.assertFalse(
            rules_path.is_symlink(),
            f"Rules file must not be a symlink: {rules_path}",
        )
        rules_text = rules_path.read_text(encoding="utf-8")
        self.assertIn("Workcell Agent Rules", rules_text)

        # Zero symlinks in harnesses/agy/runtime (excluding tests)
        runtime_symlinks = [
            p
            for p in RUNTIME_DIR.rglob("*")
            if p.is_symlink() and "tests" not in p.parts
        ]
        self.assertEqual(
            runtime_symlinks,
            [],
            f"Runtime tree must have zero symlinks: {runtime_symlinks}",
        )

        # 2. Run staging script
        self.assertTrue(
            BUILD_SCRIPT.is_file(), f"Build script missing at {BUILD_SCRIPT}"
        )
        proc = subprocess.run(
            [sys.executable, str(BUILD_SCRIPT)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"build-agy-plugin.py failed: {proc.stderr}\n{proc.stdout}",
        )

        # 3. Staged tree verification: dist/agy/workcell
        self.assertTrue(
            STAGED_PLUGIN.is_dir(),
            f"Staged plugin missing at {STAGED_PLUGIN}",
        )

        # Real manifest, hooks, rules
        staged_manifest = STAGED_PLUGIN / "plugin.json"
        self.assertTrue(staged_manifest.is_file())
        self.assertFalse(staged_manifest.is_symlink())
        staged_manifest_data = json.loads(staged_manifest.read_text(encoding="utf-8"))
        self.assertEqual(staged_manifest_data.get("name"), "workcell")

        staged_hooks = STAGED_PLUGIN / "hooks.json"
        self.assertTrue(staged_hooks.is_file())
        self.assertFalse(staged_hooks.is_symlink())

        staged_rules = STAGED_PLUGIN / "rules" / "AGENTS.md"
        self.assertTrue(staged_rules.is_file())
        self.assertFalse(staged_rules.is_symlink())

        # Ten agents as real files
        agents_dir = STAGED_PLUGIN / "agents"
        self.assertTrue(
            agents_dir.is_dir(), f"Staged agents dir missing at {agents_dir}"
        )
        staged_agents = [
            p.name
            for p in agents_dir.iterdir()
            if p.is_dir()
            and (p / "agent.md").is_file()
            and not (p / "agent.md").is_symlink()
        ]
        self.assertEqual(
            set(staged_agents),
            EXPECTED_AGENTS,
            f"Staged agents must match expected 10 agents; got {set(staged_agents)}",
        )
        self.assertEqual(
            len(staged_agents),
            10,
            f"Expected exactly 10 agents, got {len(staged_agents)}",
        )

        # 16 skills represented as real files (15 global + agent-owned jj)
        skills_dir = STAGED_PLUGIN / "skills"
        self.assertTrue(
            skills_dir.is_dir(), f"Staged skills dir missing at {skills_dir}"
        )
        global_skills = {
            p.name
            for p in skills_dir.iterdir()
            if p.is_dir()
            and (p / "SKILL.md").is_file()
            and not (p / "SKILL.md").is_symlink()
        }
        # agent-owned skills (e.g. jj under builder/skills/jj and specifier/skills/jj)
        agent_owned = {
            p.name
            for p in agents_dir.glob("*/skills/*")
            if p.is_dir()
            and (p / "SKILL.md").is_file()
            and not (p / "SKILL.md").is_symlink()
        }
        all_staged_skills = global_skills | agent_owned
        self.assertEqual(
            all_staged_skills,
            EXPECTED_SKILLS,
            f"Staged skills must contain all 16 skills; got {all_staged_skills}",
        )
        self.assertEqual(
            len(all_staged_skills),
            16,
            f"Expected 16 skills, got {len(all_staged_skills)}",
        )

        # Shared runtime staged
        staged_runtime = STAGED_PLUGIN / "runtime"
        self.assertTrue(
            staged_runtime.is_dir(),
            f"Staged runtime dir missing at {staged_runtime}",
        )
        self.assertTrue((staged_runtime / "contracts.json").is_file())
        self.assertFalse((staged_runtime / "contracts.json").is_symlink())
        self.assertTrue((staged_runtime / "handoff.md").is_file())
        self.assertFalse((staged_runtime / "handoff.md").is_symlink())
        self.assertTrue((staged_runtime / "docs").is_dir())

        # Stamp: name: workcell, sourceRoot: harnesses/agy
        stamp_path = STAGED_PLUGIN / ".workcell-stamp.json"
        self.assertTrue(stamp_path.is_file(), f"Stamp missing at {stamp_path}")
        self.assertFalse(
            stamp_path.is_symlink(),
            f"Stamp must not be a symlink: {stamp_path}",
        )
        stamp_data = json.loads(stamp_path.read_text(encoding="utf-8"))
        self.assertEqual(stamp_data.get("name"), "workcell")
        self.assertEqual(
            stamp_data.get("sourceRoot"),
            "harnesses/agy",
            f"Stamp sourceRoot must be 'harnesses/agy', got {stamp_data.get('sourceRoot')}",
        )
        self.assertTrue(
            bool(stamp_data.get("contentDigest")),
            "Stamp must have non-empty contentDigest",
        )

        # Zero symlinks in the entire staged tree
        all_symlinks = [p for p in DIST_DIR.rglob("*") if p.is_symlink()]
        self.assertEqual(
            all_symlinks,
            [],
            f"Staged tree dist/agy must have zero symlinks: {all_symlinks}",
        )

        # "with no other harness": no foreign harness manifests or plugin configurations
        self.assertFalse(
            (STAGED_PLUGIN / ".claude-plugin").exists(),
            "Claude plugin marker must not exist in agy staging",
        )
        self.assertFalse(
            (STAGED_PLUGIN / ".codex-plugin").exists(),
            "Codex plugin marker must not exist in agy staging",
        )

        # Staged files must have no repo checkout path dependencies
        repo_root_str = str(REPO_ROOT)
        for path in STAGED_PLUGIN.rglob("*"):
            if path.is_file() and not path.name.endswith(".pyc"):
                try:
                    content = path.read_text(encoding="utf-8")
                    self.assertNotIn(
                        repo_root_str,
                        content,
                        f"Staged file {path.relative_to(STAGED_PLUGIN)} contains hardcoded repo path {repo_root_str}",
                    )
                except UnicodeDecodeError:
                    pass

        # 4. Ownership seam: desired_runtime must not copy plugin.json/hooks.json/rules from plugins/agy
        from scripts import harness_generation

        source_code = inspect.getsource(harness_generation.desired_runtime)
        self.assertNotIn(
            'root / "plugins/agy/plugin.json"',
            source_code,
            "scripts/harness_generation.py: desired_runtime must not copy plugin.json from plugins/agy; "
            "harnesses/agy/runtime must own its manifest directly (#163)",
        )
        self.assertNotIn(
            'root / "plugins/agy/hooks.json"',
            source_code,
            "scripts/harness_generation.py: desired_runtime must not copy hooks.json from plugins/agy; "
            "harnesses/agy/runtime must own its hooks directly (#163)",
        )
        self.assertNotIn(
            'root / "plugins/agy/rules"',
            source_code,
            "scripts/harness_generation.py: desired_runtime must not copy rules from plugins/agy; "
            "harnesses/agy/runtime must own its rules directly (#163)",
        )

    def test_teamwork_capability_is_generated(self) -> None:
        """teamwork-capability-is-generated (unit):

        Metadata marks Teamwork paid/interactive and names fallback;
        unavailable fixture omits Teamwork fields with note.
        """
        # 1. Capability metadata exists under harnesses/agy/runtime
        capabilities_path = RUNTIME_DIR / "capabilities.json"
        self.assertTrue(
            capabilities_path.is_file(),
            f"Missing runtime capabilities metadata at {capabilities_path}: "
            "Antigravity runtime must own capability metadata under its runtime root (#163)",
        )
        self.assertFalse(
            capabilities_path.is_symlink(),
            f"Capabilities file {capabilities_path} must not be a symlink",
        )

        caps = json.loads(capabilities_path.read_text(encoding="utf-8"))
        self.assertEqual(
            caps.get("harness"),
            "agy",
            f"Expected harness 'agy', got {caps.get('harness')}",
        )

        # Headless command specification
        headless_cmd = caps.get("headless_command", [])
        self.assertIsInstance(headless_cmd, list, "headless_command must be a list")
        self.assertTrue(
            any("agy" in str(c) for c in headless_cmd),
            f"headless_command must specify 'agy'; got {headless_cmd}",
        )
        self.assertTrue(
            any("-p" in str(c) for c in headless_cmd),
            f"headless_command must specify '-p' for headless mode; got {headless_cmd}",
        )
        # Model and effort options per issue description (gemini-3.8-flash, effort high)
        cmd_str = " ".join(str(c) for c in headless_cmd)
        self.assertTrue(
            "gemini-3.8-flash" in cmd_str or "gemini-3.7-flash" in cmd_str,
            f"headless_command must specify gemini-3.8-flash; got {headless_cmd}",
        )

        # 2. Teamwork capability: marked paid/interactive and names fallback
        features = caps.get("features", {})
        self.assertIn(
            "teamwork",
            features,
            f"Capabilities metadata at {capabilities_path} missing 'teamwork' feature entry",
        )
        teamwork = features["teamwork"]

        # Teamwork must be marked paid and/or interactive, not supported in headless mode
        self.assertFalse(
            teamwork.get("supported", True) and teamwork.get("headless", True),
            "Teamwork feature must not be marked as supported in headless mode",
        )
        is_paid_or_interactive = (
            teamwork.get("paid", False)
            or teamwork.get("interactive", False)
            or "paid" in str(teamwork).lower()
            or "interactive" in str(teamwork).lower()
        )
        self.assertTrue(
            is_paid_or_interactive,
            "Teamwork capability metadata must mark Teamwork as paid and/or interactive",
        )

        # Non-empty note naming standard async headless fallback
        note = (
            teamwork.get("omission_note")
            or teamwork.get("limitation_note")
            or teamwork.get("note")
            or teamwork.get("fallback")
            or ""
        )
        self.assertTrue(
            len(note.strip()) > 0,
            "Teamwork capability metadata must provide a non-empty note explaining its status",
        )
        note_lower = note.lower()
        self.assertTrue(
            any(
                kw in note_lower
                for kw in ("headless", "subagent", "async", "workspace", "cli")
            ),
            f"Teamwork note must name standard async headless fallback; got: {note}",
        )

        # 3. Unsupported-effort note: minimal effort is not supported for gemini-3.7-flash
        effort_note = (
            caps.get("unsupported_effort_note")
            or features.get("effort", {}).get("unsupported_effort_note")
            or features.get("thinking", {}).get("unsupported_effort_note")
            or teamwork.get("unsupported_effort_note")
            or ""
        )
        self.assertTrue(
            len(effort_note.strip()) > 0,
            "Capabilities metadata must provide an unsupported-effort note documenting "
            "gemini-3.7-flash thinking/effort constraints (#163)",
        )
        effort_lower = effort_note.lower()
        self.assertIn(
            "minimal", effort_lower, "Unsupported-effort note must mention 'minimal'"
        )
        self.assertTrue(
            any(kw in effort_lower for kw in ("error", "not supported", "unsupported")),
            f"Unsupported-effort note must state that minimal effort is unsupported/returns error; got: {effort_note}",
        )

        # 4. Unavailable fixture omits Teamwork fields with note
        # When evaluating capabilities in an environment where Teamwork is unavailable
        # (e.g. headless execution fixture), Teamwork interactive orchestration fields
        # are omitted, and contracts load cleanly without requiring Teamwork.
        disallowed_teamwork_fields = {
            "teamwork_orchestration",
            "teamwork_session",
            "teamwork_channels",
            "teamwork_team",
            "teamwork_ui",
        }
        for field in disallowed_teamwork_fields:
            self.assertNotIn(
                field,
                caps,
                f"Interactive Teamwork field {field!r} must be omitted from headless capability metadata",
            )
            self.assertNotIn(
                field,
                features,
                f"Interactive Teamwork field {field!r} must be omitted from headless features",
            )

        # Contracts verification: no skill or agent in contracts.json requires teamwork
        carrier = RUNTIME_DIR / "contracts.json"
        self.assertTrue(carrier.is_file(), f"Missing contracts carrier at {carrier}")
        contracts_data = json.loads(carrier.read_text(encoding="utf-8"))
        contract = contracts_data.get("contract", {})

        skills = contract.get("skills", [])
        self.assertEqual(
            len(skills), 16, f"Expected 16 skills in contracts, got {len(skills)}"
        )
        for sk in skills:
            reqs = sk.get("requiredValues", {}).get("agy", [])
            self.assertNotIn(
                "teamwork",
                reqs,
                f"Skill {sk['name']} must not require teamwork in agy contract",
            )
            self.assertNotIn(
                "interactive",
                reqs,
                f"Skill {sk['name']} must not require interactive in agy contract",
            )

        agents = contract.get("agents", [])
        self.assertEqual(
            len(agents), 10, f"Expected 10 agents in contracts, got {len(agents)}"
        )
        for ag in agents:
            reqs = ag.get("requiredValues", {}).get("agy", [])
            self.assertNotIn(
                "teamwork",
                reqs,
                f"Agent {ag['name']} must not require teamwork in agy contract",
            )
            self.assertNotIn(
                "interactive",
                reqs,
                f"Agent {ag['name']} must not require interactive in agy contract",
            )

    def test_agy_hooks_preserve_gates(self) -> None:
        """agy-hooks-preserve-gates (integration):

        Fixture events reach the same shared guard decisions;
        a missing required hook command fails staging.
        """
        # 1. hooks.json registers PreToolUse, PostToolUse, and Stop
        hooks_path = RUNTIME_DIR / "hooks.json"
        self.assertTrue(hooks_path.is_file(), f"Missing hooks file at {hooks_path}")
        hooks_data = json.loads(hooks_path.read_text(encoding="utf-8"))
        guard_cfg = hooks_data.get("workcell-guard", {})
        self.assertTrue(guard_cfg.get("enabled"), "workcell-guard must be enabled")

        for gate in ("PreToolUse", "PostToolUse", "Stop"):
            self.assertIn(gate, guard_cfg, f"hooks.json must declare {gate}")

        # Extract all hook commands from hooks.json
        declared_commands: list[str] = []
        for gate in ("PreToolUse", "PostToolUse", "Stop"):
            entries = guard_cfg.get(gate, [])
            for entry in entries:
                if isinstance(entry, dict):
                    if "hooks" in entry:
                        for h in entry.get("hooks", []):
                            cmd = h.get("command", "")
                            declared_commands.append(cmd)
                            self.assertEqual(h.get("type"), "command")
                            self.assertGreater(h.get("timeout", 0), 0)
                    elif "command" in entry:
                        cmd = entry.get("command", "")
                        declared_commands.append(cmd)
                        self.assertEqual(entry.get("type"), "command")
                        self.assertGreater(entry.get("timeout", 0), 0)

        # Check all required hook commands are present
        for req in REQUIRED_HOOK_COMMANDS:
            self.assertTrue(
                any(req in cmd for cmd in declared_commands),
                f"hooks.json missing required command {req!r}; declared: {declared_commands}",
            )

        # 2. Guard scripts fail closed (exit code 2) on missing/invalid input
        self.assertTrue(
            os.access(GUARD_SCRIPT, os.X_OK),
            f"{GUARD_SCRIPT} must be executable",
        )
        self.assertTrue(
            os.access(HOOKS_SCRIPT, os.X_OK),
            f"{HOOKS_SCRIPT} must be executable",
        )

        # build-guard agy fails closed on empty input
        proc_empty = subprocess.run(
            ["bash", str(GUARD_SCRIPT), "agy"],
            input="",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            proc_empty.returncode,
            2,
            f"build-guard agy with empty payload must exit 2 (fail closed); got {proc_empty.returncode}",
        )

        # build-guard agy fails closed on non-JSON payload
        proc_invalid = subprocess.run(
            ["bash", str(GUARD_SCRIPT), "agy"],
            input="not-json",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            proc_invalid.returncode,
            2,
            f"build-guard agy with non-JSON payload must exit 2; got {proc_invalid.returncode}",
        )

        # build-guard agy fails closed on payload missing command field
        proc_nocmd = subprocess.run(
            ["bash", str(GUARD_SCRIPT), "agy"],
            input=json.dumps({"toolCall": {"args": {}}}),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            proc_nocmd.returncode,
            2,
            f"build-guard agy with missing command must exit 2; got {proc_nocmd.returncode}",
        )

        # build-hooks agy fails closed on missing event argument
        proc_no_event = subprocess.run(
            ["bash", str(HOOKS_SCRIPT), "agy"],
            input="",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            proc_no_event.returncode,
            2,
            f"build-hooks agy with missing event must exit 2; got {proc_no_event.returncode}",
        )

        # 3. Gate decisions: hook events reach the same shared guard decisions
        # Forbidden git push to main in PreToolUse
        deny_push_payload = {
            "agent_type": "workcell:builder",
            "toolCall": {"args": {"CommandLine": "git push origin main"}},
        }
        proc_deny_push = subprocess.run(
            ["bash", str(GUARD_SCRIPT), "agy"],
            input=json.dumps(deny_push_payload),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            proc_deny_push.returncode,
            0,
            f"build-guard agy must exit 0 when emitting a deny decision; got {proc_deny_push.returncode}",
        )
        push_output = json.loads(proc_deny_push.stdout)
        self.assertEqual(
            push_output.get("decision"),
            "deny",
            f"build-guard agy must deny 'git push origin main'; got {push_output}",
        )

        # Forbidden git checkout main followed by commit in PreToolUse
        deny_checkout_payload = {
            "agent_type": "workcell:builder",
            "toolCall": {
                "args": {"CommandLine": "git checkout main; git commit -m bad"}
            },
        }
        proc_deny_co = subprocess.run(
            ["bash", str(GUARD_SCRIPT), "agy"],
            input=json.dumps(deny_checkout_payload),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc_deny_co.returncode, 0)
        co_output = json.loads(proc_deny_co.stdout)
        self.assertEqual(co_output.get("decision"), "deny")

        # Forbidden edit to eval-mode in PreToolUse via build-hooks
        deny_eval_payload = {
            "toolCall": {"args": {"TargetFile": "/repo/.workcell/eval-mode.json"}},
        }
        proc_deny_eval = subprocess.run(
            ["bash", str(HOOKS_SCRIPT), "agy", "PreToolUse"],
            input=json.dumps(deny_eval_payload),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc_deny_eval.returncode, 0)
        eval_output = json.loads(proc_deny_eval.stdout)
        self.assertEqual(
            eval_output.get("decision"),
            "deny",
            f"build-hooks agy must deny editing eval-mode.json; got {eval_output}",
        )

        # 4. A missing required hook command fails staging
        # When hooks.json is missing any required hook command, build-agy-plugin.py
        # must fail staging (exit non-zero) and refuse to produce an un-guarded plugin.
        original_hooks_content = hooks_path.read_text(encoding="utf-8")
        try:
            # Create incomplete hooks missing build-guard agy and build-hooks agy Stop
            incomplete_hooks = {
                "workcell-guard": {
                    "enabled": True,
                    "PreToolUse": [],
                    "PostToolUse": [],
                    "Stop": [],
                }
            }
            hooks_path.write_text(json.dumps(incomplete_hooks), encoding="utf-8")
            proc_staging = subprocess.run(
                [sys.executable, str(BUILD_SCRIPT)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(
                proc_staging.returncode,
                0,
                f"build-agy-plugin.py must fail staging when required hook commands are missing; "
                f"exit code was {proc_staging.returncode}",
            )
        finally:
            hooks_path.write_text(original_hooks_content, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
