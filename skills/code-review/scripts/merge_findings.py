#!/usr/bin/env python3
"""Strictly deduplicate, verify, rank, and summarize structured review findings."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath


LENSES = {"correctness", "security", "performance", "tests", "api-contract"}
SEVERITIES = ("critical", "high", "medium", "low", "nit")
SEVERITY_RANK = {severity: rank for rank, severity in enumerate(SEVERITIES)}
SOURCE_FIELDS = {"lens", "findings"}
FINDING_FIELDS = {"file", "line", "severity", "lens", "claim", "failureScenario", "confidence"}
VERIFICATION_FIELDS = {"file", "line", "claim", "substantiated", "refutationAttempt", "evidence"}


class ReviewError(ValueError):
    pass


def exact_fields(value: dict, expected: set[str], where: str) -> None:
    missing = expected - value.keys()
    unknown = value.keys() - expected
    if missing:
        raise ReviewError(f"{where}: missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise ReviewError(f"{where}: unknown field(s): {', '.join(sorted(unknown))}")


def nonempty_string(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewError(f"{where} must be a non-empty string")
    return value.strip()


def repository_path(value: object, where: str) -> str:
    path = nonempty_string(value, where)
    parsed = PurePosixPath(path)
    if (
        parsed.is_absolute()
        or "\\" in path
        or str(parsed) != path
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise ReviewError(f"{where} must be a normalized relative repository path")
    return path


def positive_line(value: object, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ReviewError(f"{where} must be a positive integer")
    return value


def finding_key(finding: dict) -> tuple[str, int, str]:
    return finding["file"], finding["line"], finding["claim"]


def validate_finding(value: object, where: str, envelope_lens: str) -> dict:
    if not isinstance(value, dict):
        raise ReviewError(f"{where} must be an object")
    exact_fields(value, FINDING_FIELDS, where)
    finding = dict(value)
    finding["file"] = repository_path(finding["file"], f"{where}.file")
    finding["line"] = positive_line(finding["line"], f"{where}.line")
    finding["claim"] = nonempty_string(finding["claim"], f"{where}.claim")
    finding["failureScenario"] = nonempty_string(
        finding["failureScenario"], f"{where}.failureScenario"
    )
    if not isinstance(finding["severity"], str) or finding["severity"] not in SEVERITY_RANK:
        raise ReviewError(f"{where}.severity must be one of: {', '.join(SEVERITIES)}")
    if finding["lens"] != envelope_lens:
        raise ReviewError(f"{where}.lens must match envelope lens {envelope_lens}")
    confidence = finding["confidence"]
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not 0 <= confidence <= 1
    ):
        raise ReviewError(f"{where}.confidence must be a number between 0 and 1")
    return finding


def read_sources(paths: list[Path]) -> list[dict]:
    findings: list[dict] = []
    for source_index, path in enumerate(paths):
        value = json.loads(path.read_text(encoding="utf-8"))
        where = f"source[{source_index}]"
        if not isinstance(value, dict):
            raise ReviewError(f"{where} must be a JSON object")
        exact_fields(value, SOURCE_FIELDS, where)
        lens = value["lens"]
        if not isinstance(lens, str) or lens not in LENSES:
            raise ReviewError(f"{where}.lens must be an applicable review lens")
        if not isinstance(value["findings"], list):
            raise ReviewError(f"{where}.findings must be an array")
        findings.extend(
            validate_finding(item, f"{where}.findings[{index}]", lens)
            for index, item in enumerate(value["findings"])
        )
    return findings


def ranked(findings: list[dict]) -> list[dict]:
    return sorted(
        findings,
        key=lambda finding: (
            SEVERITY_RANK[finding["severity"]],
            finding["file"],
            finding["line"],
            finding["claim"],
            finding["lens"],
        ),
    )


def representative_rank(finding: dict) -> tuple[int, float, str, str]:
    return (
        SEVERITY_RANK[finding["severity"]],
        -finding["confidence"],
        finding["lens"],
        finding["failureScenario"],
    )


def deduplicate(findings: list[dict]) -> list[dict]:
    by_key: dict[tuple[str, int, str], dict] = {}
    for finding in findings:
        key = finding_key(finding)
        current = by_key.get(key)
        if current is None or representative_rank(finding) < representative_rank(current):
            by_key[key] = finding
    return ranked(list(by_key.values()))


def read_verifications(path: Path) -> dict[tuple[str, int, str], dict]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReviewError("verification must be a JSON object")
    exact_fields(value, {"verifications"}, "verification")
    if not isinstance(value["verifications"], list):
        raise ReviewError("verification.verifications must be an array")
    verified: dict[tuple[str, int, str], dict] = {}
    for index, item in enumerate(value["verifications"]):
        where = f"verification.verifications[{index}]"
        if not isinstance(item, dict):
            raise ReviewError(f"{where} must be an object")
        exact_fields(item, VERIFICATION_FIELDS, where)
        record = dict(item)
        record["file"] = repository_path(record["file"], f"{where}.file")
        record["line"] = positive_line(record["line"], f"{where}.line")
        record["claim"] = nonempty_string(record["claim"], f"{where}.claim")
        if not isinstance(record["substantiated"], bool):
            raise ReviewError(f"{where}.substantiated must be a boolean")
        record["refutationAttempt"] = nonempty_string(
            record["refutationAttempt"], f"{where}.refutationAttempt"
        )
        record["evidence"] = nonempty_string(record["evidence"], f"{where}.evidence")
        key = finding_key(record)
        if key in verified:
            raise ReviewError(f"duplicate adversarial verification for {key}")
        verified[key] = record
    return verified


def merge(candidates: list[dict], verifications: dict[tuple[str, int, str], dict]) -> list[dict]:
    candidate_keys = {finding_key(finding) for finding in candidates}
    missing = candidate_keys - verifications.keys()
    extra = verifications.keys() - candidate_keys
    if missing:
        raise ReviewError(f"missing adversarial verification for {sorted(missing)[0]}")
    if extra:
        raise ReviewError(f"adversarial verification has no candidate: {sorted(extra)[0]}")
    output = []
    for finding in candidates:
        verification = verifications[finding_key(finding)]
        if not verification["substantiated"]:
            continue
        merged = dict(finding)
        merged["verification"] = {
            "refutationAttempt": verification["refutationAttempt"],
            "evidence": verification["evidence"],
        }
        output.append(merged)
    return ranked(output)


def verdict(findings: list[dict]) -> str:
    if any(finding["severity"] in {"critical", "high"} for finding in findings):
        return "block"
    if findings:
        return "approve-with-nits"
    return "approve"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dedupe-only", action="store_true")
    mode.add_argument("--verification", type=Path)
    parser.add_argument("findings", type=Path, nargs="+")
    args = parser.parse_args()
    try:
        source_findings = read_sources(args.findings)
        candidates = deduplicate(source_findings)
        if args.dedupe_only:
            output = {
                "inputCount": len(source_findings),
                "candidateCount": len(candidates),
                "candidates": candidates,
            }
        else:
            final_findings = merge(candidates, read_verifications(args.verification))
            output = {
                "inputCount": len(source_findings),
                "candidateCount": len(candidates),
                "verifiedCount": len(final_findings),
                "droppedCount": len(candidates) - len(final_findings),
                "findings": final_findings,
                "verdict": verdict(final_findings),
            }
        print(json.dumps(output, indent=2, sort_keys=False))
    except (OSError, json.JSONDecodeError, ReviewError) as error:
        print(f"code review merge error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
