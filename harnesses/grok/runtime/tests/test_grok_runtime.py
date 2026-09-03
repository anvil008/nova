"""Acceptance tests for Grok Build runtime metadata, headless automation, and plugin staging (#166).

Tests that:
1. grok-runtime-stages-one-family (integration):
   Stage contains manifest/runtime metadata/ten agents/16 skills/shared copies/stamp
   as real files with no source-root or other harness.
2. headless-adapter-is-current-and-bounded (unit):
   Automation invokes grok --no-auto-update -p with workspace/machine output/timeout
   and explicit grok-4.6 model strategy.
3. unsupported-fields-are-not-invented (unit):
   No per-agent tool list or unsupported effort appears; optional omissions are
   noted once and missing required values fail.
"""

from __future__ import annotations

import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TEST_FILE = Path(__file__).resolve()
RUNTIME_DIR = TEST_FILE.parents[1]
HARNESS_DIR = TEST_FILE.parents[2]
REPO_ROOT = TEST_FILE.parents[4]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# All 16 Workcell skills
EXPECTED_SKILLS = (
    "build",
    "jj",
    "code-analysis",
    "code-refactor",
    "code-review",
    "debug",
    "deploy",
    "docs",
    "new-feature",
    "perf",
    "plan",
    "repo-setup",
    "research",
    "review-fix-loop",
    "use-other-harness",
    "wiki",
)

# All 10 Workcell agents
EXPECTED_AGENTS = (
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


class GrokRuntimeTests(unittest.TestCase):
    """Authoritative acceptance tests for GitHub issue #166 (GrokRuntime)."""

    def _create_isolated_fixture(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        """Create a temporary isolated fixture copying needed harness and generator paths."""
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        paths_to_copy = [
            "harnesses/grok",
            "agents",
            "skills",
            "plugins/grok",
            "contracts",
            "scripts/build-grok-plugin.py",
            "scripts/lib_dist.py",
        ]
        for rel in paths_to_copy:
            src = REPO_ROOT / rel
            if not src.exists():
                continue
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        return tmp, root

    def _run_grok_stager(self, root: Path) -> subprocess.CompletedProcess[str]:
        """Run the Grok plugin stager in the given root."""
        stager = root / "scripts" / "build-grok-plugin.py"
        return subprocess.run(
            [sys.executable, str(stager)],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_grok_runtime_stages_one_family(self) -> None:
        """grok-runtime-stages-one-family (integration):

        Stage contains manifest/runtime metadata/ten agents/16 skills/shared copies/stamp
        as real files with no source-root or other harness.
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

        # 2. Shared guard scripts exist in RUNTIME_DIR/scripts
        scripts_dir = RUNTIME_DIR / "scripts"
        self.assertTrue(
            scripts_dir.is_dir(),
            f"Missing scripts directory at {scripts_dir}: runtime must copy shared guard executables (#166)",
        )
        for guard_name in ("build-guard", "build-hooks", "build-format", "build-lint"):
            guard_file = scripts_dir / guard_name
            self.assertTrue(
                guard_file.is_file(),
                f"Shared guard script {guard_file} is missing from runtime/scripts",
            )
            self.assertTrue(
                os.access(guard_file, os.X_OK),
                f"Shared guard script {guard_file} must be executable",
            )
            self.assertFalse(
                guard_file.is_symlink(),
                f"Shared guard script {guard_file} must not be a symlink",
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
            f"harnesses/grok/runtime must contain zero symlinks; found: {runtime_symlinks}",
        )

        # 4. Ownership Seam: harnesses/grok/runtime owns its manifest and runtime metadata;
        # scripts/harness_generation.py must not copy them from plugins/grok.
        from scripts import harness_generation

        source_code = inspect.getsource(harness_generation.desired_runtime)
        self.assertNotIn(
            'root / "plugins/grok/.claude-plugin"',
            source_code,
            "scripts/harness_generation.py: desired_runtime must not copy .claude-plugin from plugins/grok; "
            "harnesses/grok/runtime must own its manifest directly (#166)",
        )
        self.assertIn(
            "grok",
            harness_generation.HARNESS_OWNED_RUNTIME,
            "scripts/harness_generation.py: HARNESS_OWNED_RUNTIME must contain 'grok' (#166)",
        )
        grok_owned = harness_generation.HARNESS_OWNED_RUNTIME.get("grok", ())
        self.assertIn(
            Path(".claude-plugin"),
            grok_owned,
            "HARNESS_OWNED_RUNTIME['grok'] must include .claude-plugin",
        )
        self.assertIn(
            Path("capabilities.json"),
            grok_owned,
            "HARNESS_OWNED_RUNTIME['grok'] must include capabilities.json",
        )

        # 5. Staging validation: build-grok-plugin.py stages with no symlinks or repo dependencies
        builder_script = REPO_ROOT / "scripts" / "build-grok-plugin.py"
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
            f"scripts/build-grok-plugin.py failed with exit code {proc.returncode}:\n{proc.stderr}",
        )

        staged_plugin = REPO_ROOT / "dist" / "grok" / "plugins" / "workcell"
        self.assertTrue(
            staged_plugin.is_dir(), f"Staged directory {staged_plugin} was not created"
        )

        # Marketplace manifest check
        staged_mkt = REPO_ROOT / "dist" / "grok" / ".grok-plugin" / "marketplace.json"
        self.assertTrue(
            staged_mkt.is_file(), f"Marketplace manifest {staged_mkt} missing"
        )
        mkt_data = json.loads(staged_mkt.read_text(encoding="utf-8"))
        self.assertEqual(mkt_data.get("name"), "workcell")
        plugins_list = mkt_data.get("plugins", [])
        self.assertTrue(
            any(p.get("name") == "workcell" for p in plugins_list),
            f"Marketplace missing 'workcell' plugin entry: {plugins_list}",
        )

        # Staged manifest check
        staged_manifest_file = staged_plugin / ".claude-plugin" / "plugin.json"
        self.assertTrue(
            staged_manifest_file.is_file(),
            f"Missing staged manifest at {staged_manifest_file}",
        )
        self.assertFalse(
            staged_manifest_file.is_symlink(),
            f"Staged manifest {staged_manifest_file} must not be a symlink",
        )
        staged_manifest = json.loads(staged_manifest_file.read_text(encoding="utf-8"))
        self.assertEqual(staged_manifest.get("name"), "workcell")
        self.assertTrue(
            staged_manifest.get("version"),
            "Staged manifest must declare non-empty version",
        )

        # Staged stamp check
        stamp_file = staged_plugin / ".workcell-stamp.json"
        self.assertTrue(stamp_file.is_file(), f"Missing stamp {stamp_file}")
        self.assertFalse(
            stamp_file.is_symlink(), f"Stamp {stamp_file} must not be a symlink"
        )
        stamp_data = json.loads(stamp_file.read_text(encoding="utf-8"))
        self.assertEqual(stamp_data.get("sourceRoot"), "harnesses/grok")
        self.assertEqual(stamp_data.get("name"), "workcell")
        self.assertTrue(stamp_data.get("version"), "Stamp must have non-empty version")

        # 10 agents staged as real files
        for agent in EXPECTED_AGENTS:
            agent_file = staged_plugin / "agents" / f"{agent}.md"
            self.assertTrue(
                agent_file.is_file(),
                f"Expected agent {agent} at {agent_file} is missing from staged plugin",
            )
            self.assertFalse(
                agent_file.is_symlink(),
                f"Staged agent {agent_file} must not be a symlink",
            )
            self.assertTrue(
                len(agent_file.read_text(encoding="utf-8").strip()) > 0,
                f"Staged agent {agent_file} is empty",
            )

        # 16 skills staged as real files
        for skill in EXPECTED_SKILLS:
            skill_md = staged_plugin / "skills" / skill / "SKILL.md"
            self.assertTrue(
                skill_md.is_file(),
                f"Expected skill {skill} at {skill_md} is missing from staged plugin",
            )
            self.assertFalse(
                skill_md.is_symlink(),
                f"Staged skill {skill_md} must not be a symlink",
            )
            self.assertTrue(
                len(skill_md.read_text(encoding="utf-8").strip()) > 0,
                f"Staged skill {skill_md} is empty",
            )

        # Shared copies staged: shared guard scripts and handoff.md
        staged_handoff = staged_plugin / "handoff.md"
        self.assertTrue(staged_handoff.is_file(), f"Missing {staged_handoff}")
        self.assertFalse(
            staged_handoff.is_symlink(), f"{staged_handoff} must not be a symlink"
        )

        for guard_name in ("build-guard", "build-hooks", "build-format", "build-lint"):
            staged_candidates = [
                staged_plugin / "scripts" / guard_name,
                staged_plugin / "runtime" / "scripts" / guard_name,
            ]
            found = [p for p in staged_candidates if p.is_file()]
            self.assertTrue(
                len(found) > 0,
                f"Shared script {guard_name} missing from staged plugin (expected at scripts/ or runtime/scripts/)",
            )
            for p in found:
                self.assertFalse(
                    p.is_symlink(), f"Staged script {p} must not be a symlink"
                )
                self.assertTrue(
                    os.access(p, os.X_OK), f"Staged script {p} must be executable"
                )

        # Zero symlinks anywhere in dist/grok
        staged_symlinks = [
            str(p.relative_to(REPO_ROOT / "dist" / "grok"))
            for p in (REPO_ROOT / "dist" / "grok").rglob("*")
            if p.is_symlink()
        ]
        self.assertEqual(
            staged_symlinks,
            [],
            f"Staged dist/grok contains symlinks: {staged_symlinks}",
        )

        # No source-root repo path leak in staged files
        repo_root_str = str(REPO_ROOT)
        for path in staged_plugin.rglob("*"):
            if path.is_file() and not path.name.endswith(".pyc"):
                try:
                    content = path.read_text(encoding="utf-8")
                    self.assertNotIn(
                        repo_root_str,
                        content,
                        f"Staged file {path.relative_to(staged_plugin)} contains hardcoded repo path {repo_root_str}",
                    )
                except UnicodeDecodeError:
                    pass

        # No foreign harness leak in staged plugin manifest, stamp, agents, skills
        foreign_terms = [
            "${CLAUDE_PLUGIN_ROOT}",
            "plugins/claude",
            "harnesses/claude",
            "plugins/codex",
            "harnesses/codex",
            "plugins/agy",
            "harnesses/agy",
            "plugins/grok",
        ]
        key_files = (
            [staged_manifest_file, stamp_file, staged_handoff]
            + list((staged_plugin / "agents").glob("*.md"))
            + list((staged_plugin / "skills").glob("*/SKILL.md"))
        )
        for path in key_files:
            if path.is_file():
                content = path.read_text(encoding="utf-8")
                for term in foreign_terms:
                    self.assertNotIn(
                        term,
                        content,
                        f"Key staged file {path.relative_to(staged_plugin)} contains foreign reference: {term}",
                    )

    def test_headless_adapter_is_current_and_bounded(self) -> None:
        """headless-adapter-is-current-and-bounded (unit):

        Automation invokes grok --no-auto-update -p with workspace/machine output/timeout
        and explicit grok-4.6 model strategy.
        """
        # 1. Runtime capabilities metadata must exist under harnesses/grok/runtime
        capabilities_path = RUNTIME_DIR / "capabilities.json"
        self.assertTrue(
            capabilities_path.is_file(),
            f"Missing runtime capabilities metadata at {capabilities_path}: "
            "must define Grok headless automation and capabilities (#166)",
        )
        self.assertFalse(
            capabilities_path.is_symlink(),
            f"Capabilities file {capabilities_path} must not be a symlink",
        )

        caps = json.loads(capabilities_path.read_text(encoding="utf-8"))
        self.assertEqual(caps.get("harness"), "grok")

        # 2. Automation headless_command specification
        headless_cmd = caps.get("headless_command", [])
        self.assertIsInstance(
            headless_cmd,
            list,
            f"headless_command in {capabilities_path} must be a list of CLI arguments",
        )
        self.assertTrue(
            len(headless_cmd) > 0,
            f"headless_command in {capabilities_path} must not be empty",
        )

        # Must invoke grok CLI
        self.assertTrue(
            any("grok" in token for token in headless_cmd),
            f"headless_command must specify grok executable; got {headless_cmd}",
        )

        # Must include --no-auto-update
        self.assertIn(
            "--no-auto-update",
            headless_cmd,
            f"headless_command missing '--no-auto-update' to avoid update checks in automation/CI: {headless_cmd}",
        )

        # Must include -p for headless non-interactive execution
        self.assertIn(
            "-p",
            headless_cmd,
            f"headless_command missing '-p' for non-interactive prompt execution: {headless_cmd}",
        )

        # Must bind workspace (e.g. via --cwd)
        self.assertIn(
            "--cwd",
            headless_cmd,
            f"headless_command missing '--cwd' workspace binding: {headless_cmd}",
        )

        # Must specify machine output format (json or streaming-json)
        output_format_present = (
            "--output-format" in headless_cmd
            or any("--output-format=" in token for token in headless_cmd)
            or "--debug-file" in headless_cmd
        )
        self.assertTrue(
            output_format_present,
            f"headless_command must configure machine output (e.g. --output-format json or --debug-file): {headless_cmd}",
        )
        if "--output-format" in headless_cmd:
            idx = headless_cmd.index("--output-format")
            self.assertTrue(
                idx + 1 < len(headless_cmd),
                "Missing argument following --output-format in headless_command",
            )
            format_val = headless_cmd[idx + 1]
            self.assertIn(
                format_val,
                ("json", "streaming-json", "plain"),
                f"Unexpected --output-format value {format_val!r}; expected json or streaming-json",
            )

        # Must bound execution with timeout / max turns
        turns_or_timeout_present = (
            "--max-turns" in headless_cmd
            or any("--max-turns=" in token for token in headless_cmd)
            or "--timeout" in headless_cmd
            or any("--timeout=" in token for token in headless_cmd)
        )
        self.assertTrue(
            turns_or_timeout_present,
            f"headless_command must bound automation with timeout/turns (e.g. --max-turns): {headless_cmd}",
        )

        # Must configure explicit grok-4.6 model strategy
        model_flag_present = (
            "--model" in headless_cmd
            or any("--model=" in token for token in headless_cmd)
            or "-m" in headless_cmd
        )
        self.assertTrue(
            model_flag_present,
            f"headless_command missing explicit model flag (--model): {headless_cmd}",
        )
        if "--model" in headless_cmd:
            idx = headless_cmd.index("--model")
            self.assertTrue(
                idx + 1 < len(headless_cmd),
                "Missing argument following --model in headless_command",
            )
            self.assertEqual(
                headless_cmd[idx + 1],
                "grok-4.6",
                f"headless_command must pin model strategy to grok-4.6; got {headless_cmd[idx + 1]!r}",
            )
        elif "-m" in headless_cmd:
            idx = headless_cmd.index("-m")
            self.assertEqual(
                headless_cmd[idx + 1],
                "grok-4.6",
                f"headless_command must pin model strategy to grok-4.6; got {headless_cmd[idx + 1]!r}",
            )
        else:
            token = [t for t in headless_cmd if t.startswith("--model=")][0]
            self.assertEqual(
                token.split("=", 1)[1],
                "grok-4.6",
                f"headless_command must pin model strategy to grok-4.6; got {token}",
            )

        # 3. Model strategy in agents/models.json
        models_file = REPO_ROOT / "agents" / "models.json"
        self.assertTrue(models_file.is_file(), f"Missing {models_file}")
        models_data = json.loads(models_file.read_text(encoding="utf-8"))
        grok_default = models_data.get("defaults", {}).get("grok")
        self.assertIsNotNone(grok_default, "agents/models.json missing defaults.grok")
        self.assertEqual(
            grok_default.get("model"),
            "grok-4.6",
            f"agents/models.json defaults.grok must specify model 'grok-4.6'; got {grok_default}",
        )
        for agent_name in EXPECTED_AGENTS:
            agent_cfg = (
                models_data.get("agents", {}).get(agent_name, {}).get("grok", {})
            )
            self.assertEqual(
                agent_cfg.get("model"),
                "grok-4.6",
                f"agents/models.json agent {agent_name}.grok must pin model 'grok-4.6'; got {agent_cfg}",
            )

        # 4. Feature evaluation against headless capability
        features = caps.get("features", {})
        required_evaluations = {
            "workflows",
            "personas",
            "forks",
            "subagents",
            "skill_isolation",
            "command_hooks",
        }
        for feat in required_evaluations:
            self.assertIn(
                feat,
                features,
                f"Capabilities metadata {capabilities_path} missing evaluation for feature {feat!r}",
            )

        # Interactive / headless boundaries
        # Workflows: interactive creation is guarded/omitted in headless automation with note
        wf_info = features["workflows"]
        wf_note = (
            wf_info.get("limitation_note")
            or wf_info.get("omission_note")
            or wf_info.get("note")
            or ""
        )
        self.assertTrue(
            len(wf_note.strip()) > 0,
            "workflows feature must document its headless status/limitation note",
        )

        # Personas: documented with inputs/outputs contracts note
        pers_info = features["personas"]
        pers_note = (
            pers_info.get("note")
            or pers_info.get("limitation_note")
            or pers_info.get("description")
            or ""
        )
        self.assertTrue(
            len(pers_note.strip()) > 0,
            "personas feature must document its contract note",
        )

        # Forks: documented with headless --fork-session note
        fork_info = features["forks"]
        fork_note = (
            fork_info.get("note")
            or fork_info.get("limitation_note")
            or fork_info.get("description")
            or ""
        )
        self.assertTrue(
            len(fork_note.strip()) > 0,
            "forks feature must document headless --fork-session strategy",
        )

        # Subagents: documented with background: true and nesting note
        sub_info = features["subagents"]
        sub_note = (
            sub_info.get("note")
            or sub_info.get("limitation_note")
            or sub_info.get("description")
            or ""
        )
        self.assertTrue(
            len(sub_note.strip()) > 0,
            "subagents feature must document background subagent strategy",
        )

    def test_unsupported_fields_are_not_invented(self) -> None:
        """unsupported-fields-are-not-invented (unit):

        No per-agent tool list or unsupported effort appears; optional omissions are
        noted once and missing required values fail.
        """
        # 1. No per-agent tool list or unsupported effort in harnesses/grok/agents/*.md frontmatter
        grok_agents_dir = HARNESS_DIR / "agents"
        self.assertTrue(grok_agents_dir.is_dir(), f"Missing {grok_agents_dir}")
        for agent_name in EXPECTED_AGENTS:
            agent_file = grok_agents_dir / f"{agent_name}.md"
            self.assertTrue(agent_file.is_file(), f"Missing {agent_file}")
            content = agent_file.read_text(encoding="utf-8")
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = parts[1]
                    self.assertNotIn(
                        "\ntools:",
                        "\n" + frontmatter,
                        f"Grok agent {agent_file.name} must not declare per-agent 'tools' list in frontmatter",
                    )
                    self.assertNotIn(
                        "\nallowed-tools:",
                        "\n" + frontmatter,
                        f"Grok agent {agent_file.name} must not declare 'allowed-tools' in frontmatter",
                    )
                    self.assertNotIn(
                        "\neffort:",
                        "\n" + frontmatter,
                        f"Grok agent {agent_file.name} must not declare unsupported 'effort' in frontmatter",
                    )

        # 2. Contracts: required values and optional surfaces
        contracts_file = REPO_ROOT / "contracts" / "harness-contracts.json"
        self.assertTrue(
            contracts_file.is_file(), f"Missing contracts at {contracts_file}"
        )
        contracts_data = json.loads(contracts_file.read_text(encoding="utf-8"))

        unsupported_required = {"tools", "allowed-tools", "effort", "mode"}
        for ag in contracts_data.get("agents", []):
            reqs = set(ag.get("requiredValues", {}).get("grok", []))
            invented = reqs.intersection(unsupported_required)
            self.assertFalse(
                invented,
                f"Agent {ag.get('name')} invents unsupported Grok required values: {invented}",
            )
            # Grok agents require exactly body and model
            self.assertEqual(
                sorted(ag.get("requiredValues", {}).get("grok", [])),
                ["body", "model"],
                f"Agent {ag.get('name')} must declare exactly ['body', 'model'] for Grok",
            )

        for sk in contracts_data.get("skills", []):
            reqs = set(sk.get("requiredValues", {}).get("grok", []))
            invented = reqs.intersection(unsupported_required)
            self.assertFalse(
                invented,
                f"Skill {sk.get('name')} invents unsupported Grok required values: {invented}",
            )

        # Optional surfaces for Grok: must be marked supported=False with non-empty limitationNote, and noted once
        grok_optional_surfaces = []
        for ag in contracts_data.get("agents", []):
            agent_grok_surfaces = [
                surf
                for surf in ag.get("optionalSurfaces", [])
                if surf.get("harness") == "grok"
            ]
            # Check noted once (no duplicates per agent)
            surface_names = [s.get("name") for s in agent_grok_surfaces]
            self.assertEqual(
                len(surface_names),
                len(set(surface_names)),
                f"Agent {ag.get('name')} has duplicate Grok optionalSurfaces: {surface_names}",
            )
            grok_optional_surfaces.extend(agent_grok_surfaces)

        self.assertTrue(
            len(grok_optional_surfaces) > 0,
            "Expected at least one Grok optionalSurface declared in contracts",
        )
        for surf in grok_optional_surfaces:
            self.assertFalse(
                surf.get("supported", True),
                f"Optional surface {surf.get('name')} for Grok must not be marked supported",
            )
            note = surf.get("limitationNote", "")
            self.assertTrue(
                len(note.strip()) > 0,
                f"Optional surface {surf.get('name')} for Grok must have a non-empty limitationNote",
            )

        # 3. Capabilities: unsupported fields are evaluated with limitation notes
        capabilities_path = RUNTIME_DIR / "capabilities.json"
        self.assertTrue(
            capabilities_path.is_file(),
            f"Missing {capabilities_path}",
        )
        caps = json.loads(capabilities_path.read_text(encoding="utf-8"))
        features = caps.get("features", {})
        for unsupp_feat in ("effort", "mode", "allowed_tools"):
            self.assertIn(
                unsupp_feat,
                features,
                f"capabilities.json missing evaluation for unsupported field {unsupp_feat!r}",
            )
            feat_info = features[unsupp_feat]
            self.assertFalse(
                feat_info.get("supported", True) and feat_info.get("headless", True),
                f"Feature {unsupp_feat!r} must not be marked supported",
            )
            limitation = (
                feat_info.get("limitation_note")
                or feat_info.get("omission_note")
                or feat_info.get("note")
                or ""
            )
            self.assertTrue(
                len(limitation.strip()) > 0,
                f"Unsupported feature {unsupp_feat!r} must carry a non-empty limitation note",
            )

        # 4. Missing required profile values fail closed
        for bad_case, modifier in (
            (
                "missing_grok_profile",
                lambda m: m["agents"]["builder"].pop("grok", None),
            ),
            (
                "missing_model",
                lambda m: (
                    m["agents"]["builder"].setdefault("grok", {}).pop("model", None)
                ),
            ),
            (
                "empty_model",
                lambda m: (
                    m["agents"]["builder"]
                    .setdefault("grok", {})
                    .__setitem__("model", "")
                ),
            ),
            (
                "invalid_model",
                lambda m: (
                    m["agents"]["builder"]
                    .setdefault("grok", {})
                    .__setitem__("model", "unsupported-model")
                ),
            ),
        ):
            with self.subTest(case=bad_case):
                tmp, root = self._create_isolated_fixture()
                with tmp:
                    models_json = root / "agents" / "models.json"
                    manifest = json.loads(models_json.read_text(encoding="utf-8"))
                    modifier(manifest)
                    models_json.write_text(json.dumps(manifest), encoding="utf-8")

                    proc = self._run_grok_stager(root)
                    self.assertNotEqual(
                        proc.returncode,
                        0,
                        f"Expected stager failure for case {bad_case}, but succeeded with exit code 0",
                    )
                    self.assertFalse(
                        (root / "dist" / "grok" / "plugins").exists(),
                        f"Stager created partial output for invalid profile case {bad_case}",
                    )


if __name__ == "__main__":
    unittest.main()
