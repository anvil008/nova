"""Acceptance tests for Codex agent definitions (issue #159).

Verifies that:
1. ten-codex-agents-resolve-routes (unit): Ten roles resolve non-empty
   gpt-5.6-sol/allowed effort; missing or unavailable routes fail rather than inherit.
2. toml-agents-and-profiles-agree (integration): Generated TOML/profile files parse
   and agree on model/effort/isolation; one mutation makes --check name the file.
3. dispatches-use-bounded-forks (unit): Every specialist dispatch requires exact
   model/effort, none or smallest bounded fork, and complete assignment/acceptance
   message; no full-history override remains.
"""

from __future__ import annotations

import atexit
import importlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from typing import Any

# Suppress bytecode generation
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

AGENTS_DIR = ROOT / "harnesses" / "codex" / "agents"
MODELS_FILE = ROOT / "agents" / "models.json"
CONTRACTS_PATH = ROOT / "contracts" / "harness-contracts.json"
SYNC_SCRIPT = ROOT / "scripts" / "sync-agent-models.py"

CODEX_ROLES = (
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

ALLOWED_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
READ_ONLY_ROLES = {"reviewer", "researcher"}
WRITER_ROLES = {"builder", "specifier", "deployer", "documenter"}


def _cleanup_pycache() -> None:
    for cache_dir in (
        Path(__file__).parent / "__pycache__",
        ROOT / "harnesses" / "codex" / "agents" / "tests" / "__pycache__",
        ROOT / "scripts" / "__pycache__",
        ROOT / "agents" / "__pycache__",
    ):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir, ignore_errors=True)


atexit.register(_cleanup_pycache)


def parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter and return (metadata, body)."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text

    frontmatter_lines: list[str] = []
    body_start_idx = 1
    found_closing = False

    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            found_closing = True
            body_start_idx = idx + 1
            break
        frontmatter_lines.append(line)

    if not found_closing:
        return {}, text

    metadata: dict[str, Any] = {}
    for line in frontmatter_lines:
        line_str = line.strip()
        if not line_str or line_str.startswith("#"):
            continue
        if ":" in line_str:
            key, val = line_str.split(":", 1)
            metadata[key.strip()] = val.strip()

    body = "".join(lines[body_start_idx:]).lstrip()
    return metadata, body


def resolve_codex_role(role: str, manifest: dict | None = None) -> dict[str, str]:
    """Resolve authoritative model and effort for a Codex role.

    Reads agents/models.json (or passed manifest dict).
    Missing or unavailable routes fail rather than inherit.
    """
    if manifest is None:
        manifest = json.loads(MODELS_FILE.read_text(encoding="utf-8"))

    agents = manifest.get("agents", {})
    if role not in agents:
        raise KeyError(f"Unknown or missing role: {role!r}")

    agent_spec = agents[role]
    codex_spec = agent_spec.get("codex", {})
    defaults = manifest.get("defaults", {}).get("codex", {})

    # Model: must be explicit in codex_spec or defaults, non-empty
    model = codex_spec.get("model") or defaults.get("model")
    if not model or not isinstance(model, str) or not model.strip():
        raise ValueError(f"Missing or empty model for role {role!r}")

    # Effort: must be specified and in ALLOWED_EFFORTS
    effort = codex_spec.get("effort") or defaults.get("effort")
    if not effort or effort not in ALLOWED_EFFORTS:
        raise ValueError(f"Invalid or unavailable effort {effort!r} for role {role!r}")

    return {"role": role, "model": model, "effort": effort}


def _gate_is_represented(gate: str, text: str) -> bool:
    """Verify that a contract ordered gate is meaningfully represented in instructions."""
    g = gate.lower()
    t = text.lower()
    if g == "sealed tests":
        return "seal" in t and "test" in t
    elif g == "green":
        return "green" in t
    elif g == "runtime proof":
        return "runtime" in t or "proof" in t or "evidence" in t
    elif g == "two reviews":
        return "two" in t and ("review" in t or "pass" in t)
    elif g == "pull request":
        return "pull request" in t or " pr" in t
    elif g == "acceptance test":
        return "acceptance" in t and "test" in t
    elif g == "red proof":
        return "red" in t
    elif g == "seal":
        return "seal" in t
    elif g == "builder handoff":
        return "handoff" in t and "builder" in t
    elif g == "assigned lens":
        return "lens" in t
    elif g == "evidence":
        return "evidence" in t
    elif g == "severity":
        return "severity" in t
    elif g == "handoff":
        return "handoff" in t
    elif g == "combined change-set":
        return "combined" in t or "change-set" in t or "changeset" in t or "wave" in t
    elif g == "full gates":
        return "gate" in t or "suite" in t
    elif g == "runtime verification":
        return "verification" in t or "verify" in t or "runtime" in t
    elif g == "truth inspection":
        return "truth" in t or "inspection" in t or "reality" in t
    elif g == "scoped edit":
        return "scope" in t or "edit" in t
    elif g == "docs validation":
        return "validation" in t or "doc" in t or "check" in t
    elif g == "benchmark harness":
        return "benchmark" in t or "harness" in t
    elif g == "distribution":
        return "distribution" in t or "rate" in t
    elif g == "comparison":
        return "comparison" in t or "compare" in t or "baseline" in t
    elif g == "one area":
        return "area" in t or "one" in t
    elif g == "read-only evidence":
        return "read-only" in t or "evidence" in t
    elif g == "structured findings":
        return "finding" in t or "structure" in t
    elif g == "approval":
        return "approval" in t
    elif g == "preflight":
        return "preflight" in t or "pre-flight" in t
    elif g == "release":
        return "release" in t
    elif g == "reproduce":
        return "reproduce" in t or "symptom" in t
    elif g == "hypotheses":
        return "hypothes" in t
    elif g == "root cause":
        return "root cause" in t or "cause" in t
    elif g == "read-only investigation":
        return "read-only" in t or "investigation" in t
    elif g == "plan folio":
        return "folio" in t or "plan" in t
    elif g == "strict sidecar":
        return "sidecar" in t
    elif g == "human approval":
        return "approval" in t or "human" in t
    elif g == "verification":
        return "verification" in t or "verify" in t
    elif g == "rollback":
        return "rollback" in t
    return True


class CodexAgentsAcceptanceTests(unittest.TestCase):
    """Authoritative acceptance tests for GitHub issue #159 (CodexAgents)."""

    def test_ten_codex_agents_resolve_routes(self) -> None:
        """ten-codex-agents-resolve-routes (unit):
        Ten roles resolve non-empty gpt-5.6-sol/allowed effort; missing or
        unavailable routes fail rather than inherit.
        """
        # 1. Exactly ten markdown files exist directly under harnesses/codex/agents/
        definition_files = {p.stem: p for p in AGENTS_DIR.glob("*.md") if p.is_file()}
        self.assertEqual(
            set(definition_files.keys()),
            set(CODEX_ROLES),
            f"Expected exactly ten roles {set(CODEX_ROLES)}, got {set(definition_files.keys())}",
        )
        self.assertEqual(len(definition_files), 10)

        # 2. Authoritative model and allowed effort resolution from agents/models.json
        models_data = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
        for role in CODEX_ROLES:
            resolved = resolve_codex_role(role, models_data)
            self.assertEqual(
                resolved["model"],
                "gpt-5.6-sol",
                f"Role {role} must resolve model 'gpt-5.6-sol', got {resolved['model']}",
            )
            self.assertIn(
                resolved["effort"],
                ALLOWED_EFFORTS,
                f"Role {role} must resolve an allowed effort in {ALLOWED_EFFORTS}, got {resolved['effort']}",
            )

            # Frontmatter check
            meta, body = parse_frontmatter(definition_files[role])
            self.assertEqual(meta.get("name"), role)
            self.assertEqual(meta.get("model"), "gpt-5.6-sol")
            self.assertEqual(meta.get("model_reasoning_effort"), resolved["effort"])
            self.assertTrue(
                bool(meta.get("description")),
                f"Role {role} must define non-empty description",
            )

        # 3. Missing or unavailable routes fail rather than inherit
        with self.assertRaises(KeyError, msg="Missing role must fail rather than inherit"):
            resolve_codex_role("nonexistent-role", models_data)

        # Missing model fails rather than inherits
        bad_manifest_missing_model = {
            "defaults": {"codex": {"model": "", "effort": "medium"}},
            "agents": {"builder": {"codex": {"effort": "high"}}},
        }
        with self.assertRaises(ValueError, msg="Missing model must fail rather than inherit"):
            resolve_codex_role("builder", bad_manifest_missing_model)

        # Unavailable/invalid effort fails rather than inherits
        bad_manifest_bad_effort = {
            "defaults": {"codex": {"model": "gpt-5.6-sol", "effort": "unsupported-effort"}},
            "agents": {"builder": {"codex": {"model": "gpt-5.6-sol", "effort": "turbo"}}},
        }
        with self.assertRaises(ValueError, msg="Unavailable effort must fail rather than inherit"):
            resolve_codex_role("builder", bad_manifest_bad_effort)

        # Build-codex-plugin codex_routing verification
        build_codex_mod = importlib.import_module("build-codex-plugin")
        codex_routing = getattr(build_codex_mod, "codex_routing")
        BuildError = getattr(build_codex_mod, "BuildError")
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            f.write(json.dumps({"defaults": {}, "agents": {"builder": {"codex": {"model": ""}}}}))
            f.flush()
            with self.assertRaises(BuildError):
                codex_routing(Path(f.name))

        # 4. Contracts from harness-contracts.json
        contracts_data = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))
        agent_contracts = {entry["name"]: entry for entry in contracts_data.get("agents", [])}
        for role in CODEX_ROLES:
            contract = agent_contracts.get(role)
            self.assertIsNotNone(contract, f"Missing contract for role {role}")
            meta, body = parse_frontmatter(definition_files[role])

            # Required values for codex: ["body", "model", "effort"]
            for req in contract.get("requiredValues", {}).get("codex", []):
                if req == "body":
                    self.assertTrue(bool(body.strip()), f"Role {role} body must be non-empty")
                elif req == "model":
                    self.assertEqual(meta.get("model"), "gpt-5.6-sol")
                elif req == "effort":
                    self.assertIn(meta.get("model_reasoning_effort"), ALLOWED_EFFORTS)

            # Handoff schema
            self.assertEqual(contract.get("handoffSchema"), "anvil.agent-handoff/v1")
            self.assertIn("anvil.agent-handoff/v1", body)

            # Ordered gates
            for gate in contract.get("orderedGates", []):
                self.assertTrue(
                    _gate_is_represented(gate, body),
                    f"Role {role} must represent gate {gate!r}",
                )

        # 5. Official GPT-5.6 Sol guide citations
        for role in CODEX_ROLES:
            meta, body = parse_frontmatter(definition_files[role])
            has_sol_guide = bool(
                re.search(
                    r"docs/models/gpt-5\.6-sol/prompting\.md|gpt-5\.6-sol/prompting\.md",
                    body,
                )
            )
            self.assertTrue(
                has_sol_guide,
                f"Role {role} must cite official GPT-5.6 Sol guide (docs/models/gpt-5.6-sol/prompting.md)",
            )
            self.assertNotIn("claude-fable", body.lower())
            self.assertNotIn("claude-opus", body.lower())
            self.assertNotIn("claude-sonnet", body.lower())
            self.assertNotIn("gemini-3.7-flash", body.lower())
            self.assertNotIn("grok-4.6", body.lower())

        # 6. No fallback markers
        for role in CODEX_ROLES:
            meta, body = parse_frontmatter(definition_files[role])
            self.assertNotIn(
                "<!-- generated harness-owned procedure: Codex -->",
                body,
                f"Role {role} contains fallback marker '<!-- generated harness-owned procedure: Codex -->'",
            )
            self.assertNotIn("<!-- legacy-shared-body", body)
            self.assertNotIn("<!-- TODO", body)
            self.assertNotIn("<!-- FIXME", body)
            self.assertNotIn("<!-- STUB", body)

    def test_toml_agents_and_profiles_agree(self) -> None:
        """toml-agents-and-profiles-agree (integration):
        Generated TOML/profile files parse and agree on model/effort/isolation;
        one mutation makes --check name the file.
        """
        # 1. Generate profiles in a temporary directory and verify parsing
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            models_data = json.loads(MODELS_FILE.read_text(encoding="utf-8"))

            gen_proc = subprocess.run(
                [
                    sys.executable,
                    str(SYNC_SCRIPT),
                    "--codex-profiles",
                    "--codex-home",
                    str(codex_home),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                gen_proc.returncode,
                0,
                f"Failed to generate Codex profiles:\n{gen_proc.stderr}",
            )

            # Verify every profile exists, parses with tomllib, and agrees with models.json & frontmatter
            for role in CODEX_ROLES:
                profile_path = codex_home / f"workcell-{role}.config.toml"
                self.assertTrue(profile_path.is_file(), f"Missing profile {profile_path}")

                profile_text = profile_path.read_text(encoding="utf-8")
                parsed = tomllib.loads(profile_text)

                expected_route = resolve_codex_role(role, models_data)
                meta, body = parse_frontmatter(AGENTS_DIR / f"{role}.md")

                # Agreement on model
                self.assertEqual(parsed.get("model"), "gpt-5.6-sol")
                self.assertEqual(parsed.get("model"), expected_route["model"])
                self.assertEqual(parsed.get("model"), meta.get("model"))

                # Agreement on effort
                self.assertEqual(parsed.get("model_reasoning_effort"), expected_route["effort"])
                self.assertEqual(parsed.get("model_reasoning_effort"), meta.get("model_reasoning_effort"))

                # Agreement on capability / read-only isolation
                if role in READ_ONLY_ROLES:
                    self.assertTrue(
                        bool(re.search(r"\bread-only\b", body, re.IGNORECASE)),
                        f"Read-only role {role} must assert read-only boundary in body",
                    )
                    self.assertTrue(
                        bool(re.search(r"no edits|never mutate|never edit", body, re.IGNORECASE)),
                        f"Read-only role {role} must declare no-edits/never-mutate in body",
                    )
                    if "sandbox" in parsed:
                        self.assertEqual(parsed["sandbox"], "read-only")
                    if "isolation" in parsed:
                        self.assertEqual(parsed["isolation"], "read-only")
                elif role in WRITER_ROLES:
                    self.assertNotEqual(parsed.get("sandbox"), "read-only")
                    self.assertNotEqual(parsed.get("isolation"), "read-only")

            # Check any custom TOML agent files in harnesses/codex/agents/
            for toml_agent in AGENTS_DIR.glob("*.toml"):
                toml_data = tomllib.loads(toml_agent.read_text(encoding="utf-8"))
                role = toml_agent.stem
                if role in CODEX_ROLES:
                    expected_route = resolve_codex_role(role, models_data)
                    self.assertEqual(toml_data.get("model"), expected_route["model"])
                    self.assertEqual(toml_data.get("model_reasoning_effort"), expected_route["effort"])

            # 2. Verify drift check passes initially
            check_proc = subprocess.run(
                [
                    sys.executable,
                    str(SYNC_SCRIPT),
                    "--check",
                    "--codex-profiles",
                    "--codex-home",
                    str(codex_home),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                check_proc.returncode,
                0,
                f"Initial check failed:\n{check_proc.stdout}\n{check_proc.stderr}",
            )

            # 3. Mutation test: one mutation makes --check name the file
            for mutated_role, mutated_key, mutated_val in (
                ("builder", "model_reasoning_effort", "low"),
                ("reviewer", "model", "gpt-5.6-mutated"),
            ):
                target_file = codex_home / f"workcell-{mutated_role}.config.toml"
                original_content = target_file.read_text(encoding="utf-8")

                # Apply mutation
                if mutated_key == "model_reasoning_effort":
                    mutated_content = re.sub(
                        r'model_reasoning_effort\s*=\s*"[^"]+"',
                        f'model_reasoning_effort = "{mutated_val}"',
                        original_content,
                    )
                else:
                    mutated_content = re.sub(
                        r'model\s*=\s*"[^"]+"',
                        f'model = "{mutated_val}"',
                        original_content,
                    )
                target_file.write_text(mutated_content, encoding="utf-8")

                mut_check = subprocess.run(
                    [
                        sys.executable,
                        str(SYNC_SCRIPT),
                        "--check",
                        "--codex-profiles",
                        "--codex-home",
                        str(codex_home),
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(
                    mut_check.returncode,
                    0,
                    f"Drift check should fail when {target_file.name} is mutated",
                )
                combined_output = mut_check.stdout + mut_check.stderr
                self.assertIn(
                    target_file.name,
                    combined_output,
                    f"Output of --check must explicitly name mutated file {target_file.name}:\n{combined_output}",
                )

                # Revert mutation
                target_file.write_text(original_content, encoding="utf-8")

            # Final verify check is clean after restoring
            recheck_proc = subprocess.run(
                [
                    sys.executable,
                    str(SYNC_SCRIPT),
                    "--check",
                    "--codex-profiles",
                    "--codex-home",
                    str(codex_home),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(recheck_proc.returncode, 0)

    def test_dispatches_use_bounded_forks(self) -> None:
        """dispatches-use-bounded-forks (unit):
        Every specialist dispatch requires exact model/effort, none or smallest
        bounded fork, and complete assignment/acceptance message; no full-history
        override remains.
        """
        # 1. Generated dispatch contract enforces bounded forks and exact models
        build_codex_mod = importlib.import_module("build-codex-plugin")
        codex_dispatch_contract = getattr(build_codex_mod, "codex_dispatch_contract")
        codex_routing = getattr(build_codex_mod, "codex_routing")

        routing = codex_routing(MODELS_FILE)
        contract_text = codex_dispatch_contract(routing)

        self.assertIn("spawn_agent", contract_text)
        self.assertIn("fork_turns", contract_text)
        self.assertIn("none", contract_text)
        self.assertIn("smallest positive number", contract_text)
        self.assertIn("cannot use a full-history fork", contract_text)
        self.assertIn(
            "complete assignment and acceptance criteria in `message`",
            contract_text,
        )
        self.assertIn("do not silently fall back to the parent", contract_text)

        for role in CODEX_ROLES:
            expected_effort = routing[role]["effort"]
            self.assertIn(
                f"- `{role}`: `model=gpt-5.6-sol`, `reasoning_effort={expected_effort}`",
                contract_text,
            )

        # 2. Builder agent dispatch instructions require bounded forks and exact model/effort
        builder_file = AGENTS_DIR / "builder.md"
        meta, builder_body = parse_frontmatter(builder_file)

        # Must mention spawn_agent and reviewer dispatch
        self.assertIn("spawn_agent", builder_body)
        self.assertIn("reviewer", builder_body)

        # Specialist dispatch must require exact model and reasoning_effort
        self.assertTrue(
            bool(
                re.search(
                    r"exact\s+(?:`?model`?\s+and\s+`?reasoning_effort`?|model/effort)",
                    builder_body,
                    re.IGNORECASE,
                )
            )
            or ("model" in builder_body and "reasoning_effort" in builder_body),
            "Builder dispatch instructions must specify exact model and reasoning_effort",
        )

        # Specialist dispatch must require bounded fork context
        self.assertIn(
            "fork_turns",
            builder_body,
            "Builder dispatch instructions must require setting fork_turns",
        )
        self.assertTrue(
            bool(re.search(r"fork_turns.*(?:none|smallest|\d+)", builder_body, re.IGNORECASE)),
            "Builder dispatch instructions must specify fork_turns as none or smallest bounded integer",
        )

        # Must explicitly forbid full-history forks
        self.assertTrue(
            bool(
                re.search(
                    r"(?:cannot|never|no)\s+(?:use\s+)?(?:a\s+)?full-history",
                    builder_body,
                    re.IGNORECASE,
                )
            ),
            "Builder dispatch instructions must forbid full-history forks",
        )

        # Must require complete assignment and acceptance in message
        self.assertTrue(
            bool(
                re.search(
                    r"complete assignment|acceptance criteria",
                    builder_body,
                    re.IGNORECASE,
                )
            ),
            "Builder dispatch instructions must instruct putting complete assignment and acceptance criteria in message",
        )

        # 3. Across all Codex agent definitions, no full-history override remains
        for doc in AGENTS_DIR.glob("*.md"):
            doc_text = doc.read_text(encoding="utf-8")
            self.assertNotIn(
                "fork_turns: full",
                doc_text,
                f"{doc.name} must not contain full-history override 'fork_turns: full'",
            )
            self.assertNotIn(
                "fork_turns=full",
                doc_text,
                f"{doc.name} must not contain full-history override 'fork_turns=full'",
            )
            self.assertNotIn(
                "fork_turns: all",
                doc_text,
                f"{doc.name} must not contain full-history override 'fork_turns: all'",
            )


if __name__ == "__main__":
    unittest.main()
