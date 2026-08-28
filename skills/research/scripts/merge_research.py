#!/usr/bin/env python3
"""Merge per-area research reports into one deduplicated evidence packet.

Reads the declared areas manifest plus one report per area, deduplicates
findings by (area, source, finding), groups them by declared-area order,
surfaces cross-area conflicts (a shared topic where at least one finding
takes the `contradicts` stance) without dropping any finding, and reports
coverage, gaps, and open questions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


AREAS_FIELDS = {"areas"}
AREA_DECL_FIELDS = {"area", "scope", "sources"}
REPORT_FIELDS = {"area", "coverage", "findings", "gaps", "openQuestions"}
COVERAGE_FIELDS = {"scope", "sourcesInspected"}
FINDING_FIELDS = ("source", "finding", "evidence", "topic", "position")
STANCE_FIELD = "stance"
STANCES = ("supports", "contradicts", "neutral")
DEFAULT_STANCE = "neutral"


class ResearchError(ValueError):
    pass


def exact_fields(value: object, expected: set[str], where: str, optional: set[str] = frozenset()) -> None:
    if not isinstance(value, dict):
        raise ResearchError(f"{where} must be an object")
    missing = expected - value.keys()
    unknown = value.keys() - expected - optional
    if missing:
        raise ResearchError(f"{where}: missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise ResearchError(f"{where}: unknown field(s): {', '.join(sorted(unknown))}")


def nonempty_string(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchError(f"{where} must be a non-empty string")
    return value.strip()


def string_list(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ResearchError(f"{where} must be an array of non-empty strings")
    return value


def load_areas(path: Path) -> list[str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    exact_fields(value, AREAS_FIELDS, "areas")
    if not isinstance(value["areas"], list) or not value["areas"]:
        raise ResearchError("areas.areas must be a non-empty array")
    order: list[str] = []
    for index, declared in enumerate(value["areas"]):
        exact_fields(declared, AREA_DECL_FIELDS, f"areas.areas[{index}]")
        name = nonempty_string(declared["area"], f"areas.areas[{index}].area")
        string_list(declared["sources"], f"areas.areas[{index}].sources")
        nonempty_string(declared["scope"], f"areas.areas[{index}].scope")
        if name in order:
            raise ResearchError(f"duplicate declared area: {name}")
        order.append(name)
    return order


def load_report(path: Path, declared: list[str]) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    exact_fields(value, REPORT_FIELDS, "report")
    area = nonempty_string(value["area"], "report.area")
    if area not in declared:
        raise ResearchError(f"report area '{area}' is not declared in the areas manifest")
    exact_fields(value["coverage"], COVERAGE_FIELDS, "report.coverage")
    nonempty_string(value["coverage"]["scope"], "report.coverage.scope")
    string_list(value["coverage"]["sourcesInspected"], "report.coverage.sourcesInspected")
    if not isinstance(value["findings"], list):
        raise ResearchError("report.findings must be an array")
    value["findings"] = [load_finding(finding, f"report.findings[{index}]") for index, finding in enumerate(value["findings"])]
    if not isinstance(value["gaps"], list) or any(not isinstance(x, str) or not x.strip() for x in value["gaps"]):
        raise ResearchError("report.gaps must be an array of non-empty strings")
    if not isinstance(value["openQuestions"], list) or any(not isinstance(x, str) or not x.strip() for x in value["openQuestions"]):
        raise ResearchError("report.openQuestions must be an array of non-empty strings")
    return value


def load_finding(value: object, where: str) -> dict:
    """Normalise one finding: strip every string and default the stance to neutral."""
    exact_fields(value, set(FINDING_FIELDS), where, optional={STANCE_FIELD})
    finding = {field: nonempty_string(value[field], f"{where}.{field}") for field in FINDING_FIELDS}
    stance = nonempty_string(value.get(STANCE_FIELD, DEFAULT_STANCE), f"{where}.{STANCE_FIELD}")
    if stance not in STANCES:
        raise ResearchError(f"{where}.{STANCE_FIELD} must be one of: {', '.join(STANCES)}")
    finding[STANCE_FIELD] = stance
    return finding


def build_packet(declared: list[str], reports: dict[str, dict]) -> dict:
    input_count = sum(len(reports[area]["findings"]) for area in reports)
    areas_out: list[dict] = []
    ranked_findings: list[dict] = []
    for area in declared:
        if area not in reports:
            continue
        seen: set[tuple[str, str, str]] = set()
        deduped: list[dict] = []
        for finding in reports[area]["findings"]:
            key = (area, finding["source"], finding["finding"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(finding)
        areas_out.append({"area": area, "findings": deduped})
        ranked_findings.extend(deduped)

    # Distinct wording is not disagreement: a topic conflicts only when a finding
    # explicitly contradicts, and then every position on that topic is listed.
    positions: dict[str, list[str]] = {}
    contested: set[str] = set()
    for finding in ranked_findings:
        bucket = positions.setdefault(finding["topic"], [])
        if finding["position"] not in bucket:
            bucket.append(finding["position"])
        if finding[STANCE_FIELD] == "contradicts":
            contested.add(finding["topic"])
    conflicts = [
        {"topic": topic, "positions": sorted(values)}
        for topic, values in sorted(positions.items())
        if topic in contested
    ]

    missing = [area for area in declared if area not in reports]
    gaps: list[str] = []
    open_questions: list[str] = []
    for area in declared:
        if area in reports:
            gaps.extend(f"{area}: {gap}" for gap in reports[area]["gaps"])
            open_questions.extend(f"{area}: {question}" for question in reports[area]["openQuestions"])
        else:
            gaps.append(f"{area}: no research report was supplied")

    return {
        "inputFindingCount": input_count,
        "findingCount": sum(len(area["findings"]) for area in areas_out),
        "areas": areas_out,
        "conflicts": conflicts,
        "coverage": {"missingAreas": missing, "complete": not missing},
        "gaps": gaps,
        "openQuestions": open_questions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("areas", type=Path)
    parser.add_argument("reports", type=Path, nargs="+")
    args = parser.parse_args()
    try:
        declared = load_areas(args.areas)
        reports: dict[str, dict] = {}
        for path in args.reports:
            report = load_report(path, declared)
            if report["area"] in reports:
                raise ResearchError(f"duplicate report for area {report['area']}")
            reports[report["area"]] = report
        print(json.dumps(build_packet(declared, reports), indent=2, sort_keys=False))
    except (OSError, json.JSONDecodeError, ResearchError) as error:
        print(f"research merge error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
