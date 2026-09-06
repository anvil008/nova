#!/usr/bin/env python3
"""Render a strict planner sidecar as Markdown, with an optional HTML companion."""

from __future__ import annotations

import argparse
import html
import itertools
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# A caller loading this module by file location leaves its directory off
# sys.path, so the sibling import has to place it there itself.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import diagrams

ROOT = Path(__file__).resolve().parents[1]
TOP_FIELDS = {
    "planId",
    "planName",
    "repo",
    "generatedAt",
    "summary",
    "architecture",
    "issues",
    "risks",
}
RISK_FIELDS = {"id", "title", "likelihood", "impact", "owner", "mitigation"}
ARCH_FIELDS = {"components", "changeSummary", "diagramsMermaid"}
ISSUE_FIELDS = {
    "key",
    "title",
    "body",
    "labels",
    "dependsOn",
    "ownershipHint",
    "wave",
    "acceptanceTests",
}
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
    if (
        not isinstance(architecture["components"], list)
        or not architecture["components"]
    ):
        raise PlanError("architecture.components must be a non-empty array")
    for index, component in enumerate(architecture["components"]):
        if isinstance(component, str):
            nonempty_string(component, f"architecture.components[{index}]")
        elif isinstance(component, dict):
            require_exact_fields(
                component, {"name", "purpose"}, f"architecture.components[{index}]"
            )
            nonempty_string(component["name"], f"architecture.components[{index}].name")
            nonempty_string(
                component["purpose"], f"architecture.components[{index}].purpose"
            )
        else:
            raise PlanError(
                f"architecture.components[{index}] must be a string or name/purpose object"
            )
    sources = architecture["diagramsMermaid"]
    if not isinstance(sources, dict) or not sources:
        raise PlanError("architecture.diagramsMermaid must be a non-empty object")
    for key, source in sources.items():
        nonempty_string(key, "architecture.diagramsMermaid key")
        nonempty_string(source, f"architecture.diagramsMermaid.{key}")
    for required_diagram in ("currentArchitecture", "targetArchitecture"):
        if required_diagram not in sources:
            raise PlanError(
                f"architecture.diagramsMermaid.{required_diagram} is required"
            )

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
        if not isinstance(issue["labels"], list) or any(
            not isinstance(label, str) or not label for label in issue["labels"]
        ):
            raise PlanError(
                f"issues[{index}].labels must be an array of non-empty strings"
            )
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
        if (
            not isinstance(issue["wave"], int)
            or isinstance(issue["wave"], bool)
            or issue["wave"] < 0
        ):
            raise PlanError(f"issues[{index}].wave must be a non-negative integer")
        tests = issue["acceptanceTests"]
        if not isinstance(tests, list) or not tests:
            raise PlanError(
                f"issues[{index}].acceptanceTests must be a non-empty array"
            )
        for tindex, spec in enumerate(tests):
            twhere = f"issues[{index}].acceptanceTests[{tindex}]"
            if not isinstance(spec, dict):
                raise PlanError(f"{twhere} must be an object")
            missing = ACC_REQUIRED - spec.keys()
            unknown = spec.keys() - ACC_ALLOWED
            if missing:
                raise PlanError(
                    f"{twhere}: missing field(s): {', '.join(sorted(missing))}"
                )
            if unknown:
                raise PlanError(
                    f"{twhere}: unknown field(s): {', '.join(sorted(unknown))}"
                )
            nonempty_string(spec["name"], f"{twhere}.name")
            if spec["kind"] not in ACC_KINDS:
                raise PlanError(
                    f"{twhere}.kind must be one of: {', '.join(sorted(ACC_KINDS))}"
                )
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
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value not in (1, 2, 3)
            ):
                raise PlanError(f"{where}.{axis} must be 1, 2, or 3")


PLAN_MARKER = "<!-- workcell-planner planId={plan_id} -->"
PLAN_FILE = re.compile(r"^plan(\d+)-\d{8}-.*\.(?:md|html)$")
SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def escaped(value: object) -> str:
    return html.escape(str(value), quote=True)


BOLD = re.compile(r"\*\*(.+?)\*\*")
CODE = re.compile(r"`([^`]+)`")


def prose(value: object) -> str:
    """Escape, then render the two inline marks plan text actually uses —
    **bold** and `code` — and split blank-line-separated paragraphs into
    <p> blocks, so a long summary reads as prose rather than one wall."""
    paragraphs = []
    for block in re.split(r"\n\s*\n", str(value).strip()):
        text = escaped(" ".join(block.split()))
        text = BOLD.sub(r"<strong>\1</strong>", text)
        text = CODE.sub(r"<code>\1</code>", text)
        paragraphs.append(f"<p>{text}</p>")
    return "".join(paragraphs)


def title_slug(plan_name: str, limit: int = 60) -> str:
    slug = SLUG_STRIP.sub("-", plan_name.lower()).strip("-")
    if len(slug) > limit:
        slug = slug[:limit].rsplit("-", 1)[0] or slug[:limit]
    return slug or "plan"


def plan_path(plan: dict, plans_dir: Path, extension: str = "md") -> Path:
    """Allocate a stable plan filename shared by its Markdown and HTML versions.

    The number is allocated once per plan and then reused: a re-render of the
    same planId overwrites its existing file rather than claiming a new number,
    so revising a plan never scatters stale copies across the directory.
    """
    marker = PLAN_MARKER.format(plan_id=plan["planId"])
    taken: set[int] = set()
    if plans_dir.is_dir():
        for existing in sorted(plans_dir.glob("plan*")):
            match = PLAN_FILE.match(existing.name)
            if not match:
                continue
            taken.add(int(match.group(1)))
            try:
                if marker in existing.read_text(encoding="utf-8"):
                    return existing.with_suffix(f".{extension}")
            except OSError:
                continue
    number = next(n for n in range(1, len(taken) + 2) if n not in taken)
    date = datetime.fromisoformat(plan["generatedAt"].replace("Z", "+00:00")).strftime(
        "%Y%m%d"
    )
    return plans_dir / f"plan{number:02d}-{date}-{title_slug(plan['planName'])}.{extension}"


def markdown_fence(value: str, language: str = "") -> str:
    """Keep authored diagrams and test skeletons inside their code block."""
    longest = max((len(run) for run in re.findall(r"`+", value)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{value}\n{fence}"


def render_markdown(plan: dict) -> str:
    """Include every acceptance criterion and implementation detail in the plan."""
    sections = [
        PLAN_MARKER.format(plan_id=plan["planId"]),
        f"# {plan['planName']}",
        f"Repository: {plan['repo'] or 'Local repository'}  \nPlan: {plan['planId']}  \nGenerated: {plan['generatedAt']}",
        "## Goal and decisions", plan["summary"],
        "## Architecture change", plan["architecture"]["changeSummary"],
    ]
    components = []
    for component in plan["architecture"]["components"]:
        components.append(
            f"- {component}" if isinstance(component, str)
            else f"- **{component['name']}**: {component['purpose']}"
        )
    sections.append("\n".join(components))
    sources = plan["architecture"]["diagramsMermaid"]
    for key, title in (("currentArchitecture", "Current"), ("targetArchitecture", "Proposed")):
        sections.extend([f"### {title}", markdown_fence(sources[key], "mermaid")])
    for key, source in sources.items():
        if key not in {"currentArchitecture", "targetArchitecture"}:
            sections.extend([f"### {key}", markdown_fence(source, "mermaid")])
    sections.append("## Implementation issues")
    for issue in plan["issues"]:
        sections.extend([
            f"### {issue['key']}: {issue['title']}", issue["body"],
            f"- Wave: {issue['wave']}\n"
            f"- Ownership: {issue['ownershipHint']}\n"
            f"- Dependencies: {', '.join(issue['dependsOn']) or 'None'}\n"
            f"- Labels: {', '.join(issue['labels']) or 'None'}",
            "Acceptance criteria:",
        ])
        tests = []
        for spec in issue["acceptanceTests"]:
            tests.append(f"- [ ] **{spec['name']}** ({spec['kind']}): {spec['oracle']}")
            if "testPath" in spec:
                tests.append(f"  Test path: {spec['testPath']}")
            if "stub" in spec:
                tests.append("\n" + markdown_fence(spec["stub"]))
        sections.append("\n".join(tests))
    sections.append("## Execution waves")
    for wave in sorted({issue["wave"] for issue in plan["issues"]}):
        keys = ", ".join(issue["key"] for issue in plan["issues"] if issue["wave"] == wave)
        sections.append(f"- Wave {wave}: {keys}")
    sections.append("## Risks")
    if not plan["risks"]:
        sections.append("No identified risks were recorded for this plan.")
    for risk in plan["risks"]:
        sections.extend([
            f"### {risk['id']}: {risk['title']}",
            f"- Likelihood: {risk['likelihood']}/3\n- Impact: {risk['impact']}/3\n"
            f"- Owner: {risk['owner']}\n- Mitigation: {risk['mitigation']}",
        ])
    return "\n\n".join(sections) + "\n"


def node_id(key: str) -> str:
    return "issue_" + key.replace("-", "_")


WAVE_SLOTS = 5


def wave_slot(wave: int) -> int:
    """Map an unbounded wave number onto one of the five themed colour slots."""
    return (wave - 1) % WAVE_SLOTS + 1


def authored_diagram(source: str, key: str, dom_id: str, title: str) -> str:
    """A sidecar diagram. Mermaid stays the authoring format; SVG is what ships."""
    parsed = diagrams.parse(source, f"architecture.diagramsMermaid.{key}")
    return diagrams.block(parsed, dom_id, title)


def dependency_diagram(issues: list[dict]) -> diagrams.Diagram:
    """The issue DAG, built straight from the validated issues. Wave paint comes
    from the slot class, which plan.css resolves against the active theme."""
    known = {issue["key"] for issue in issues}
    diagram = diagrams.Diagram("LR")
    for issue in issues:
        slot = f"wave{wave_slot(issue['wave'])}" if issue["wave"] > 0 else "neutral"
        diagram.node(node_id(issue["key"]), issue["title"], sub=issue["key"], css=slot)
    for issue in issues:
        for dependency in issue["dependsOn"]:
            if dependency not in known:
                diagram.node(
                    node_id(dependency), f"{dependency} (external)", css="neutral"
                )
            diagram.edge(node_id(dependency), node_id(issue["key"]))
    return diagram


def waves_diagram(issues: list[dict]) -> diagrams.Diagram:
    grouped: dict[int, list[dict]] = {}
    for issue in issues:
        grouped.setdefault(issue["wave"], []).append(issue)
    ordered = sorted(wave for wave in grouped if wave > 0)
    diagram = diagrams.Diagram("TD")
    for wave in ordered:
        keys = " · ".join(issue["key"] for issue in grouped[wave])
        diagram.node(
            f"wave_{wave}", f"Wave {wave}", sub=keys, css=f"wave{wave_slot(wave)}"
        )
    for left, right in itertools.pairwise(ordered):
        diagram.edge(f"wave_{left}", f"wave_{right}")
    if 0 in grouped:
        keys = " · ".join(issue["key"] for issue in grouped[0])
        diagram.node("ungrouped", "Ungrouped", sub=keys, css="neutral")
    return diagram


def components_html(components: list[object]) -> str:
    cards = []
    for component in components:
        if isinstance(component, dict):
            name, purpose = component["name"], component["purpose"]
        else:
            name, purpose = component, "Target component"
        cards.append(
            f'<article class="card"><h3>{escaped(name)}</h3><p>{escaped(purpose)}</p></article>'
        )
    return "".join(cards)


def metrics_html(plan: dict) -> str:
    issues = plan["issues"]
    known = {issue["key"] for issue in issues}
    external = sorted(
        {dep for issue in issues for dep in issue["dependsOn"] if dep not in known}
    )
    waves = sorted({issue["wave"] for issue in issues if issue["wave"] > 0})
    top_risks = [
        risk for risk in plan["risks"] if risk["likelihood"] * risk["impact"] >= 6
    ]
    tests = sum(len(issue["acceptanceTests"]) for issue in issues)
    cells = [
        ("Issues", len(issues), "", f"{len(waves)} parallel waves", ""),
        ("Acceptance tests", tests, "", "definition of done", ""),
        (
            "External deps",
            len(external),
            "",
            ", ".join(external) if external else "all internal",
            "high" if external else "",
        ),
        (
            "Risks",
            len(plan["risks"]),
            "",
            f"{len(top_risks)} in the top band",
            "critical" if top_risks else "ok",
        ),
    ]
    tiles = []
    for label, value, unit, delta, tone in cells:
        tone_class = f" tone-{tone}" if tone else ""
        unit_html = f"<span>{escaped(unit)}</span>" if unit else ""
        tiles.append(
            f'<div class="metric{tone_class}"><div class="k">{escaped(label)}</div>'
            f'<div class="v">{escaped(value)}{unit_html}</div>'
            f'<div class="d">{escaped(delta)}</div></div>'
        )
    return f'<div class="metrics">{"".join(tiles)}</div>'


def issues_html(issues: list[dict]) -> str:
    rows = []
    for issue in issues:
        labels = "".join(
            f'<span class="tag">{escaped(label)}</span>' for label in issue["labels"]
        )
        depends = ", ".join(issue["dependsOn"]) or "—"
        wave = f"Wave {issue['wave']}" if issue["wave"] else "Ungrouped"
        rows.append(
            '<details class="row"><summary>'
            '<span class="stripe bar-low"></span>'
            '<div class="row-body">'
            f'<div class="row-title"><span class="issue-key">{escaped(issue["key"])}</span>'
            f"<strong>{escaped(issue['title'])}</strong></div>"
            f'<div class="row-meta"><span>{escaped(wave)}</span><span>{escaped(issue["ownershipHint"])}</span>'
            f"{labels}</div></div>"
            '<span class="caret">&#9662;</span></summary>'
            '<div class="row-detail">'
            f'<div class="issue-body">{prose(issue["body"])}</div>'
            '<div class="issue-facts">'
            f'<div><div class="k">Depends on</div><div class="v">{escaped(depends)}</div></div>'
            f'<div><div class="k">Ownership</div><div class="v">{escaped(issue["ownershipHint"])}</div></div>'
            f'<div><div class="k">Wave</div><div class="v">{escaped(wave)}</div></div>'
            "</div></div></details>"
        )
    return "".join(rows)


def issue_table(issues: list[dict]) -> str:
    rows = []
    for issue in issues:
        depends = ", ".join(issue["dependsOn"]) or "—"
        wave = issue["wave"] or "Ungrouped"
        rows.append(
            f'<tr><td class="mono">{escaped(issue["key"])}</td><td>{escaped(issue["title"])}</td>'
            f'<td class="mono">{escaped(depends)}</td><td class="mono">{escaped(wave)}</td>'
            f'<td class="mono">{escaped(issue["ownershipHint"])}</td></tr>'
        )
    return (
        '<table><thead><tr><th class="mono">Key</th><th>Issue</th><th>Depends on</th>'
        "<th>Wave</th><th>Ownership</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def waves_html(issues: list[dict]) -> str:
    grouped: dict[int, list[dict]] = {}
    for issue in issues:
        grouped.setdefault(issue["wave"], []).append(issue)
    lanes = []
    for wave in sorted(w for w in grouped if w > 0):
        members = grouped[wave]
        items = "".join(
            f'<span class="wave-item"><span class="k">{escaped(issue["key"])}</span>{escaped(issue["title"])}</span>'
            for issue in members
        )
        plural = "issue" if len(members) == 1 else "issues"
        lanes.append(
            f'<div class="wave"><div class="wave-label"><div class="n">Wave {wave}</div>'
            f'<div class="t">{"Parallel" if len(members) > 1 else "Single"}</div>'
            f'<div class="c">{len(members)} {plural}</div></div>'
            f'<div class="wave-items">{items}</div></div>'
        )
    if 0 in grouped:
        items = "".join(
            f'<span class="wave-item"><span class="k">{escaped(issue["key"])}</span>{escaped(issue["title"])}</span>'
            for issue in grouped[0]
        )
        lanes.append(
            '<div class="wave ungrouped"><div class="wave-label"><div class="n">Unassigned</div>'
            '<div class="t">Ungrouped</div><div class="c">no wave</div></div>'
            f'<div class="wave-items">{items}</div></div>'
        )
    if not lanes:
        return '<div class="empty">No execution waves are defined.</div>'
    return f'<div class="waves">{"".join(lanes)}</div>'


AXIS = {1: "low", 2: "med", 3: "high"}


def risks_html(risks: list[dict]) -> str:
    if not risks:
        return '<div class="empty">No risks recorded for this plan.</div>'

    placed: dict[tuple[int, int], list[str]] = {}
    for risk in risks:
        placed.setdefault((risk["likelihood"], risk["impact"]), []).append(risk["id"])

    cells = []
    for likelihood in (3, 2, 1):
        cells.append(f'<div class="matrix-y">{AXIS[likelihood]}</div>')
        for impact in (1, 2, 3):
            pins = "".join(
                f'<span class="pin">{escaped(identifier)}</span>'
                for identifier in placed.get((likelihood, impact), [])
            )
            cells.append(f'<div class="cell s{likelihood * impact}">{pins}</div>')

    entries = []
    for risk in sorted(
        risks, key=lambda r: (-(r["likelihood"] * r["impact"]), r["id"])
    ):
        entries.append(
            '<article class="risk">'
            f'<div class="risk-head"><span class="id">{escaped(risk["id"])}</span>'
            f"<strong>{escaped(risk['title'])}</strong>"
            f'<span class="owner">{escaped(risk["owner"])}</span></div>'
            f'<p><span class="k">Likelihood {AXIS[risk["likelihood"]]} &middot; impact {AXIS[risk["impact"]]}</span></p>'
            f'<p><span class="k">Mitigation</span>{escaped(risk["mitigation"])}</p>'
            "</article>"
        )

    return (
        '<div class="risk-layout"><div class="matrix">'
        f'<div class="matrix-grid">{"".join(cells)}</div>'
        '<div class="matrix-x"><span></span><span>low</span><span>med</span><span>high</span></div>'
        '<div class="matrix-axis">likelihood &uarr; &middot; impact &rarr;</div>'
        f'</div><div class="risk-list">{"".join(entries)}</div></div>'
    )


def render(plan: dict) -> str:
    templates = ROOT / "templates"
    template = (templates / "plan.html.tmpl").read_text(encoding="utf-8")
    css = (
        (templates / "report.css").read_text(encoding="utf-8")
        + "\n"
        + (templates / "plan.css").read_text(encoding="utf-8")
    )
    generated = datetime.fromisoformat(plan["generatedAt"].replace("Z", "+00:00"))
    waves = {issue["wave"] for issue in plan["issues"] if issue["wave"] > 0}
    replacements = {
        "PLAN_MARKER": PLAN_MARKER.format(plan_id=plan["planId"]),
        "DOCUMENT_TITLE": escaped(f"{plan['planName']} · Workcell Plan"),
        "INLINE_CSS": css,
        "PLAN_ID": escaped(plan["planId"]),
        "PLAN_NAME": escaped(plan["planName"]),
        "SUMMARY": prose(plan["summary"]),
        "GENERATED_AT": escaped(plan["generatedAt"]),
        "DISPLAY_DATE": escaped(generated.strftime("%B %d, %Y")),
        "MILESTONE_TARGET": (
            f'<a href="https://github.com/{escaped(plan["repo"])}/milestones">{escaped(plan["planName"])}</a>'
            if plan["repo"] is not None else "Local task ledger"
        ),
        "REPO": escaped(plan["repo"] or "Local repository"),
        "ISSUE_COUNT": escaped(len(plan["issues"])),
        "WAVE_COUNT": escaped(len(waves)),
        "RISK_COUNT": escaped(len(plan["risks"])),
        "METRICS": metrics_html(plan),
        "COMPONENTS": components_html(plan["architecture"]["components"]),
        "ARCHITECTURE_DELTA": escaped(plan["architecture"]["changeSummary"]),
        "CURRENT_ARCHITECTURE_DIAGRAM": authored_diagram(
            plan["architecture"]["diagramsMermaid"]["currentArchitecture"],
            "currentArchitecture",
            "d-current",
            "Current architecture",
        ),
        "PROPOSED_ARCHITECTURE_DIAGRAM": authored_diagram(
            plan["architecture"]["diagramsMermaid"]["targetArchitecture"],
            "targetArchitecture",
            "d-proposed",
            "Proposed architecture",
        ),
        "ISSUE_CARDS": issues_html(plan["issues"]),
        "DEPENDENCY_DIAGRAM": diagrams.block(
            dependency_diagram(plan["issues"]), "d-deps", "Issue dependency graph"
        ),
        "ISSUE_TABLE": issue_table(plan["issues"]),
        "WAVES": waves_html(plan["issues"]),
        "RISKS": risks_html(plan["risks"]),
        "WAVES_DIAGRAM": diagrams.block(
            waves_diagram(plan["issues"]), "d-waves", "Execution wave order"
        ),
    }
    return substitute_tokens(template, replacements)


def substitute_tokens(template: str, replacements: dict[str, str]) -> str:
    """Single pass: a token-shaped string inside user text is never re-substituted."""
    leftovers: list[str] = []

    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in replacements:
            leftovers.append(match.group(0))
            return match.group(0)
        return replacements[key]

    rendered = re.sub(r"\{\{([A-Z_]+)\}\}", substitute, template)
    if leftovers:
        raise PlanError(
            f"unresolved template token(s): {', '.join(sorted(set(leftovers)))}"
        )
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sidecar", type=Path)
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="explicit .md or .html path; .html requests both formats",
    )
    parser.add_argument("--plans-dir", type=Path, default=Path("docs/plans"))
    parser.add_argument("--format", choices=("md", "html"), help="default: md; html adds a visual companion")
    args = parser.parse_args()
    try:
        plan = validate_plan(json.loads(args.sidecar.read_text(encoding="utf-8")))
        requested_format = args.format or ("html" if args.output and args.output.suffix == ".html" else "md")
        output = args.output or plan_path(plan, args.plans_dir, requested_format)
        if output.suffix != f".{requested_format}":
            raise PlanError(f"output must end in .{requested_format} for the requested format")
        outputs = {output.with_suffix(".md"): render_markdown(plan)}
        if requested_format == "html":
            outputs[output] = render(plan)
        # Validate/render every requested artifact before writing any of them.
        for path, content in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    except (OSError, json.JSONDecodeError, PlanError, diagrams.DiagramError) as error:
        print(f"planner render error: {error}", file=sys.stderr)
        return 1
    for path in outputs:
        print(f"rendered {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
