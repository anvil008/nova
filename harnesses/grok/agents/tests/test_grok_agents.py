"""Acceptance tests for Grok Build agent definitions.

Issue #165: Replace ten fallbacks citing the Grok 4.6 guide, using Grok's
distinction between session agents, roles and personas. Declare I/O, capability
modes, model resolution to grok-4.6, and isolation. Preserve read-only roles
through capability/permission mode because no per-agent tool list is verified.

Definition of Done (acceptance tests):
1. ten-grok-roles-resolve-approved-strategy (unit) — oracle:
   Ten roles cite the Grok 4.6 guide and resolve the grok-4.6 pin; unresolved
   inherited model is a hard error.
2. roles-personas-capabilities-are-truthful (unit) — oracle:
   Files parse under documented formats, declare Workcell I/O, use read-only
   modes where required, and invent no tool-list restriction.
3. grok-agent-gates-are-green (integration) — oracle:
   Agent sync, Grok agent evals and parity exit 0 without fallbacks.
"""

from __future__ import annotations

import atexit
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

# Prevent writing bytecode into tracked workspace
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[4]
GROK_AGENTS_DIR = ROOT / "harnesses" / "grok" / "agents"
MODELS_FILE = ROOT / "agents" / "models.json"
CONTRACTS_FILE = ROOT / "contracts" / "harness-contracts.json"

EXPECTED_ROLES = (
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

READ_ONLY_ROLES = {"reviewer", "researcher"}
WRITER_ROLES = {"builder", "debugger", "documenter", "planner", "specifier"}
VALID_CAPABILITY_MODES = {"read-only", "read-write", "execute", "all"}
FORBIDDEN_TOOL_KEYS = {"tools", "allowed-tools", "disallowedTools", "disallowed-tools"}

INAPPLICABLE_GUIDES = {
    "gpt-5.6-sol",
    "gemini-3.7-flash",
    "claude-fable-5-1",
    "claude-opus-5",
    "claude-sonnet-5",
}


def _cleanup_pycache() -> None:
    cache = Path(__file__).resolve().parent / "__pycache__"
    if cache.is_dir():
        shutil.rmtree(cache, ignore_errors=True)


atexit.register(_cleanup_pycache)


def parse_frontmatter(path_or_text: Path | str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter and return (meta, body)."""
    if isinstance(path_or_text, Path):
        text = path_or_text.read_text(encoding="utf-8")
    else:
        text = path_or_text

    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    raw_front = parts[1]
    body = parts[2].lstrip("\n")

    try:
        import yaml

        meta = yaml.safe_load(raw_front)
        if isinstance(meta, dict):
            return meta, body
    except Exception:
        pass

    # Fallback parser for key: value pairs
    meta: dict[str, Any] = {}
    for line in raw_front.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        if ":" in trimmed:
            k, v = trimmed.split(":", 1)
            k, v = k.strip(), v.strip()
            if v.lower() == "true":
                meta[k] = True
            elif v.lower() == "false":
                meta[k] = False
            elif v.isdigit():
                meta[k] = int(v)
            else:
                meta[k] = v.strip("\"'")
    return meta, body


def resolve_grok_role(role: str, manifest: dict[str, Any] | None = None) -> dict[str, str]:
    """Resolve authoritative model for a Grok role.

    Reads agents/models.json (or passed manifest dict).
    Unresolved or inherited models fail with a hard error rather than inheriting
    unspecified parent models.
    """
    if manifest is None:
        manifest = json.loads(MODELS_FILE.read_text(encoding="utf-8"))

    agents = manifest.get("agents", {})
    if role not in agents:
        raise KeyError(f"Unknown or missing role: {role!r}")

    agent_spec = agents[role]
    grok_spec = agent_spec.get("grok", {})
    defaults = manifest.get("defaults", {}).get("grok", {})

    model = grok_spec.get("model") or defaults.get("model")
    if not model or not isinstance(model, str) or not model.strip():
        raise ValueError(f"Missing or empty model for Grok role {role!r}")

    if model == "inherit":
        raise ValueError(
            f"Unresolved inherited model for Grok role {role!r}: must explicitly pin grok-4.6"
        )

    if model != "grok-4.6":
        raise ValueError(
            f"Unapproved model {model!r} for Grok role {role!r}: must pin grok-4.6"
        )

    return {"role": role, "model": model}


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
    elif g == "verification":
        return "verification" in t or "verify" in t
    elif g == "rollback":
        return "rollback" in t
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
    tokens = [w for w in re.findall(r"[a-zA-Z0-9]+", g) if len(w) >= 3]
    return any(tok in t for tok in tokens)


def _check_io_contract(meta: dict[str, Any], body: str) -> tuple[bool, str]:
    """Verify that a role declares Workcell I/O contracts.

    Per docs/models/grok-4.6/prompting.md:
    - Declares inputs and outputs
    - Contract items define name, io_type, required, and description
    Can be declared in YAML frontmatter or in a dedicated section in the body.
    """
    # 1. Frontmatter check
    fm_inputs = meta.get("inputs")
    fm_outputs = meta.get("outputs")
    if isinstance(fm_inputs, list) and isinstance(fm_outputs, list):
        if not fm_inputs or not fm_outputs:
            return False, "Frontmatter inputs and outputs must not be empty"
        for kind, items in (("inputs", fm_inputs), ("outputs", fm_outputs)):
            for item in items:
                if not isinstance(item, dict):
                    return False, f"Frontmatter {kind} item must be a mapping: {item}"
                for field in ("name", "io_type", "required", "description"):
                    if field not in item:
                        return False, f"Frontmatter {kind} item missing required field {field!r}: {item}"
                if not isinstance(item["required"], bool):
                    return False, f"Frontmatter {kind} item 'required' must be boolean: {item}"
        return True, "Valid frontmatter I/O contract"

    # 2. Body section check
    body_lower = body.lower()
    has_io_section = (
        ("## input" in body_lower and "## output" in body_lower)
        or "input and output contract" in body_lower
        or "i/o contract" in body_lower
        or "inputs and outputs" in body_lower
        or ("inputs:" in body_lower and "outputs:" in body_lower)
    )
    if has_io_section:
        has_tokens = (
            "io_type" in body
            and ("required" in body_lower or "optional" in body_lower)
            and "description" in body_lower
            and ("inputs" in body_lower and "outputs" in body_lower)
        )
        if has_tokens:
            return True, "Valid markdown body I/O contract"

    return False, "Missing Workcell I/O contract declaration (expected inputs and outputs with name, io_type, required, and description)"


class GrokAgentsAcceptanceTests(unittest.TestCase):
    """Authoritative acceptance tests for GitHub issue #165 (GrokAgents)."""

    @classmethod
    def tearDownClass(cls) -> None:
        _cleanup_pycache()

    def tearDown(self) -> None:
        _cleanup_pycache()

    def test_ten_grok_roles_resolve_approved_strategy(self) -> None:
        """ten-grok-roles-resolve-approved-strategy (unit):

        Oracle: Ten roles cite the Grok 4.6 guide and resolve the grok-4.6 pin;
        unresolved inherited model is a hard error.
        """
        self.assertTrue(
            GROK_AGENTS_DIR.is_dir(),
            f"Expected Grok agents directory at {GROK_AGENTS_DIR}",
        )

        # 1. Exactly ten definition files exist
        definition_paths = sorted(
            p for p in GROK_AGENTS_DIR.glob("*.md") if p.is_file()
        )
        agent_names = {p.stem for p in definition_paths}
        self.assertEqual(
            len(definition_paths),
            10,
            f"Expected exactly 10 agent definitions under {GROK_AGENTS_DIR}, found {len(definition_paths)}: {agent_names}",
        )
        self.assertEqual(
            agent_names,
            set(EXPECTED_ROLES),
            f"Agent definitions must match the ten Grok roles {set(EXPECTED_ROLES)}",
        )

        # 2. Resolve the grok-4.6 pin; unresolved inherited model is a hard error
        models_data = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
        defaults = models_data.get("defaults", {}).get("grok", {})
        self.assertEqual(
            defaults.get("model"),
            "grok-4.6",
            "Default Grok model in agents/models.json must be 'grok-4.6'",
        )

        for role in EXPECTED_ROLES:
            resolved = resolve_grok_role(role, models_data)
            self.assertEqual(
                resolved["model"],
                "grok-4.6",
                f"Role {role!r} must resolve to 'grok-4.6', got {resolved.get('model')!r}",
            )

        # Hard error verification on synthetic manifests
        with self.assertRaises(ValueError, msg="Empty model must raise ValueError"):
            resolve_grok_role("builder", {"agents": {"builder": {"grok": {"model": ""}}}})

        with self.assertRaises(ValueError, msg="Unresolved inherited model must be a hard error"):
            resolve_grok_role("builder", {"agents": {"builder": {"grok": {"model": "inherit"}}}})

        with self.assertRaises(ValueError, msg="Unapproved model must raise ValueError"):
            resolve_grok_role("builder", {"agents": {"builder": {"grok": {"model": "grok-3"}}}})

        with self.assertRaises(KeyError, msg="Unknown role must raise KeyError"):
            resolve_grok_role("unknown_role", models_data)

        # 3. Each role file frontmatter pins grok-4.6, cites guide, contains no fallback
        for role in EXPECTED_ROLES:
            agent_file = GROK_AGENTS_DIR / f"{role}.md"
            self.assertTrue(
                agent_file.is_file(),
                f"Missing agent definition file {agent_file}",
            )
            meta, body = parse_frontmatter(agent_file)

            # Frontmatter model must be grok-4.6
            self.assertEqual(
                meta.get("model"),
                "grok-4.6",
                f"Role {role!r} frontmatter model must be 'grok-4.6', got {meta.get('model')!r}",
            )

            # Body must cite Grok 4.6 prompting guide
            full_guide_ref = "docs/models/grok-4.6/prompting.md"
            short_guide_ref = "grok-4.6/prompting.md"
            has_guide_citation = (
                full_guide_ref in body
                or short_guide_ref in body
                or "models/grok-4.6" in body
            )
            self.assertTrue(
                has_guide_citation,
                f"Role {role!r} definition must cite the Grok 4.6 guide ({full_guide_ref})",
            )

            # Must NOT cite inapplicable guides
            for other_guide in INAPPLICABLE_GUIDES:
                self.assertNotIn(
                    f"{other_guide}/prompting.md",
                    body,
                    f"Role {role!r} must not cite inapplicable guide {other_guide!r}",
                )

            # Must contain no fallback markers or legacy bodies
            self.assertNotIn(
                "<!-- generated harness-owned procedure: Grok Build -->",
                body,
                f"Role {role!r} definition retains generated harness-owned fallback marker",
            )
            self.assertNotIn(
                "<!-- legacy-shared-body",
                body,
                f"Role {role!r} definition must not retain legacy shared body marker",
            )
            for marker in ("TODO", "FIXME", "STUB"):
                self.assertNotIn(
                    marker,
                    body,
                    f"Role {role!r} definition contains unfinished marker {marker!r}",
                )

    def test_roles_personas_capabilities_are_truthful(self) -> None:
        """roles-personas-capabilities-are-truthful (unit):

        Oracle: Files parse under documented formats, declare Workcell I/O,
        use read-only modes where required, and invent no tool-list restriction.
        """
        registry = json.loads(CONTRACTS_FILE.read_text(encoding="utf-8"))
        agent_contracts = {entry["name"]: entry for entry in registry.get("agents", [])}

        for role in EXPECTED_ROLES:
            agent_file = GROK_AGENTS_DIR / f"{role}.md"
            self.assertTrue(
                agent_file.is_file(),
                f"Missing agent definition file {agent_file}",
            )
            meta, body = parse_frontmatter(agent_file)

            # 1. Files parse under documented formats
            self.assertEqual(
                meta.get("name"),
                role,
                f"Role {role!r} frontmatter name must match filename stem, got {meta.get('name')!r}",
            )
            desc = meta.get("description", "")
            self.assertIsInstance(
                desc, str, f"Role {role!r} description must be a string"
            )
            self.assertTrue(
                bool(desc), f"Role {role!r} description must not be empty"
            )

            # Understands Grok's distinction between session agents, roles and personas
            has_agent_persona_concept = bool(
                re.search(
                    r"persona|\.grok/personas|\.grok/agents|session agent|general-purpose|explore|\bplan\b",
                    body,
                    re.IGNORECASE,
                )
            )
            self.assertTrue(
                has_agent_persona_concept,
                f"Role {role!r} must reflect Grok's distinction between session agents, roles, and personas",
            )

            # 2. Declare Workcell I/O
            io_valid, io_reason = _check_io_contract(meta, body)
            self.assertTrue(
                io_valid,
                f"Role {role!r} {io_reason}",
            )

            # 3. Use read-only modes where required
            if role in READ_ONLY_ROLES:
                perm_mode = meta.get("permission_mode")
                cap_mode = meta.get("capability_mode") or meta.get("capability")
                is_read_only = (
                    perm_mode == "plan"
                    or cap_mode == "read-only"
                    or "read-only" in body.lower()
                )
                self.assertTrue(
                    is_read_only,
                    f"Read-only role {role!r} must declare read-only mode (permission_mode: plan or capability_mode: read-only)",
                )
                self.assertTrue(
                    bool(re.search(r"read-only", body, re.IGNORECASE)),
                    f"Read-only role {role!r} instructions must enforce read-only operation",
                )
            elif role in WRITER_ROLES:
                perm_mode = meta.get("permission_mode")
                cap_mode = meta.get("capability_mode") or meta.get("capability")
                self.assertNotEqual(
                    perm_mode,
                    "plan",
                    f"Write-capable role {role!r} must not declare permission_mode: plan",
                )
                self.assertNotEqual(
                    cap_mode,
                    "read-only",
                    f"Write-capable role {role!r} must not declare capability_mode: read-only",
                )

            # If capability mode is declared, it must be from valid modes
            declared_cap = meta.get("capability_mode") or meta.get("capability")
            if declared_cap:
                self.assertIn(
                    declared_cap,
                    VALID_CAPABILITY_MODES,
                    f"Role {role!r} declared invalid capability mode {declared_cap!r}",
                )

            # 4. Invent no tool-list restriction
            for forbidden_key in FORBIDDEN_TOOL_KEYS:
                self.assertNotIn(
                    forbidden_key,
                    meta,
                    f"Role {role!r} frontmatter must NOT declare {forbidden_key!r}; "
                    "no per-agent tool list is verified in Grok Build",
                )

            # 5. Contract parity and isolation
            contract = agent_contracts.get(role)
            self.assertIsNotNone(
                contract,
                f"Role {role!r} missing from contracts registry {CONTRACTS_FILE}",
            )

            # Handoff schema
            handoff_schema = contract.get("handoffSchema")
            if handoff_schema:
                self.assertIn(
                    handoff_schema,
                    body,
                    f"Role {role!r} instructions must reference handoff schema {handoff_schema!r}",
                )

            # Ordered gates representation
            for gate in contract.get("orderedGates", []):
                self.assertTrue(
                    _gate_is_represented(gate, body),
                    f"Role {role!r} instructions must represent ordered gate {gate!r}",
                )

            # Isolation: no commit to main
            has_isolation = bool(
                re.search(
                    r"never commit (?:directly )?to [`']?main[`']?|isolated|workspace",
                    body,
                    re.IGNORECASE,
                )
            )
            self.assertTrue(
                has_isolation,
                f"Role {role!r} instructions must preserve isolation (workspace, never commit to main)",
            )

    def test_grok_agent_gates_are_green(self) -> None:
        """grok-agent-gates-are-green (integration):

        Oracle: Agent sync, Grok agent evals and parity exit 0 without fallbacks.
        """
        # 1. No fallbacks survive across any Grok agent definitions
        for role in EXPECTED_ROLES:
            agent_file = GROK_AGENTS_DIR / f"{role}.md"
            self.assertTrue(
                agent_file.is_file(),
                f"Missing agent definition file {agent_file}",
            )
            raw = agent_file.read_text(encoding="utf-8")
            self.assertNotIn(
                "<!-- generated harness-owned procedure: Grok Build -->",
                raw,
                f"Role {role!r} retains generated harness-owned procedure fallback",
            )
            self.assertNotIn(
                "<!-- legacy-shared-body",
                raw,
                f"Role {role!r} retains legacy shared body fallback marker",
            )
            meta, body = parse_frontmatter(raw)
            self.assertNotIn(
                "fallback",
                body.lower(),
                f"Role {role!r} body contains forbidden fallback marker or text",
            )

        # 2. Agent sync check exits 0
        sync_result = subprocess.run(
            ["python3", "scripts/sync-agents.py", "--check", "--diff"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            sync_result.returncode,
            0,
            f"scripts/sync-agents.py --check --diff failed:\n{sync_result.stdout}\n{sync_result.stderr}",
        )

        # 3. Contract parity exits 0
        parity_result = subprocess.run(
            ["python3", "scripts/check-contract-parity.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            parity_result.returncode,
            0,
            f"scripts/check-contract-parity.py failed:\n{parity_result.stdout}\n{parity_result.stderr}",
        )

        # 4. Evals contract parity exits 0
        evals_parity_result = subprocess.run(
            ["python3", "evals/run_evals.py", "--contract-parity"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            evals_parity_result.returncode,
            0,
            f"evals/run_evals.py --contract-parity failed:\n{evals_parity_result.stdout}\n{evals_parity_result.stderr}",
        )

        # 5. Grok agent evals exit 0
        evals_grok_result = subprocess.run(
            [
                "python3",
                "evals/run_evals.py",
                "--structural",
                "--harness",
                "grok",
                "--root",
                str(ROOT),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            evals_grok_result.returncode,
            0,
            f"evals/run_evals.py --structural --harness grok failed:\n{evals_grok_result.stdout}\n{evals_grok_result.stderr}",
        )

        # 6. Grok plugin builds and stages all 10 agents
        plugin_build_result = subprocess.run(
            ["python3", "scripts/build-grok-plugin.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            plugin_build_result.returncode,
            0,
            f"scripts/build-grok-plugin.py failed:\n{plugin_build_result.stdout}\n{plugin_build_result.stderr}",
        )
        staged_agents_dir = ROOT / "dist" / "grok" / "plugins" / "workcell" / "agents"
        self.assertTrue(
            staged_agents_dir.is_dir(),
            f"Expected staged agents directory at {staged_agents_dir}",
        )
        for role in EXPECTED_ROLES:
            staged_agent_file = staged_agents_dir / f"{role}.md"
            self.assertTrue(
                staged_agent_file.is_file(),
                f"Role {role!r} missing from staged plugin at {staged_agent_file}",
            )


if __name__ == "__main__":
    unittest.main()
