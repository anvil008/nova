"""Authoritative Claude model and role-to-guide mappings and decision records."""

from __future__ import annotations

import atexit
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

# Prevent bytecode generation in agents/ directory during imports
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / "agents"
MODELS_FILE = AGENTS_DIR / "models.json"
MODELS_DOCS_DIR = ROOT / "docs" / "models"


def _cleanup_pycache() -> None:
    """Ensure no __pycache__ directory or bytecode remains in agents/."""
    pycache = AGENTS_DIR / "__pycache__"
    if pycache.is_dir():
        shutil.rmtree(pycache, ignore_errors=True)


_cleanup_pycache()
atexit.register(_cleanup_pycache)

CLAUDE_ROLES = (
    "planner",
    "specifier",
    "builder",
    "reviewer",
    "integrator",
    "researcher",
    "documenter",
    "deployer",
    "debugger",
    "profiler",
)

VALID_CLAUDE_GUIDES = {
    "claude-fable-5-1",
    "claude-opus-5",
    "claude-sonnet-5",
}


def get_model_guide_mappings() -> dict[str, str]:
    """Return explicit mappings from model names or aliases to guide names.

    Reads agents/models.json ('model_guides') as the sole authoritative source of truth.
    """
    mappings: dict[str, str] = {}
    if MODELS_FILE.is_file():
        try:
            data = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
            for key in (
                "model_guides",
                "guides",
                "mappings",
                "role_to_guide",
                "claude_guides",
            ):
                section = data.get(key)
                if isinstance(section, dict):
                    if "claude" in section and isinstance(section["claude"], dict):
                        mappings.update(section["claude"])
                    else:
                        mappings.update(section)
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    return mappings


def resolve_claude_role(role: str) -> dict[str, Any]:
    """Resolve authoritative model, effort, mode, and guide for a Claude role.

    Reads agents/models.json and incorporates defaults and explicit mappings.
    """
    if not MODELS_FILE.is_file():
        return {}

    try:
        data = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}

    defaults = data.get("defaults", {}).get("claude", {})
    agent_spec = data.get("agents", {}).get(role, {})
    claude_spec = agent_spec.get("claude", {})

    merged: dict[str, Any] = {
        "role": role,
        "model": claude_spec.get("model", defaults.get("model", "")),
        "effort": claude_spec.get("effort", defaults.get("effort", "")),
    }

    if "mode" in claude_spec:
        merged["mode"] = claude_spec["mode"]
    elif "mode" in defaults:
        merged["mode"] = defaults["mode"]

    if "guide" in claude_spec:
        merged["guide"] = claude_spec["guide"]
    elif "guide" in defaults:
        merged["guide"] = defaults["guide"]
    else:
        mappings = get_model_guide_mappings()
        if merged["model"] in mappings:
            merged["guide"] = mappings[merged["model"]]
        elif role in mappings:
            merged["guide"] = mappings[role]

    return merged


def resolve_role_guide(role: str) -> Path | None:
    """Resolve a Claude role to its exact docs/models/<model>/prompting.md path.

    Returns the Path to the guide file if it exists and is explicitly mapped.
    Returns None if unmapped, using implicit fallback, or missing.
    """
    if role not in CLAUDE_ROLES:
        return None

    info = resolve_claude_role(role)
    raw_model = info.get("model", "")
    explicit_guide = info.get("guide")
    mappings = get_model_guide_mappings()

    target_guide: str | None = None
    if explicit_guide and explicit_guide in VALID_CLAUDE_GUIDES:
        target_guide = explicit_guide
    elif raw_model in VALID_CLAUDE_GUIDES:
        target_guide = raw_model
    elif raw_model in mappings and mappings[raw_model] in VALID_CLAUDE_GUIDES:
        target_guide = mappings[raw_model]
    elif role in mappings and mappings[role] in VALID_CLAUDE_GUIDES:
        target_guide = mappings[role]
    else:
        # No unmapped alias or implicit fallback allowed
        return None

    candidate = MODELS_DOCS_DIR / target_guide / "prompting.md"
    if candidate.is_file():
        return candidate
    return None


def _extract_json_block(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from a markdown text or code block."""
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass

    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def load_decision_record() -> dict[str, Any] | None:
    """Load the checked-in Claude roster decision record.

    Searches standard checked-in locations under agents/, docs/adr/, evals/results/.
    Returns parsed dictionary if a valid decision record is found, None otherwise.
    """
    candidate_paths: list[Path] = [
        AGENTS_DIR / "claude-roster-decision.json",
        AGENTS_DIR / "claude_roster_decision.json",
        AGENTS_DIR / "roster-decision.json",
        AGENTS_DIR / "decision-record.json",
        AGENTS_DIR / "claude-roster-decision.md",
        AGENTS_DIR / "claude_roster_decision.md",
    ]

    adr_dir = ROOT / "docs" / "adr"
    if adr_dir.is_dir():
        for path in sorted(adr_dir.glob("*.md")):
            name = path.name.lower()
            if any(
                term in name for term in ("fable", "roster", "claude")
            ) or path.name.startswith("0024"):
                candidate_paths.append(path)

    results_dir = ROOT / "evals" / "results"
    if results_dir.is_dir():
        for path in sorted(results_dir.glob("*.json")):
            name = path.name.lower()
            if any(term in name for term in ("roster", "fable", "decision")):
                candidate_paths.append(path)

    for path in candidate_paths:
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
            if path.suffix == ".json":
                parsed = json.loads(content)
                if isinstance(parsed, dict) and (
                    "roles" in parsed or "comparisons" in parsed or "planner" in parsed
                ):
                    return parsed
            elif path.suffix == ".md":
                extracted = _extract_json_block(content)
                if extracted and (
                    "roles" in extracted
                    or "comparisons" in extracted
                    or "planner" in extracted
                ):
                    return extracted
        except (OSError, json.JSONDecodeError, TypeError):
            continue

    return None


_cleanup_pycache()
