"""Acceptance tests for Claude agent definitions (issue #155).

Verifies that:
1. Exactly ten definitions resolve ClaudeRoster model/effort, cite that guide,
   and contain no fallback.
2. Roster-selected Fable roles use goals/constraints/boundaries without forced
   step scaffolding; selected Opus/Sonnet roles retain only guide-supported
   structure.
3. Contracts match; read-only roles deny writes, writers retain tools,
   handoffs remain v1, and fresh verifier delegation exists without redundant
   self-critique.
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

# Suppress bytecode generation
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.roster import (
    CLAUDE_ROLES,
    VALID_CLAUDE_GUIDES,
    resolve_claude_role,
    resolve_role_guide,
)

AGENTS_DIR = ROOT / "harnesses" / "claude" / "agents"
CONTRACTS_PATH = ROOT / "contracts" / "harness-contracts.json"


def _cleanup_pycache() -> None:
    for cache_dir in (
        Path(__file__).parent / "__pycache__",
        ROOT / "agents" / "__pycache__",
        ROOT / "scripts" / "__pycache__",
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
    # Fallback to token search
    tokens = [w for w in re.findall(r"[a-zA-Z0-9]+", g) if len(w) >= 3]
    return any(tok in t for tok in tokens)


class ClaudeAgentsAcceptanceTests(unittest.TestCase):
    """Acceptance tests for Claude agent definitions."""

    def tearDown(self) -> None:
        _cleanup_pycache()

    @classmethod
    def tearDownClass(cls) -> None:
        _cleanup_pycache()

    def test_ten_claude_agents_are_owned_and_routed(self) -> None:
        """ten-claude-agents-are-owned-and-routed (unit):
        Exactly ten definitions resolve ClaudeRoster model/effort, cite that guide,
        and contain no fallback.
        """
        # 1. Exactly ten definitions exist directly under harnesses/claude/agents/
        definition_paths = sorted(
            p for p in AGENTS_DIR.glob("*.md") if p.is_file()
        )
        agent_names = {p.stem for p in definition_paths}
        self.assertEqual(
            len(definition_paths),
            10,
            f"Expected exactly 10 agent definitions under {AGENTS_DIR}, found {len(definition_paths)}: {agent_names}",
        )
        self.assertEqual(
            agent_names,
            set(CLAUDE_ROLES),
            f"Agent definitions must match the ten Claude roles {set(CLAUDE_ROLES)}",
        )

        # 2. Each definition resolves ClaudeRoster model, effort, and mode
        for role in CLAUDE_ROLES:
            agent_file = AGENTS_DIR / f"{role}.md"
            self.assertTrue(
                agent_file.is_file(),
                f"Missing definition file for Claude role {role!r}: {agent_file}",
            )
            meta, body = parse_frontmatter(agent_file)
            roster_info = resolve_claude_role(role)

            self.assertEqual(
                meta.get("model"),
                roster_info.get("model"),
                f"Role {role!r} frontmatter model {meta.get('model')!r} must match roster {roster_info.get('model')!r}",
            )
            self.assertEqual(
                meta.get("effort"),
                roster_info.get("effort"),
                f"Role {role!r} frontmatter effort {meta.get('effort')!r} must match roster {roster_info.get('effort')!r}",
            )
            if "mode" in roster_info:
                self.assertEqual(
                    meta.get("mode"),
                    roster_info.get("mode"),
                    f"Role {role!r} frontmatter mode {meta.get('mode')!r} must match roster {roster_info.get('mode')!r}",
                )

            # 3. Cite that guide
            guide_path = resolve_role_guide(role)
            self.assertIsNotNone(
                guide_path,
                f"Role {role!r} must resolve to a valid guide",
            )
            guide_model = guide_path.parent.name
            full_guide_ref = f"docs/models/{guide_model}/prompting.md"
            short_guide_ref = f"{guide_model}/prompting.md"

            has_guide_citation = (
                full_guide_ref in body
                or short_guide_ref in body
                or f"models/{guide_model}" in body
            )
            self.assertTrue(
                has_guide_citation,
                f"Role {role!r} definition must cite its model guide ({full_guide_ref})",
            )

            # Must not cite other model guides
            for other_guide in VALID_CLAUDE_GUIDES - {guide_model}:
                self.assertNotIn(
                    f"{other_guide}/prompting.md",
                    body,
                    f"Role {role!r} must not cite inapplicable guide {other_guide!r}",
                )

            # 4. Contain no fallback
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
                    f"Role {role!r} definition contains unfinished marker {forbidden_marker!r}",
                )

    def test_fable_prose_is_deprescribed(self) -> None:
        """fable-prose-is-deprescribed (unit):
        Roster-selected Fable roles use goals/constraints/boundaries without forced
        step scaffolding; selected Opus/Sonnet roles retain only guide-supported structure.
        """
        fable_roles = [
            r for r in CLAUDE_ROLES
            if "fable" in resolve_claude_role(r).get("model", "").lower()
        ]
        non_fable_roles = [r for r in CLAUDE_ROLES if r not in fable_roles]
        self.assertEqual(
            set(fable_roles),
            {"builder", "debugger"},
            "Fable roles must be exactly builder and debugger",
        )

        # 1. Fable roles use goals/constraints/boundaries without forced step scaffolding
        for role in fable_roles:
            agent_file = AGENTS_DIR / f"{role}.md"
            meta, body = parse_frontmatter(agent_file)

            # Frontmatter declares de-prescribed mode
            self.assertEqual(
                meta.get("mode"),
                "de-prescribed",
                f"Fable role {role!r} must declare mode: de-prescribed",
            )

            # Section presence: Goals, Constraints, Boundaries
            has_goals = bool(
                re.search(r"^#+\s+(?:Goals?|Goal\b|Objective)", body, re.IGNORECASE | re.MULTILINE)
            )
            has_constraints = bool(
                re.search(r"^#+\s+(?:Constraints?|Constraint\b)", body, re.IGNORECASE | re.MULTILINE)
            )
            has_boundaries = bool(
                re.search(r"^#+\s+(?:Boundaries?|Boundary\b)", body, re.IGNORECASE | re.MULTILINE)
            )

            self.assertTrue(
                has_goals,
                f"Fable role {role!r} must structure instructions with a Goals section",
            )
            self.assertTrue(
                has_constraints,
                f"Fable role {role!r} must structure instructions with a Constraints section",
            )
            self.assertTrue(
                has_boundaries,
                f"Fable role {role!r} must structure instructions with a Boundaries section",
            )

            # Absence of forced step scaffolding: no Procedure header
            has_procedure = bool(
                re.search(r"^#+\s+Procedure\b", body, re.IGNORECASE | re.MULTILINE)
            )
            self.assertFalse(
                has_procedure,
                f"Fable role {role!r} must not use 'Procedure' heading (scaffolding must be de-prescribed)",
            )

            # Absence of sequential numbered steps scaffolding (e.g., 1. ... 2. ... 3. ...)
            has_sequential_steps = bool(
                re.search(r"^\s*1\.\s+.*?\n\s*2\.\s+.*?\n\s*3\.\s+", body, re.DOTALL | re.MULTILINE)
            )
            self.assertFalse(
                has_sequential_steps,
                f"Fable role {role!r} must not use forced sequential step scaffolding (1. ... 2. ... 3. ...)",
            )

        # 2. Selected Opus/Sonnet roles retain only guide-supported structure
        opus_roles = [
            r for r in non_fable_roles
            if "opus" in resolve_claude_role(r).get("model", "").lower()
        ]
        sonnet_roles = [
            r for r in non_fable_roles
            if "sonnet" in resolve_claude_role(r).get("model", "").lower()
        ]

        # Non-Fable roles must not declare de-prescribed mode
        for role in non_fable_roles:
            agent_file = AGENTS_DIR / f"{role}.md"
            meta, _ = parse_frontmatter(agent_file)
            self.assertNotEqual(
                meta.get("mode"),
                "de-prescribed",
                f"Non-Fable role {role!r} must not declare mode: de-prescribed",
            )

        # Opus roles: no redundant verifier subagents (native self-correction per Opus guide)
        for role in opus_roles:
            agent_file = AGENTS_DIR / f"{role}.md"
            _, body = parse_frontmatter(agent_file)
            self.assertNotIn(
                "verifier subagent",
                body.lower(),
                f"Opus role {role!r} must not demand a redundant verifier subagent",
            )
            self.assertNotIn(
                "double-check subagent",
                body.lower(),
                f"Opus role {role!r} must not demand a redundant double-check subagent",
            )

        # Sonnet roles: no fixed-cadence scaffolding (e.g. status after every few calls per Sonnet guide)
        for role in sonnet_roles:
            agent_file = AGENTS_DIR / f"{role}.md"
            _, body = parse_frontmatter(agent_file)
            self.assertIsNone(
                re.search(r"after every \d+ (?:tool )?calls?", body, re.IGNORECASE),
                f"Sonnet role {role!r} must not contain fixed-cadence update scaffolding",
            )

    def test_claude_agent_contracts_and_capabilities_hold(self) -> None:
        """claude-agent-contracts-and-capabilities-hold (integration):
        Contracts match; read-only roles deny writes, writers retain tools,
        handoffs remain v1, and fresh verifier delegation exists without
        redundant self-critique.
        """
        # 1. Contracts match harness-contracts.json
        contracts_data = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))
        agent_contracts = {
            entry["name"]: entry for entry in contracts_data.get("agents", [])
        }

        read_only_roles = {"reviewer", "researcher"}
        writer_roles = {"builder", "specifier", "documenter", "debugger"}

        for role in CLAUDE_ROLES:
            contract = agent_contracts.get(role)
            self.assertIsNotNone(
                contract,
                f"Missing contract for role {role!r} in {CONTRACTS_PATH}",
            )
            agent_file = AGENTS_DIR / f"{role}.md"
            meta, body = parse_frontmatter(agent_file)

            # Required values for claude harness: ["body", "model", "effort"]
            for req in contract.get("requiredValues", {}).get("claude", []):
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

            # Handoff schema is anvil.agent-handoff/v1
            self.assertEqual(
                contract.get("handoffSchema"),
                "anvil.agent-handoff/v1",
                f"Role {role!r} contract handoff schema must be anvil.agent-handoff/v1",
            )
            self.assertIn(
                "anvil.agent-handoff/v1",
                body,
                f"Role {role!r} body must reference handoff contract anvil.agent-handoff/v1",
            )

            # Ordered gates must be represented in instructions
            for gate in contract.get("orderedGates", []):
                self.assertTrue(
                    _gate_is_represented(gate, body),
                    f"Role {role!r} instructions must represent contract gate {gate!r}",
                )

        # 2. Read-only roles deny writes
        for role in read_only_roles:
            agent_file = AGENTS_DIR / f"{role}.md"
            meta, body = parse_frontmatter(agent_file)
            disallowed = {
                t.strip() for t in meta.get("disallowedTools", "").split(",") if t.strip()
            }
            required_disallowed = {"Edit", "Write", "NotebookEdit", "Task"}
            self.assertTrue(
                required_disallowed <= disallowed,
                f"Read-only role {role!r} must disallow {required_disallowed}; got {disallowed}",
            )
            max_turns = int(meta.get("maxTurns", 0))
            self.assertGreater(
                max_turns,
                0,
                f"Read-only role {role!r} must declare positive maxTurns",
            )
            self.assertTrue(
                bool(re.search(r"read-only|no edits|never mutate", body, re.IGNORECASE)),
                f"Read-only role {role!r} must state read-only boundary in body",
            )

        # 3. Writers retain tools
        for role in writer_roles:
            agent_file = AGENTS_DIR / f"{role}.md"
            meta, _ = parse_frontmatter(agent_file)
            tools = {
                t.strip() for t in meta.get("tools", "").split(",") if t.strip()
            }
            self.assertIn(
                "Edit",
                tools,
                f"Writer role {role!r} must retain Edit tool in tools frontmatter",
            )
            self.assertIn(
                "Write",
                tools,
                f"Writer role {role!r} must retain Write tool in tools frontmatter",
            )
            disallowed = {
                t.strip() for t in meta.get("disallowedTools", "").split(",") if t.strip()
            }
            self.assertNotIn(
                "Edit",
                disallowed,
                f"Writer role {role!r} must not disallow Edit tool",
            )
            self.assertNotIn(
                "Write",
                disallowed,
                f"Writer role {role!r} must not disallow Write tool",
            )

        # 4. Fresh verifier delegation exists without redundant self-critique
        builder_file = AGENTS_DIR / "builder.md"
        _, builder_body = parse_frontmatter(builder_file)
        self.assertIn(
            "reviewer",
            builder_body.lower(),
            "Builder must delegate review to reviewer agent (fresh verifier)",
        )
        self.assertTrue(
            bool(re.search(r"fresh|independent|read-only reviewer", builder_body, re.IGNORECASE)),
            "Builder must specify fresh/independent reviewer delegation",
        )
        self.assertNotIn(
            "self-critique",
            builder_body.lower(),
            "Builder must not rely on redundant self-critique loops",
        )

        # 5. Staging integration: build-claude-plugin packages all 10 agents
        staged_build = subprocess.run(
            ["python3", str(ROOT / "scripts" / "build-claude-plugin.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            staged_build.returncode,
            0,
            f"build-claude-plugin.py failed:\n{staged_build.stderr}",
        )
        staged_agents_dir = ROOT / "dist" / "claude" / "workcell" / "agents"
        self.assertTrue(
            staged_agents_dir.is_dir(),
            f"Missing staged agents directory {staged_agents_dir}",
        )
        staged_files = {p.stem for p in staged_agents_dir.glob("*.md") if p.is_file()}
        self.assertEqual(
            staged_files,
            set(CLAUDE_ROLES),
            f"Staged agents must match all ten Claude roles; got {staged_files}",
        )


if __name__ == "__main__":
    unittest.main()
