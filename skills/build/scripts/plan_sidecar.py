"""Strict validation of a planner sidecar, as waves.py consumes it.

Mirrors validate_plan() and the closure it needs — PlanError, require_exact_fields(),
nonempty_string(), canonical_write_target(), validate_risks() and the field/pattern constants they read — from
the sibling skills/plan/scripts/render_plan.py, duplicated because build ships
self-contained. The bodies are copied verbatim so the two can be diffed line for
line; render_plan's HTML rendering is deliberately left behind. Keep the accepts,
the rejects and the error strings in step: waves.py is a dry run of what the
planner already accepted, so a divergence here is a false verdict.
"""

from __future__ import annotations

import re
from datetime import datetime

TOP_FIELDS = {
    "planId", "planName", "repo", "generatedAt", "summary",
    "architecture", "issues", "risks",
}
RISK_FIELDS = {"id", "title", "likelihood", "impact", "owner", "mitigation"}
ARCH_FIELDS = {"components", "changeSummary", "diagramsMermaid"}
ISSUE_FIELDS = {"key", "title", "body", "labels", "dependsOn", "ownershipHint", "wave", "acceptanceTests"}
ACC_REQUIRED = {"name", "kind", "oracle"}
ACC_ALLOWED = {"name", "kind", "oracle", "testPath", "stub"}
ACC_KINDS = {"unit", "integration", "e2e"}
PLAN_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ISSUE_KEY = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class PlanError(ValueError):
    pass


def require_exact_fields(value: dict, expected: set[str], where: str) -> None:
    missing = expected - value.keys()
    unknown = value.keys() - expected
    if missing:
        raise PlanError(f"{where}: missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise PlanError(f"{where}: unknown field(s): {', '.join(sorted(unknown))}")


def nonempty_string(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanError(f"{where} must be a non-empty string")
    return value.strip()


def canonical_write_target(value: object, where: str) -> str:
    """Keep ownership and test writes in one lexical, repository-relative namespace."""
    target = nonempty_string(value, where)
    if "," in target or target.split() != [target]:
        raise PlanError(f"{where} takes one path or glob, not {value!r}")
    # PurePath collapses dot/empty components but preserves '..'; neither behavior
    # is suitable before the scheduler compares ownership strings. Reject aliases
    # instead of silently changing a write target the user reviewed.
    if (
        target != value
        or "\\" in target
        or re.match(r"^[A-Za-z]:", target)
        or any(ord(character) < 32 or ord(character) == 127 for character in target)
        or any(part in {"", ".", ".."} for part in target.split("/"))
    ):
        raise PlanError(
            f"{where} must be a canonical relative POSIX path or glob, not {value!r}"
        )
    return target


def validate_plan(plan: object) -> dict:
    if not isinstance(plan, dict):
        raise PlanError("sidecar must be a JSON object")
    require_exact_fields(plan, TOP_FIELDS, "sidecar")
    plan_id = nonempty_string(plan["planId"], "planId")
    if not PLAN_ID.fullmatch(plan_id):
        raise PlanError("planId must be a stable lowercase slug")
    # Identifiers are stored stripped so markers round-trip byte-for-byte and a
    # re-run of an unchanged plan is a no-op even if the sidecar carries padding.
    plan["planId"] = plan_id
    nonempty_string(plan["planName"], "planName")
    if plan["repo"] is not None:
        repo = nonempty_string(plan["repo"], "repo")
        if not REPOSITORY.fullmatch(repo):
            raise PlanError("repo must be owner/name or null for local-only plans")
        plan["repo"] = repo
    generated_at = nonempty_string(plan["generatedAt"], "generatedAt")
    try:
        datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise PlanError("generatedAt must be ISO8601") from error
    nonempty_string(plan["summary"], "summary")

    architecture = plan["architecture"]
    if not isinstance(architecture, dict):
        raise PlanError("architecture must be an object")
    require_exact_fields(architecture, ARCH_FIELDS, "architecture")
    nonempty_string(architecture["changeSummary"], "architecture.changeSummary")
    if not isinstance(architecture["components"], list) or not architecture["components"]:
        raise PlanError("architecture.components must be a non-empty array")
    for index, component in enumerate(architecture["components"]):
        if isinstance(component, str):
            nonempty_string(component, f"architecture.components[{index}]")
        elif isinstance(component, dict):
            require_exact_fields(component, {"name", "purpose"}, f"architecture.components[{index}]")
            nonempty_string(component["name"], f"architecture.components[{index}].name")
            nonempty_string(component["purpose"], f"architecture.components[{index}].purpose")
        else:
            raise PlanError(f"architecture.components[{index}] must be a string or name/purpose object")
    sources = architecture["diagramsMermaid"]
    if not isinstance(sources, dict) or not sources:
        raise PlanError("architecture.diagramsMermaid must be a non-empty object")
    for key, source in sources.items():
        nonempty_string(key, "architecture.diagramsMermaid key")
        nonempty_string(source, f"architecture.diagramsMermaid.{key}")
    for required_diagram in ("currentArchitecture", "targetArchitecture"):
        if required_diagram not in sources:
            raise PlanError(f"architecture.diagramsMermaid.{required_diagram} is required")

    issues = plan["issues"]
    if not isinstance(issues, list) or not issues:
        raise PlanError("issues must be a non-empty array")
    keys: set[str] = set()
    for index, issue in enumerate(issues):
        if not isinstance(issue, dict):
            raise PlanError(f"issues[{index}] must be an object")
        require_exact_fields(issue, ISSUE_FIELDS, f"issues[{index}]")
        key = nonempty_string(issue["key"], f"issues[{index}].key")
        if not ISSUE_KEY.fullmatch(key):
            raise PlanError(f"issues[{index}].key must be a stable ASCII slug")
        if key in keys:
            raise PlanError(f"duplicate issue key: {key}")
        keys.add(key)
        issue["key"] = key
        nonempty_string(issue["title"], f"issues[{index}].title")
        nonempty_string(issue["body"], f"issues[{index}].body")
        issue["ownershipHint"] = canonical_write_target(
            issue["ownershipHint"], f"issues[{index}].ownershipHint"
        )
        if not isinstance(issue["labels"], list) or any(not isinstance(label, str) or not label for label in issue["labels"]):
            raise PlanError(f"issues[{index}].labels must be an array of non-empty strings")
        if len(set(issue["labels"])) != len(issue["labels"]):
            raise PlanError(f"issues[{index}].labels contains duplicates")
        if not isinstance(issue["dependsOn"], list):
            raise PlanError(f"issues[{index}].dependsOn must be an array of issue keys")
        dependencies = []
        for dependency in issue["dependsOn"]:
            dependency = dependency.strip() if isinstance(dependency, str) else ""
            if not ISSUE_KEY.fullmatch(dependency):
                raise PlanError(
                    f"issues[{index}].dependsOn entries must be stable ASCII slugs"
                )
            dependencies.append(dependency)
        issue["dependsOn"] = dependencies
        if not isinstance(issue["wave"], int) or isinstance(issue["wave"], bool) or issue["wave"] < 0:
            raise PlanError(f"issues[{index}].wave must be a non-negative integer")
        tests = issue["acceptanceTests"]
        if not isinstance(tests, list) or not tests:
            raise PlanError(f"issues[{index}].acceptanceTests must be a non-empty array")
        for tindex, spec in enumerate(tests):
            twhere = f"issues[{index}].acceptanceTests[{tindex}]"
            if not isinstance(spec, dict):
                raise PlanError(f"{twhere} must be an object")
            missing = ACC_REQUIRED - spec.keys()
            unknown = spec.keys() - ACC_ALLOWED
            if missing:
                raise PlanError(f"{twhere}: missing field(s): {', '.join(sorted(missing))}")
            if unknown:
                raise PlanError(f"{twhere}: unknown field(s): {', '.join(sorted(unknown))}")
            nonempty_string(spec["name"], f"{twhere}.name")
            if spec["kind"] not in ACC_KINDS:
                raise PlanError(f"{twhere}.kind must be one of: {', '.join(sorted(ACC_KINDS))}")
            nonempty_string(spec["oracle"], f"{twhere}.oracle")
            if "testPath" in spec:
                spec["testPath"] = canonical_write_target(
                    spec["testPath"], f"{twhere}.testPath"
                )
                if any(character in spec["testPath"] for character in "*?["):
                    raise PlanError(
                        f"{twhere}.testPath must name one concrete test file without glob metacharacters, not {spec['testPath']!r}"
                    )
            if "stub" in spec:
                nonempty_string(spec["stub"], f"{twhere}.stub")

    validate_risks(plan["risks"])
    return plan


def validate_risks(risks: object) -> None:
    """Risks may be empty — an explicit "no risks" is a statement — but never absent."""
    if not isinstance(risks, list):
        raise PlanError("risks must be an array")
    seen: set[str] = set()
    for index, risk in enumerate(risks):
        where = f"risks[{index}]"
        if not isinstance(risk, dict):
            raise PlanError(f"{where} must be an object")
        require_exact_fields(risk, RISK_FIELDS, where)
        identifier = nonempty_string(risk["id"], f"{where}.id")
        if not ISSUE_KEY.fullmatch(identifier):
            raise PlanError(f"{where}.id must be a stable ASCII slug")
        if identifier in seen:
            raise PlanError(f"duplicate risk id: {identifier}")
        seen.add(identifier)
        risk["id"] = identifier
        nonempty_string(risk["title"], f"{where}.title")
        nonempty_string(risk["owner"], f"{where}.owner")
        nonempty_string(risk["mitigation"], f"{where}.mitigation")
        for axis in ("likelihood", "impact"):
            value = risk[axis]
            if not isinstance(value, int) or isinstance(value, bool) or value not in (1, 2, 3):
                raise PlanError(f"{where}.{axis} must be 1, 2, or 3")
