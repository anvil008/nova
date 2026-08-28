#!/usr/bin/env python3
"""Render a strict planner sidecar as a self-contained HTML folio."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOP_FIELDS = {"planId", "planName", "repo", "generatedAt", "summary", "architecture", "issues"}
ARCH_FIELDS = {"components", "diagramsMermaid"}
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


def validate_plan(plan: object) -> dict:
    if not isinstance(plan, dict):
        raise PlanError("sidecar must be a JSON object")
    require_exact_fields(plan, TOP_FIELDS, "sidecar")
    plan_id = nonempty_string(plan["planId"], "planId")
    if not PLAN_ID.fullmatch(plan_id):
        raise PlanError("planId must be a stable lowercase slug")
    nonempty_string(plan["planName"], "planName")
    repo = nonempty_string(plan["repo"], "repo")
    if not REPOSITORY.fullmatch(repo):
        raise PlanError("repo must be owner/name")
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
    diagrams = architecture["diagramsMermaid"]
    if not isinstance(diagrams, dict) or not diagrams:
        raise PlanError("architecture.diagramsMermaid must be a non-empty object")
    for key, source in diagrams.items():
        nonempty_string(key, "architecture.diagramsMermaid key")
        nonempty_string(source, f"architecture.diagramsMermaid.{key}")
    if "targetArchitecture" not in diagrams:
        raise PlanError("architecture.diagramsMermaid.targetArchitecture is required")

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
        nonempty_string(issue["title"], f"issues[{index}].title")
        nonempty_string(issue["body"], f"issues[{index}].body")
        nonempty_string(issue["ownershipHint"], f"issues[{index}].ownershipHint")
        if not isinstance(issue["labels"], list) or any(not isinstance(label, str) or not label for label in issue["labels"]):
            raise PlanError(f"issues[{index}].labels must be an array of non-empty strings")
        if len(set(issue["labels"])) != len(issue["labels"]):
            raise PlanError(f"issues[{index}].labels contains duplicates")
        if not isinstance(issue["dependsOn"], list):
            raise PlanError(f"issues[{index}].dependsOn must be an array of issue keys")
        for dependency in issue["dependsOn"]:
            if not isinstance(dependency, str) or not ISSUE_KEY.fullmatch(dependency):
                raise PlanError(
                    f"issues[{index}].dependsOn entries must be stable ASCII slugs"
                )
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
                nonempty_string(spec["testPath"], f"{twhere}.testPath")
            if "stub" in spec:
                nonempty_string(spec["stub"], f"{twhere}.stub")
    return plan


def escaped(value: object) -> str:
    return html.escape(str(value), quote=True)


def mermaid_label(value: str) -> str:
    return value.replace('"', "'").replace("\n", " ").replace("[", "(").replace("]", ")")


def node_id(key: str) -> str:
    return "issue_" + key.replace("-", "_")


def diagram(source: str, label: str) -> str:
    safe_source = escaped(source)
    return (
        f'<div class="diagram-shell" aria-label="{escaped(label)}">'
        f'<pre class="mermaid">{safe_source}</pre>'
        '<details class="diagram-fallback"><summary>Diagram source</summary>'
        '<p class="diagram-error"></p>'
        f'<pre>{safe_source}</pre></details></div>'
    )


def dependency_source(issues: list[dict]) -> str:
    by_key = {issue["key"]: issue for issue in issues}
    lines = ["flowchart LR"]
    unknown: set[str] = set()
    waves = sorted({issue["wave"] for issue in issues if issue["wave"] > 0})
    palette = ["#dbe7f5", "#e8e1f3", "#dceee5", "#f3e7d7", "#e9e9e7"]
    for wave in waves:
        color = palette[(wave - 1) % len(palette)]
        lines.append(f"  classDef wave{wave} fill:{color},stroke:#2b4c7e,color:#1a1a1a")
    lines.append("  classDef neutral fill:transparent,stroke:#6b6b6b,color:#6b6b6b")
    for issue in issues:
        lines.append(f'  {node_id(issue["key"])}["{mermaid_label(issue["title"])}"]')
    for issue in issues:
        for dependency in issue["dependsOn"]:
            if dependency not in by_key:
                unknown.add(dependency)
                lines.append(f'  {node_id(dependency)}["{mermaid_label(dependency)} (external)"]')
            lines.append(f"  {node_id(dependency)} --> {node_id(issue['key'])}")
    for issue in issues:
        class_name = f"wave{issue['wave']}" if issue["wave"] > 0 else "neutral"
        lines.append(f"  class {node_id(issue['key'])} {class_name}")
    for dependency in sorted(unknown):
        lines.append(f"  class {node_id(dependency)} neutral")
    return "\n".join(lines)


def waves_source(issues: list[dict]) -> str:
    grouped: dict[int, list[dict]] = {}
    for issue in issues:
        grouped.setdefault(issue["wave"], []).append(issue)
    ordered = sorted(wave for wave in grouped if wave > 0)
    lines = ["flowchart TD", "  classDef neutral fill:transparent,stroke:#6b6b6b,color:#6b6b6b"]
    for wave in ordered:
        titles = " · ".join(mermaid_label(issue["key"]) for issue in grouped[wave])
        lines.append(f'  wave_{wave}["Wave {wave}<br/>{titles}"]')
    for left, right in zip(ordered, ordered[1:]):
        lines.append(f"  wave_{left} --> wave_{right}")
    if 0 in grouped:
        titles = " · ".join(mermaid_label(issue["key"]) for issue in grouped[0])
        lines.append(f'  ungrouped["Ungrouped<br/>{titles}"]')
        lines.append("  class ungrouped neutral")
    return "\n".join(lines)


def components_html(components: list[object]) -> str:
    cards = []
    for component in components:
        if isinstance(component, str):
            name, purpose = component, "Target component"
        else:
            name, purpose = component["name"], component["purpose"]
        cards.append(f'<article class="card"><h3>{escaped(name)}</h3><p>{escaped(purpose)}</p></article>')
    return "".join(cards)


def issues_html(issues: list[dict]) -> str:
    cards = []
    for issue in issues:
        labels = "".join(f'<span class="label">{escaped(label)}</span>' for label in issue["labels"])
        depends = ", ".join(issue["dependsOn"]) or "None"
        cards.append(
            '<article class="card">'
            f'<span class="issue-key">{escaped(issue["key"])}</span>'
            f'<h3>{escaped(issue["title"])}</h3>'
            f'<p class="issue-body">{escaped(issue["body"])}</p>'
            f'<p class="issue-meta">Wave {issue["wave"] or "Ungrouped"} · Depends on: {escaped(depends)}<br>'
            f'Ownership: {escaped(issue["ownershipHint"])}</p><div class="labels">{labels}</div></article>'
        )
    return "".join(cards)


def issue_table(issues: list[dict]) -> str:
    rows = []
    for issue in issues:
        depends = ", ".join(issue["dependsOn"]) or "—"
        wave = issue["wave"] or "Ungrouped"
        rows.append(
            f'<tr><td>{escaped(issue["key"])}</td><td>{escaped(issue["title"])}</td>'
            f'<td>{escaped(depends)}</td><td>{escaped(wave)}</td><td>{escaped(issue["ownershipHint"])}</td></tr>'
        )
    return "<table><thead><tr><th>Key</th><th>Issue</th><th>Depends on</th><th>Wave</th><th>Ownership</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def risks_html(issues: list[dict]) -> str:
    known = {issue["key"] for issue in issues}
    unresolved = sorted({dep for issue in issues for dep in issue["dependsOn"] if dep not in known})
    dependency_text = (
        "Resolve external dependencies before execution: " + ", ".join(unresolved)
        if unresolved
        else "Dependency keys are internally resolved; verify integration assumptions during implementation."
    )
    return (
        '<article class="card"><h3>Delivery risk</h3><p>Parallelize only issues whose ownership boundaries are genuinely disjoint; run an integrated verification pass after each wave.</p></article>'
        f'<article class="card"><h3>Open dependency question</h3><p>{escaped(dependency_text)}</p></article>'
        '<article class="card"><h3>Approval boundary</h3><p>Confirm that the HTML and sidecar describe the same approved scope before any GitHub write.</p></article>'
        '<article class="card"><h3>Repository readiness</h3><p>Confirm labels exist and ownership hints still match the target repository at execution time.</p></article>'
    )


def render(plan: dict) -> str:
    template = (ROOT / "templates" / "plan.html.tmpl").read_text(encoding="utf-8")
    css = (ROOT / "templates" / "plan.css").read_text(encoding="utf-8")
    mermaid_js = (ROOT / "assets" / "mermaid.min.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
    generated = datetime.fromisoformat(plan["generatedAt"].replace("Z", "+00:00"))
    replacements = {
        "DOCUMENT_TITLE": escaped(f"{plan['planName']} · Foundry Zero Plan"),
        "INLINE_CSS": css,
        "PLAN_ID": escaped(plan["planId"]),
        "PLAN_NAME": escaped(plan["planName"]),
        "SUMMARY": escaped(plan["summary"]),
        "GENERATED_AT": escaped(plan["generatedAt"]),
        "DISPLAY_DATE": escaped(generated.strftime("%B %d, %Y")),
        "MILESTONE_URL": escaped(f"https://github.com/{plan['repo']}/milestones"),
        "REPO": escaped(plan["repo"]),
        "COMPONENTS": components_html(plan["architecture"]["components"]),
        "ARCHITECTURE_DIAGRAM": diagram(plan["architecture"]["diagramsMermaid"]["targetArchitecture"], "Target architecture"),
        "ISSUE_CARDS": issues_html(plan["issues"]),
        "DEPENDENCY_DIAGRAM": diagram(dependency_source(plan["issues"]), "Issue dependency DAG"),
        "ISSUE_TABLE": issue_table(plan["issues"]),
        "RISKS": risks_html(plan["issues"]),
        "WAVES_DIAGRAM": diagram(waves_source(plan["issues"]), "Execution waves"),
        "MERMAID_JS": mermaid_js,
    }
    for key, value in replacements.items():
        template = template.replace("{{" + key + "}}", value)
    leftovers = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", template)))
    if leftovers:
        raise PlanError(f"unresolved template token(s): {', '.join(leftovers)}")
    return template


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sidecar", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        plan = validate_plan(json.loads(args.sidecar.read_text(encoding="utf-8")))
        rendered = render(plan)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    except (OSError, json.JSONDecodeError, PlanError) as error:
        print(f"planner render error: {error}", file=sys.stderr)
        return 1
    print(f"rendered {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
