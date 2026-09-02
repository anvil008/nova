#!/usr/bin/env python3
"""Render a merged research packet (merge_research.py output) as a self-contained HTML report.

The packet is evidence. The optional synthesis file carries the primary agent's
conclusion: a verdict, a summary, and recommendations that cite findings.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET_FIELDS = {"inputFindingCount", "findingCount", "areas", "conflicts", "coverage", "gaps", "openQuestions"}
FINDING_FIELDS = {"source", "finding", "evidence", "topic", "position", "stance"}
STANCES = ("supports", "contradicts", "neutral")
SYNTHESIS_FIELDS = {"verdict", "summary", "recommendations"}
REC_FIELDS = {"priority", "title", "detail", "refs"}
PRIORITIES = ("high", "medium", "low")
PRIORITY_BAR = {"high": "bar-high", "medium": "bar-medium", "low": "bar-low"}
VERDICTS = {
    "clean": ("verdict-clean", "Clean — no issues found that need action"),
    "advisory": ("verdict-advisory", "Advisory — issues found, none urgent"),
    "action-needed": ("verdict-action", "Action needed — issues found that should be fixed"),
}
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class ResearchRenderError(ValueError):
    pass


def require_exact_fields(value: object, expected: set[str], where: str) -> dict:
    if not isinstance(value, dict):
        raise ResearchRenderError(f"{where} must be an object")
    missing = expected - value.keys()
    unknown = value.keys() - expected
    if missing:
        raise ResearchRenderError(f"{where}: missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise ResearchRenderError(f"{where}: unknown field(s): {', '.join(sorted(unknown))}")
    return value


def nonempty_string(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchRenderError(f"{where} must be a non-empty string")
    return value.strip()


def string_list(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ResearchRenderError(f"{where} must be an array of non-empty strings")
    return value


def validate_packet(packet: object) -> dict:
    require_exact_fields(packet, PACKET_FIELDS, "packet")
    for field in ("inputFindingCount", "findingCount"):
        if not isinstance(packet[field], int) or isinstance(packet[field], bool) or packet[field] < 0:
            raise ResearchRenderError(f"{field} must be a non-negative integer")
    if not isinstance(packet["areas"], list):
        raise ResearchRenderError("areas must be an array")
    total = 0
    for index, area in enumerate(packet["areas"]):
        require_exact_fields(area, {"area", "findings"}, f"areas[{index}]")
        nonempty_string(area["area"], f"areas[{index}].area")
        if not isinstance(area["findings"], list):
            raise ResearchRenderError(f"areas[{index}].findings must be an array")
        for j, finding in enumerate(area["findings"]):
            require_exact_fields(finding, FINDING_FIELDS, f"areas[{index}].findings[{j}]")
            for field in FINDING_FIELDS:
                nonempty_string(finding[field], f"areas[{index}].findings[{j}].{field}")
            if finding["stance"] not in STANCES:
                raise ResearchRenderError(f"areas[{index}].findings[{j}].stance must be one of: {', '.join(STANCES)}")
        total += len(area["findings"])
    if total != packet["findingCount"]:
        raise ResearchRenderError("findingCount does not match the findings present")
    if not isinstance(packet["conflicts"], list):
        raise ResearchRenderError("conflicts must be an array")
    for index, conflict in enumerate(packet["conflicts"]):
        require_exact_fields(conflict, {"topic", "positions"}, f"conflicts[{index}]")
        nonempty_string(conflict["topic"], f"conflicts[{index}].topic")
        string_list(conflict["positions"], f"conflicts[{index}].positions")
    coverage = require_exact_fields(packet["coverage"], {"missingAreas", "complete"}, "coverage")
    string_list(coverage["missingAreas"], "coverage.missingAreas")
    if not isinstance(coverage["complete"], bool) or coverage["complete"] != (not coverage["missingAreas"]):
        raise ResearchRenderError("coverage.complete must be a bool consistent with missingAreas")
    string_list(packet["gaps"], "gaps")
    string_list(packet["openQuestions"], "openQuestions")
    return packet


def validate_synthesis(synthesis: object, packet: dict) -> dict:
    require_exact_fields(synthesis, SYNTHESIS_FIELDS, "synthesis")
    if synthesis["verdict"] not in VERDICTS:
        raise ResearchRenderError(f"synthesis.verdict must be one of: {', '.join(VERDICTS)}")
    nonempty_string(synthesis["summary"], "synthesis.summary")
    if not isinstance(synthesis["recommendations"], list):
        raise ResearchRenderError("synthesis.recommendations must be an array")
    known_ids = {identifier(a, i) for a, area in enumerate(packet["areas"]) for i in range(len(area["findings"]))}
    for index, rec in enumerate(synthesis["recommendations"]):
        require_exact_fields(rec, REC_FIELDS, f"synthesis.recommendations[{index}]")
        if rec["priority"] not in PRIORITIES:
            raise ResearchRenderError(f"synthesis.recommendations[{index}].priority must be one of: {', '.join(PRIORITIES)}")
        nonempty_string(rec["title"], f"synthesis.recommendations[{index}].title")
        nonempty_string(rec["detail"], f"synthesis.recommendations[{index}].detail")
        for ref in string_list(rec["refs"], f"synthesis.recommendations[{index}].refs"):
            if ref not in known_ids:
                raise ResearchRenderError(f"synthesis.recommendations[{index}].refs cites unknown finding {ref}")
    if synthesis["verdict"] == "clean" and synthesis["recommendations"]:
        raise ResearchRenderError("a clean verdict cannot carry recommendations")
    return synthesis


def escaped(value: object) -> str:
    return html.escape(str(value), quote=True)


def identifier(area_index: int, finding_index: int) -> str:
    return f"F{area_index + 1}-{finding_index + 1:02d}"


def metrics_html(packet: dict, rec_count: int) -> str:
    conflicts = len(packet["conflicts"])
    missing = len(packet["coverage"]["missingAreas"])
    cells = [
        ("Raw findings", packet["inputFindingCount"], "before dedupe", ""),
        ("Deduplicated", packet["findingCount"], f"across {len(packet['areas'])} area(s)", ""),
        ("Conflicts", conflicts, "topics with a contradicting stance", "high" if conflicts else "ok"),
        ("Missing areas", missing, "declared, no report", "critical" if missing else "ok"),
        ("Gaps", len(packet["gaps"]), "unresolved by an area", ""),
        ("Open questions", len(packet["openQuestions"]), "raised by an area", ""),
    ]
    tiles = []
    for label, value, delta, tone in cells:
        tone_class = f" tone-{tone}" if tone else ""
        tiles.append(
            f'<div class="metric{tone_class}"><div class="k">{escaped(label)}</div>'
            f'<div class="v">{escaped(value)}</div>'
            f'<div class="d">{escaped(delta)}</div></div>'
        )
    return f'<div class="metrics">{"".join(tiles)}</div>'


def area_filters(packet: dict) -> str:
    buttons = []
    for area in packet["areas"]:
        buttons.append(
            f'<button type="button" class="filter" aria-pressed="true" data-value="{escaped(area["area"])}">'
            f'{escaped(area["area"])} <span class="n">{len(area["findings"])}</span></button>'
        )
    return "".join(buttons)


def finding_rows(packet: dict) -> str:
    rows = []
    for a, area in enumerate(packet["areas"]):
        for i, finding in enumerate(area["findings"]):
            rows.append(
                f'<details class="row" id="{identifier(a, i)}" data-area="{escaped(area["area"])}">'
                "<summary>"
                '<span class="stripe" style="background: var(--acc);"></span>'
                '<div class="row-body">'
                '<div class="row-title">'
                f'<span class="finding-id">{escaped(identifier(a, i))}</span>'
                f'<strong>{escaped(finding["finding"])}</strong></div>'
                '<div class="row-meta">'
                f'<span class="loc">{escaped(finding["source"])}</span>'
                f'<span class="area">{escaped(area["area"])}</span>'
                f'<span class="topic">{escaped(finding["topic"])}</span>'
                "</div></div>"
                '<span class="caret">&#9662;</span></summary>'
                '<div class="row-detail">'
                '<div class="block proof"><div class="k">Evidence</div>'
                f'<p>{escaped(finding["evidence"])}</p></div>'
                f'<div class="block"><div class="k">Position ({escaped(finding["stance"])})</div>'
                f'<p>{escaped(finding["position"])}</p></div>'
                "</div></details>"
            )
    if not rows:
        return '<div class="empty">No area returned a substantiated finding.</div>'
    return "".join(rows)


def recommendations_html(synthesis: dict | None) -> str:
    if synthesis is None:
        return '<div class="empty">No synthesis supplied; the packet is evidence only.</div>'
    recs = sorted(synthesis["recommendations"], key=lambda r: PRIORITIES.index(r["priority"]))
    if not recs:
        return '<div class="empty">No recommendations — nothing in the evidence calls for action.</div>'
    items = []
    for index, rec in enumerate(recs):
        refs = "".join(f'<a class="tag" href="#{escaped(r)}">{escaped(r)}</a>' for r in rec["refs"])
        items.append(
            f'<article class="rec"><span class="stripe {PRIORITY_BAR[rec["priority"]]}"></span><div>'
            f'<h3><span class="sev sev-{escaped(rec["priority"])}">{escaped(rec["priority"])}</span>'
            f'<span class="finding-id">R-{index + 1:02d}</span>{escaped(rec["title"])}</h3>'
            f'<p>{escaped(rec["detail"])}</p>'
            f'<div class="refs">{refs}</div></div></article>'
        )
    return f'<div class="recs">{"".join(items)}</div>'


def conflicts_html(packet: dict) -> str:
    if not packet["conflicts"]:
        return '<div class="empty">No finding contradicted another position on its topic.</div>'
    blocks = []
    for conflict in packet["conflicts"]:
        positions = "".join(f"<li>{escaped(p)}</li>" for p in conflict["positions"])
        blocks.append(f'<div class="conflict"><div class="k">{escaped(conflict["topic"])}</div><ul>{positions}</ul></div>')
    return "".join(blocks)


def coverage_html(packet: dict) -> str:
    missing = packet["coverage"]["missingAreas"]
    if not missing:
        return '<div class="callout note"><span class="mark">&#9679;</span><p>Every declared area returned a report; the packet is complete.</p></div>'
    return (
        '<div class="callout blocker"><span class="mark">&#9679;</span>'
        f'<p>Packet incomplete — no report for: {escaped(", ".join(missing))}.</p></div>'
    )


def prefixed_list(items: list[str]) -> str:
    if not items:
        return '<div class="empty">None recorded.</div>'
    out = []
    for item in items:
        area, sep, rest = item.partition(": ")
        if sep:
            out.append(f'<li><span class="area">{escaped(area)}</span>{escaped(rest)}</li>')
        else:
            out.append(f"<li>{escaped(item)}</li>")
    return f'<ul class="list">{"".join(out)}</ul>'


def render(packet: dict, synthesis: dict | None, context: dict) -> str:
    templates = ROOT / "templates"
    template = (templates / "research.html.tmpl").read_text(encoding="utf-8")
    css = (templates / "report.css").read_text(encoding="utf-8") + "\n" + (templates / "research.css").read_text(encoding="utf-8")
    complete = packet["coverage"]["complete"]
    if synthesis is None:
        verdict_class, verdict_text = "verdict-advisory", "Evidence only — no synthesis supplied"
    else:
        verdict_class, verdict_text = VERDICTS[synthesis["verdict"]]
    if not complete:
        verdict_class = "verdict-incomplete"
    rec_count = len(synthesis["recommendations"]) if synthesis else 0
    generated = datetime.fromisoformat(context["generatedAt"].replace("Z", "+00:00"))
    lede = (
        f"{packet['findingCount']} deduplicated finding(s) from {packet['inputFindingCount']} raw observation(s) "
        f"across {len(packet['areas'])} area(s); {len(packet['conflicts'])} conflict(s), "
        f"{len(packet['gaps'])} gap(s), {len(packet['openQuestions'])} open question(s)."
    )
    summary = f'<p style="margin-top:16px;">{escaped(synthesis["summary"])}</p>' if synthesis else ""
    replacements = {
        "DOCUMENT_TITLE": escaped(f"{context['title']} · Foundry Zero Research"),
        "INLINE_CSS": css,
        "TITLE": escaped(context["title"]),
        "LEDE": escaped(lede),
        "REPO": escaped(context["repo"]),
        "SUBJECT": escaped(context["subject"]),
        "GENERATED_AT": escaped(context["generatedAt"]),
        "DISPLAY_DATE": escaped(generated.strftime("%B %d, %Y")),
        "VERDICT_CLASS": verdict_class,
        "VERDICT_TEXT": escaped(verdict_text),
        "COVERAGE_TEXT": "complete" if complete else f"incomplete · {len(packet['coverage']['missingAreas'])} missing",
        "AREA_COUNT": escaped(len(packet["areas"])),
        "FINDING_COUNT": escaped(packet["findingCount"]),
        "REC_COUNT": escaped(rec_count),
        "CONFLICT_COUNT": escaped(len(packet["conflicts"])),
        "METRICS": metrics_html(packet, rec_count),
        "AREAS": "".join(f'<span class="tag">{escaped(a["area"])}</span>' for a in packet["areas"]) or '<span class="tag">none</span>',
        "SUMMARY": summary,
        "RECOMMENDATIONS": recommendations_html(synthesis),
        "AREA_FILTERS": area_filters(packet),
        "FINDINGS": finding_rows(packet),
        "CONFLICTS": conflicts_html(packet),
        "COVERAGE": coverage_html(packet),
        "GAPS": prefixed_list(packet["gaps"]),
        "OPEN_QUESTIONS": prefixed_list(packet["openQuestions"]),
    }
    # Single pass: a token-shaped string inside user text is never re-substituted.
    leftovers: list[str] = []

    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in replacements:
            leftovers.append(match.group(0))
            return match.group(0)
        return replacements[key]

    template = re.sub(r"\{\{([A-Z_]+)\}\}", substitute, template)
    if leftovers:
        raise ResearchRenderError(f"unresolved template token(s): {', '.join(sorted(set(leftovers)))}")
    return template


def build_context(args: argparse.Namespace) -> dict:
    repo = args.repo.strip()
    if repo != "—" and not REPOSITORY.fullmatch(repo):
        raise ResearchRenderError("--repo must be owner/name")
    generated_at = args.generated_at or datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ResearchRenderError("--generated-at must be ISO8601") from error
    return {
        "title": args.title.strip() or "Research packet",
        "repo": repo,
        "subject": args.subject.strip(),
        "generatedAt": generated_at,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path, help="output of merge_research.py")
    parser.add_argument("output", type=Path)
    parser.add_argument("--synthesis", type=Path, default=None, help="JSON: {verdict, summary, recommendations[]}")
    parser.add_argument("--title", default="Research packet")
    parser.add_argument("--repo", default="—", help="owner/name")
    parser.add_argument("--subject", default="repository", help="what was researched")
    parser.add_argument("--generated-at", default="", help="ISO8601; defaults to now")
    args = parser.parse_args()
    try:
        context = build_context(args)
        packet = validate_packet(json.loads(args.packet.read_text(encoding="utf-8")))
        synthesis = None
        if args.synthesis is not None:
            synthesis = validate_synthesis(json.loads(args.synthesis.read_text(encoding="utf-8")), packet)
        rendered = render(packet, synthesis, context)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    except (OSError, json.JSONDecodeError, ResearchRenderError) as error:
        print(f"research render error: {error}", file=sys.stderr)
        return 1
    print(f"rendered {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
