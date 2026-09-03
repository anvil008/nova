"""Acceptance tests for Antigravity agent definitions.

Issue #162: Replace ten fallbacks with Gemini/Antigravity-native agents using async
fresh-context subagents and truthful tools. Preserve Flash routing; omit per-agent
effort with note because effort is session-wide. Workspace modes must respect
ownership/isolation.

Definition of Done (acceptance tests):
1. ten-agy-agents-have-truthful-frontmatter (unit) — oracle:
   Ten agents parse with supported tools/policy/main/subagent/Flash; no per-agent
   effort exists and one note explains it.
2. agy-delegation-is-async-and-owned (unit) — oracle:
   Allowed roles use invoke_subagent with fresh context/explicit workspace; parallel
   writers require disjoint ownership and read-only roles cannot request edits.
3. agy-agent-gates-are-green (integration) — oracle:
   Agent sync, agy agent evals and parity exit 0 without fallbacks.
"""

from __future__ import annotations

import atexit
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Prevent writing bytecode into tracked workspace
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[4]
AGY_AGENTS_DIR = ROOT / "harnesses" / "agy" / "agents"
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

ALLOWED_DELEGATION_ROLES = {"builder"}
READ_ONLY_ROLES = {"reviewer", "researcher"}

VALID_AGY_TOOLS = {
    "view_file",
    "grep_search",
    "find_by_name",
    "list_dir",
    "replace_file_content",
    "write_to_file",
    "run_command",
    "invoke_subagent",
    "define_subagent",
    "manage_subagents",
    "send_message",
    "schedule",
    "manage_task",
    "call_mcp_tool",
    "list_resources",
    "read_resource",
    "read_url_content",
    "generate_image",
    "ask_question",
}


def _cleanup_pycache() -> None:
    cache = Path(__file__).resolve().parent / "__pycache__"
    if cache.is_dir():
        shutil.rmtree(cache, ignore_errors=True)


atexit.register(_cleanup_pycache)


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Parse YAML frontmatter and return (meta, body)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    raw_front = parts[1]
    body = parts[2].lstrip("\n")

    meta: dict[str, object] = {}
    current_key: str | None = None
    for line in raw_front.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        if trimmed.startswith("- ") and current_key:
            val = trimmed[2:].strip().strip("\"'")
            cast = meta.get(current_key)
            if isinstance(cast, list):
                cast.append(val)
            continue
        if ":" in trimmed:
            k, v = trimmed.split(":", 1)
            k = k.strip()
            v = v.strip()
            current_key = k
            if not v:
                meta[k] = []
            elif v.lower() == "true":
                meta[k] = True
            elif v.lower() == "false":
                meta[k] = False
            elif v.isdigit():
                meta[k] = int(v)
            else:
                meta[k] = v.strip("\"'")
        else:
            current_key = None
    return meta, body


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
        return "reproduce" in t
    elif g == "hypotheses":
        return "hypothes" in t
    elif g == "root cause":
        return "root cause" in t or "cause" in t
    elif g == "read-only investigation":
        return "read-only" in t and "investigat" in t
    elif g == "plan folio":
        return "folio" in t
    elif g == "strict sidecar":
        return "sidecar" in t
    elif g == "human approval":
        return "human" in t or "approval" in t
    tokens = [w for w in re.findall(r"[a-zA-Z0-9]+", g) if len(w) >= 3]
    return any(tok in t for tok in tokens)


class AntigravityAgentsAcceptanceTests(unittest.TestCase):
    """Acceptance tests for Antigravity-native agent definitions."""

    @classmethod
    def tearDownClass(cls) -> None:
        _cleanup_pycache()

    def tearDown(self) -> None:
        _cleanup_pycache()

    def test_ten_agy_agents_have_truthful_frontmatter(self) -> None:
        """ten-agy-agents-have-truthful-frontmatter (unit):

        Oracle: Ten agents parse with supported tools/policy/main/subagent/Flash;
        no per-agent effort exists and one note explains it.
        """
        self.assertTrue(
            AGY_AGENTS_DIR.is_dir(),
            f"Expected Antigravity agents directory at {AGY_AGENTS_DIR}",
        )

        agent_dirs = sorted(
            p.name for p in AGY_AGENTS_DIR.iterdir() if p.is_dir() and p.name != "tests"
        )
        self.assertEqual(
            agent_dirs,
            list(EXPECTED_ROLES),
            f"Expected exactly 10 agent directories under {AGY_AGENTS_DIR}, got {agent_dirs}",
        )

        for role in EXPECTED_ROLES:
            agent_file = AGY_AGENTS_DIR / role / "agent.md"
            self.assertTrue(
                agent_file.is_file(),
                f"Missing agent definition file {agent_file}",
            )

            raw = agent_file.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(raw)

            # Name and description
            self.assertEqual(
                meta.get("name"),
                role,
                f"Role {role!r} frontmatter name must match directory name, got {meta.get('name')!r}",
            )
            desc = meta.get("description", "")
            self.assertIsInstance(
                desc, str, f"Role {role!r} description must be a string"
            )
            self.assertTrue(bool(desc), f"Role {role!r} description must not be empty")
            self.assertLessEqual(
                len(str(desc)),
                1024,
                f"Role {role!r} description exceeds 1024 chars",
            )

            # Model routing: preserve Flash routing
            self.assertEqual(
                meta.get("model"),
                "flash",
                f"Role {role!r} must route to 'flash', got {meta.get('model')!r}",
            )

            # Execution policy and agent flags
            self.assertEqual(
                meta.get("commandExecutionPolicy"),
                "sandbox",
                f"Role {role!r} commandExecutionPolicy must be 'sandbox'",
            )
            self.assertTrue(
                meta.get("mainAgent") is True,
                f"Role {role!r} mainAgent must be True",
            )
            self.assertTrue(
                meta.get("subagent") is True,
                f"Role {role!r} subagent must be True",
            )

            # Truthful tools
            tools = meta.get("tools")
            self.assertIsInstance(tools, list, f"Role {role!r} tools must be a list")
            tool_set = set(tools)
            invalid_tools = tool_set - VALID_AGY_TOOLS
            self.assertFalse(
                invalid_tools,
                f"Role {role!r} declares unsupported Antigravity tools: {sorted(invalid_tools)}",
            )

            # Omit per-agent effort with note because effort is session-wide
            self.assertNotIn(
                "effort",
                meta,
                f"Role {role!r} frontmatter must NOT declare per-agent effort; effort is session-wide in Antigravity",
            )
            self.assertNotIn(
                "model_reasoning_effort",
                meta,
                f"Role {role!r} frontmatter must NOT declare model_reasoning_effort",
            )

            # Body must contain a note explaining why effort is omitted / session-wide
            has_effort_note = bool(
                re.search(
                    r"effort.*(?:session-wide|session wide|session-level)|(?:session-wide|session wide).*effort|/effort|--effort",
                    body,
                    re.IGNORECASE,
                )
            )
            self.assertTrue(
                has_effort_note,
                f"Role {role!r} instructions must explain that reasoning effort is session-wide",
            )

            # Model guide citation
            has_guide_citation = bool(
                re.search(
                    r"docs/models/gemini-3\.7-flash/prompting\.md|gemini-3\.7-flash/prompting\.md",
                    body,
                )
            )
            self.assertTrue(
                has_guide_citation,
                f"Role {role!r} instructions must cite the official Gemini 3.7 Flash prompting guide (docs/models/gemini-3.7-flash/prompting.md)",
            )

            # Ensure Teamwork is not conflated as a model feature
            self.assertFalse(
                bool(
                    re.search(
                        r"teamwork is a (?:model|gemini) feature",
                        body,
                        re.IGNORECASE,
                    )
                ),
                f"Role {role!r} must not misstate Teamwork as a model feature",
            )

    def test_agy_delegation_is_async_and_owned(self) -> None:
        """agy-delegation-is-async-and-owned (unit):

        Oracle: Allowed roles use invoke_subagent with fresh context/explicit workspace;
        parallel writers require disjoint ownership and read-only roles cannot request edits.
        """
        for role in EXPECTED_ROLES:
            agent_file = AGY_AGENTS_DIR / role / "agent.md"
            self.assertTrue(
                agent_file.is_file(), f"Missing agent definition {agent_file}"
            )
            raw = agent_file.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(raw)
            tools = set(meta.get("tools", []))

            if role in ALLOWED_DELEGATION_ROLES:
                # Allowed roles use invoke_subagent
                self.assertIn(
                    "invoke_subagent",
                    tools,
                    f"Delegating role {role!r} must declare 'invoke_subagent' in tools",
                )
                self.assertIn(
                    "invoke_subagent",
                    body,
                    f"Delegating role {role!r} instructions must reference 'invoke_subagent'",
                )

                # Fresh context
                has_fresh_context = bool(
                    re.search(
                        r"fresh[- ]context|fresh conversation|independent context|new context",
                        body,
                        re.IGNORECASE,
                    )
                )
                self.assertTrue(
                    has_fresh_context,
                    f"Role {role!r} delegation instructions must mandate fresh context for subagents",
                )

                # Explicit workspace mode
                has_explicit_workspace = bool(
                    re.search(
                        r"""workspace\s*(?::\s*['"]?(?:inherit|branch|share)['"]?|['"](?:inherit|branch|share)['"])""",
                        body,
                        re.IGNORECASE,
                    )
                )
                self.assertTrue(
                    has_explicit_workspace,
                    f"Role {role!r} delegation instructions must specify explicit workspace modes (inherit, branch, or share)",
                )

                # Parallel writers require disjoint ownership
                has_disjoint_ownership = bool(
                    re.search(
                        r"disjoint ownership",
                        body,
                        re.IGNORECASE,
                    )
                )
                self.assertTrue(
                    has_disjoint_ownership,
                    f"Role {role!r} instructions must state that parallel writers require disjoint ownership",
                )
            else:
                # Disallowed roles must not have invoke_subagent
                self.assertNotIn(
                    "invoke_subagent",
                    tools,
                    f"Non-delegating role {role!r} must NOT declare 'invoke_subagent' in tools",
                )

            # Read-only roles cannot request edits
            if role in READ_ONLY_ROLES:
                self.assertNotIn(
                    "write_to_file",
                    tools,
                    f"Read-only role {role!r} must not have 'write_to_file' tool",
                )
                self.assertNotIn(
                    "replace_file_content",
                    tools,
                    f"Read-only role {role!r} must not have 'replace_file_content' tool",
                )
                has_cannot_request_edits = bool(
                    re.search(
                        r"cannot request edits",
                        body,
                        re.IGNORECASE,
                    )
                )
                self.assertTrue(
                    has_cannot_request_edits,
                    f"Read-only role {role!r} instructions must explicitly state that the role cannot request edits",
                )

    def test_agy_agent_gates_are_green(self) -> None:
        """agy-agent-gates-are-green (integration):

        Oracle: Agent sync, agy agent evals and parity exit 0 without fallbacks.
        """
        # 1. No fallbacks in any agent definition
        for role in EXPECTED_ROLES:
            agent_file = AGY_AGENTS_DIR / role / "agent.md"
            self.assertTrue(
                agent_file.is_file(), f"Missing agent definition {agent_file}"
            )
            raw = agent_file.read_text(encoding="utf-8")
            _, body = parse_frontmatter(raw)
            lower_body = body.lower()

            self.assertNotIn(
                "fallback",
                lower_body,
                f"Role {role!r} definition contains forbidden fallback marker or text",
            )
            self.assertNotIn(
                "<!-- legacy-shared-body",
                body,
                f"Role {role!r} definition must not retain legacy shared body marker",
            )
            for forbidden_marker in ("TODO", "FIXME", "STUB"):
                self.assertNotIn(
                    forbidden_marker,
                    body,
                    f"Role {role!r} contains unresolved marker {forbidden_marker!r}",
                )

            # Native Antigravity agents must not retain legacy template macros
            self.assertNotIn(
                "{{",
                body,
                f"Role {role!r} retains unrendered template variable '{{'",
            )
            self.assertNotIn(
                "<!-- only:",
                body,
                f"Role {role!r} retains legacy conditional comment '<!-- only:'",
            )

            # Native agent body must cite the Gemini 3.7 Flash model prompting guide
            has_gemini_guide = bool(
                re.search(
                    r"docs/models/gemini-3\.7-flash/prompting\.md|gemini-3\.7-flash/prompting\.md",
                    body,
                )
            )
            self.assertTrue(
                has_gemini_guide,
                f"Role {role!r} is still an uncustomized fallback; native agent must cite Gemini 3.7 Flash guide",
            )

        # 2. Verify contracts and ordered gates from contracts/harness-contracts.json
        self.assertTrue(
            CONTRACTS_FILE.is_file(),
            f"Missing contracts registry {CONTRACTS_FILE}",
        )
        registry = json.loads(CONTRACTS_FILE.read_text(encoding="utf-8"))
        agent_contracts = {entry["name"]: entry for entry in registry.get("agents", [])}

        for role in EXPECTED_ROLES:
            contract = agent_contracts.get(role)
            self.assertIsNotNone(
                contract,
                f"Role {role!r} missing from contracts registry {CONTRACTS_FILE}",
            )
            agent_file = AGY_AGENTS_DIR / role / "agent.md"
            raw = agent_file.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(raw)

            # Required values for agy harness: ["body", "model"]
            for req in contract.get("requiredValues", {}).get("agy", []):
                if req == "body":
                    self.assertTrue(
                        bool(body.strip()),
                        f"Role {role!r} must have a non-empty body",
                    )
                else:
                    self.assertTrue(
                        bool(meta.get(req)),
                        f"Role {role!r} must define required frontmatter key {req!r}",
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
            ordered_gates = contract.get("orderedGates", [])
            for gate in ordered_gates:
                self.assertTrue(
                    _gate_is_represented(gate, body),
                    f"Role {role!r} instructions must represent ordered gate {gate!r}",
                )

        # 3. Agent sync exits 0
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

        # 4. Contract parity exits 0
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

        # 5. Evals contract parity exits 0
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

        # 6. Agy agent evals exit 0
        with tempfile.TemporaryDirectory(prefix="workcell-agy-eval-") as temp_dir:
            temp_root = Path(temp_dir)
            for top in ("contracts", "agents", "evals", "scripts"):
                (temp_root / top).symlink_to(ROOT / top)
            (temp_root / "harnesses" / "agy").mkdir(parents=True)
            (temp_root / "harnesses" / "agy" / "skills").symlink_to(
                ROOT / "harnesses" / "agy" / "skills"
            )
            (temp_root / "harnesses" / "agy" / "runtime").symlink_to(
                ROOT / "harnesses" / "agy" / "runtime"
            )
            (temp_root / "harnesses" / "agy" / "agents").mkdir(parents=True)
            for agent_dir in AGY_AGENTS_DIR.iterdir():
                if agent_dir.is_dir() and agent_dir.name != "tests":
                    (
                        temp_root / "harnesses" / "agy" / "agents" / agent_dir.name
                    ).symlink_to(agent_dir)

            evals_agy_result = subprocess.run(
                [
                    "python3",
                    "evals/run_evals.py",
                    "--harness",
                    "agy",
                    "--root",
                    str(temp_root),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                evals_agy_result.returncode,
                0,
                f"evals/run_evals.py --harness agy failed:\n{evals_agy_result.stdout}\n{evals_agy_result.stderr}",
            )

        # 7. Antigravity plugin builds and stages all 10 agents
        plugin_build_result = subprocess.run(
            ["python3", "scripts/build-agy-plugin.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            plugin_build_result.returncode,
            0,
            f"scripts/build-agy-plugin.py failed:\n{plugin_build_result.stdout}\n{plugin_build_result.stderr}",
        )
        staged_agents_dir = ROOT / "dist" / "agy" / "workcell" / "agents"
        self.assertTrue(
            staged_agents_dir.is_dir(),
            f"Expected staged agents directory at {staged_agents_dir}",
        )
        for role in EXPECTED_ROLES:
            staged_agent_file = staged_agents_dir / role / "agent.md"
            self.assertTrue(
                staged_agent_file.is_file(),
                f"Role {role!r} missing from staged plugin at {staged_agent_file}",
            )


if __name__ == "__main__":
    unittest.main()
