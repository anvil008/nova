"""Acceptance tests for Claude Fable 5.1 roster decision (#153)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from agents.roster import (
    CLAUDE_ROLES,
    ROOT,
    VALID_CLAUDE_GUIDES,
    get_model_guide_mappings,
    load_decision_record,
    resolve_claude_role,
    resolve_role_guide,
)

REQUIRED_DECISION_ROLES = {"planner", "debugger", "builder"}
COST_KEYS = {
    "cost",
    "cost_evidence",
    "cost_usd",
    "spend",
    "tokens",
    "token_usage",
    "total_tokens",
    "input_tokens",
    "output_tokens",
    "latency",
    "latency_seconds",
    "duration",
    "duration_seconds",
}
RESULT_KEYS = {
    "result",
    "results",
    "outcome",
    "grade",
    "status",
    "pass",
    "quality",
    "refusal",
}


def _is_fable(info: dict[str, Any]) -> bool:
    model = str(info.get("model", "")).lower()
    guide = str(info.get("guide", "")).lower()
    return "fable" in model or "fable" in guide


def _extract_variant(
    role_data: dict[str, Any], variant_type: str
) -> dict[str, Any] | None:
    """Extract current or candidate variant data from a role comparison dict."""
    if variant_type == "current":
        keys = (
            "current",
            "baseline",
            "opus",
            "claude-opus-5",
            "sonnet",
            "claude-sonnet-5",
        )
    else:
        keys = ("candidate", "fable", "claude-fable-5-1")

    for key in keys:
        if key in role_data and isinstance(role_data[key], dict):
            return role_data[key]
    return None


def _extract_expectations(variant_data: dict[str, Any]) -> list[str]:
    """Extract named expectations from a variant dict."""
    raw = variant_data.get("expectations")
    if isinstance(raw, list):
        names: list[str] = []
        for item in raw:
            if isinstance(item, str):
                names.append(item.strip())
            elif isinstance(item, dict):
                name = (
                    item.get("name")
                    or item.get("text")
                    or item.get("id")
                    or item.get("expectation")
                )
                if name:
                    names.append(str(name).strip())
        return names
    if isinstance(raw, dict):
        return [str(k).strip() for k in raw.keys()]

    results = variant_data.get("results")
    if isinstance(results, dict):
        return [str(k).strip() for k in results.keys()]

    return []


def _has_result(variant_data: dict[str, Any]) -> bool:
    for key in RESULT_KEYS:
        if key in variant_data:
            return True
    raw_exp = variant_data.get("expectations")
    if isinstance(raw_exp, list):
        for item in raw_exp:
            if isinstance(item, dict) and any(k in item for k in RESULT_KEYS):
                return True
    return False


def _has_cost_evidence(variant_data: dict[str, Any]) -> bool:
    for key in COST_KEYS:
        if key in variant_data:
            return True
    evidence = variant_data.get("evidence")
    if isinstance(evidence, dict) and any(k in evidence for k in COST_KEYS):
        return True
    cost_evidence = variant_data.get("cost_evidence")
    if isinstance(cost_evidence, dict) and any(k in cost_evidence for k in COST_KEYS):
        return True
    return False


def _normalize_decision_record(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize various decision record formats into {role: {current: ..., candidate: ...}}."""
    roles_data: dict[str, dict[str, Any]] = {}

    if "roles" in record and isinstance(record["roles"], dict):
        for role, role_dict in record["roles"].items():
            if isinstance(role_dict, dict):
                roles_data[role] = role_dict

    if "comparisons" in record and isinstance(record["comparisons"], list):
        for entry in record["comparisons"]:
            if isinstance(entry, dict) and "role" in entry:
                role = entry["role"]
                roles_data.setdefault(role, {})
                route = entry.get("route", entry.get("variant", ""))
                if route in ("current", "baseline", "opus", "claude-opus-5"):
                    roles_data[role]["current"] = entry
                elif route in ("candidate", "fable", "claude-fable-5-1"):
                    roles_data[role]["candidate"] = entry

    for role in REQUIRED_DECISION_ROLES:
        if role not in roles_data and role in record and isinstance(record[role], dict):
            roles_data[role] = record[role]

    return roles_data


class ClaudeRosterAcceptanceTests(unittest.TestCase):
    """Acceptance tests for issue #153: Claude Fable 5.1 roster decision."""

    def test_roster_compares_controlled_variants(self) -> None:
        """roster-compares-controlled-variants (integration):

        A checked-in decision record runs the same named expectations for current
        and Fable candidate planner/debugger/builder routes and records result
        plus available cost evidence.
        """
        record = load_decision_record()
        self.assertIsNotNone(
            record,
            "Checked-in decision record for Claude roster comparison not found "
            "(expected checked-in record under agents/ or docs/adr/)",
        )

        normalized = _normalize_decision_record(record)
        missing_roles = REQUIRED_DECISION_ROLES - set(normalized.keys())
        self.assertFalse(
            missing_roles,
            f"Decision record is missing comparisons for required roles: {sorted(missing_roles)}",
        )

        for role in sorted(REQUIRED_DECISION_ROLES):
            with self.subTest(role=role):
                role_data = normalized[role]
                current_variant = _extract_variant(role_data, "current")
                candidate_variant = _extract_variant(role_data, "candidate")

                self.assertIsNotNone(
                    current_variant,
                    f"Decision record for {role!r} missing current route comparison",
                )
                self.assertIsNotNone(
                    candidate_variant,
                    f"Decision record for {role!r} missing Fable candidate route comparison",
                )

                current_exp = _extract_expectations(current_variant)
                candidate_exp = _extract_expectations(candidate_variant)

                self.assertGreater(
                    len(current_exp),
                    0,
                    f"Current route for {role!r} does not record any named expectations",
                )
                self.assertGreater(
                    len(candidate_exp),
                    0,
                    f"Fable candidate route for {role!r} does not record any named expectations",
                )
                self.assertEqual(
                    set(current_exp),
                    set(candidate_exp),
                    f"Current and candidate routes for {role!r} must run the same named expectations; "
                    f"difference: {set(current_exp) ^ set(candidate_exp)}",
                )

                self.assertTrue(
                    _has_result(current_variant),
                    f"Current route for {role!r} must record result evidence (e.g. pass, grade, quality)",
                )
                self.assertTrue(
                    _has_result(candidate_variant),
                    f"Candidate route for {role!r} must record result evidence (e.g. pass, grade, quality)",
                )

                self.assertTrue(
                    _has_cost_evidence(current_variant),
                    f"Current route for {role!r} must record cost evidence (e.g. tokens, cost, latency)",
                )
                self.assertTrue(
                    _has_cost_evidence(candidate_variant),
                    f"Candidate route for {role!r} must record cost evidence (e.g. tokens, cost, latency)",
                )

    def test_selected_routes_obey_fable_constraints(self) -> None:
        """selected-routes-obey-fable-constraints (unit):

        Fable-selected roles use effort high and de-prescribed mode; no security
        reviewer uses Fable; retained roles have explicit Opus 5 or Sonnet 5 mappings.
        """
        # Constraint 1: no security reviewer uses Fable
        reviewer_info = resolve_claude_role("reviewer")
        self.assertNotIn(
            "fable",
            str(reviewer_info.get("model", "")).lower(),
            "Reviewer / security reviewer must not use Fable",
        )
        self.assertNotIn(
            "fable",
            str(reviewer_info.get("guide", "")).lower(),
            "Reviewer / security reviewer must not map to Fable guide",
        )

        mappings = get_model_guide_mappings()
        fable_roles: list[str] = []
        retained_roles: list[str] = []

        for role in CLAUDE_ROLES:
            info = resolve_claude_role(role)
            if _is_fable(info):
                fable_roles.append(role)
            else:
                retained_roles.append(role)

        # Constraint 2: Fable-selected roles use effort high and de-prescribed mode
        for role in fable_roles:
            with self.subTest(fable_role=role):
                info = resolve_claude_role(role)
                self.assertEqual(
                    info.get("effort"),
                    "high",
                    f"Fable-selected role {role!r} must use effort high (got {info.get('effort')!r})",
                )
                self.assertNotEqual(
                    info.get("effort"),
                    "xhigh",
                    f"Fable-selected role {role!r} must not use effort xhigh",
                )
                self.assertEqual(
                    info.get("mode"),
                    "de-prescribed",
                    f"Fable-selected role {role!r} must use de-prescribed mode (got {info.get('mode')!r})",
                )

        # Constraint 3: retained roles have explicit Opus 5 or Sonnet 5 mappings
        for role in retained_roles:
            with self.subTest(retained_role=role):
                info = resolve_claude_role(role)
                raw_model = info.get("model", "")
                mapped_guide = (
                    info.get("guide")
                    or mappings.get(raw_model)
                    or mappings.get(role)
                    or (raw_model if raw_model in VALID_CLAUDE_GUIDES else None)
                )
                self.assertIn(
                    mapped_guide,
                    {"claude-opus-5", "claude-sonnet-5"},
                    f"Retained role {role!r} does not have an explicit Opus 5 or Sonnet 5 mapping "
                    f"(raw model: {raw_model!r}, mapped guide: {mapped_guide!r})",
                )

    def test_each_claude_role_resolves_one_guide(self) -> None:
        """each-claude-role-resolves-one-guide (unit):

        All ten resolved Claude roles map to exactly one existing
        docs/models/<model>/prompting.md with no unmapped alias or implicit fallback.
        """
        mappings = get_model_guide_mappings()

        for role in CLAUDE_ROLES:
            with self.subTest(role=role):
                info = resolve_claude_role(role)
                raw_model = info.get("model", "")

                # Must not have an unmapped alias or implicit fallback
                is_explicit = (
                    raw_model in VALID_CLAUDE_GUIDES
                    or raw_model in mappings
                    or role in mappings
                    or info.get("guide") in VALID_CLAUDE_GUIDES
                )
                self.assertTrue(
                    is_explicit,
                    f"Role {role!r} uses alias or unmapped model {raw_model!r} with no explicit "
                    f"mapping in authoritative model-to-guide mappings; implicit fallbacks are forbidden",
                )

                guide_path = resolve_role_guide(role)
                self.assertIsNotNone(
                    guide_path,
                    f"Role {role!r} must resolve to exactly one guide path",
                )
                self.assertTrue(
                    guide_path.is_file(),
                    f"Resolved guide {guide_path} for role {role!r} does not exist",
                )
                self.assertEqual(
                    guide_path.name,
                    "prompting.md",
                    f"Resolved guide {guide_path} for role {role!r} must be named prompting.md",
                )
                self.assertIn(
                    guide_path.parent.name,
                    VALID_CLAUDE_GUIDES,
                    f"Resolved guide model directory {guide_path.parent.name} must be in {VALID_CLAUDE_GUIDES}",
                )


if __name__ == "__main__":
    unittest.main()
