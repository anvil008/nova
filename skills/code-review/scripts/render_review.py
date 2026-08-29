#!/usr/bin/env python3
"""Render a merged code-review result as a self-contained HTML report."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP_FIELDS = {
    "inputCount", "candidateCount", "verifiedCount", "droppedCount",
    "findings", "dropped", "verdict",
}
FINDING_FIELDS = {
    "file", "line", "severity", "lens", "claim",
    "failureScenario", "confidence", "verification",
}
VERIFICATION_FIELDS = {"refutationAttempt", "evidence"}
SEVERITIES = ("critical", "high", "medium", "low", "nit")
LENSES = ("correctness", "security", "performance", "tests", "api-contract", "frontend")
VERDICTS = {
    "block": ("verdict-block", "Block — resolve the blocking findings before merge"),
    "approve-with-nits": ("verdict-nits", "Approve with nits — nothing blocks merge"),
    "approve": ("verdict-approve", "Approve — no findings survived verification"),
}
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class ReviewError(ValueError):
    pass


def require_exact_fields(value: dict, expected: set[str], where: str) -> None:
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


def validate_finding(value: object, where: str) -> dict:
    if not isinstance(value, dict):
        raise ReviewError(f"{where} must be an object")
    require_exact_fields(value, FINDING_FIELDS, where)
    nonempty_string(value["file"], f"{where}.file")
    nonempty_string(value["claim"], f"{where}.claim")
    nonempty_string(value["failureScenario"], f"{where}.failureScenario")
    if not isinstance(value["line"], int) or isinstance(value["line"], bool) or value["line"] < 1:
        raise ReviewError(f"{where}.line must be a positive integer")
    if value["severity"] not in SEVERITIES:
        raise ReviewError(f"{where}.severity must be one of: {', '.join(SEVERITIES)}")
    if value["lens"] not in LENSES:
        raise ReviewError(f"{where}.lens must be one of: {', '.join(LENSES)}")
    confidence = value["confidence"]
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not 0 <= confidence <= 1
    ):
        raise ReviewError(f"{where}.confidence must be a number between 0 and 1")
    verification = value["verification"]
    if not isinstance(verification, dict):
        raise ReviewError(f"{where}.verification must be an object")
    require_exact_fields(verification, VERIFICATION_FIELDS, f"{where}.verification")
    nonempty_string(verification["refutationAttempt"], f"{where}.verification.refutationAttempt")
    nonempty_string(verification["evidence"], f"{where}.verification.evidence")
    return value


def validate_review(review: object) -> dict:
    if not isinstance(review, dict):
        raise ReviewError("review must be a JSON object")
    require_exact_fields(review, TOP_FIELDS, "review")
    for field in ("inputCount", "candidateCount", "verifiedCount", "droppedCount"):
        count = review[field]
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ReviewError(f"{field} must be a non-negative integer")
    if review["verdict"] not in VERDICTS:
        raise ReviewError(f"verdict must be one of: {', '.join(sorted(VERDICTS))}")
    for field in ("findings", "dropped"):
        if not isinstance(review[field], list):
            raise ReviewError(f"{field} must be an array")
        for index, finding in enumerate(review[field]):
            validate_finding(finding, f"{field}[{index}]")
    if len(review["findings"]) != review["verifiedCount"]:
        raise ReviewError("verifiedCount does not match findings length")
    if len(review["dropped"]) != review["droppedCount"]:
        raise ReviewError("droppedCount does not match dropped length")
    return review


def escaped(value: object) -> str:
    return html.escape(str(value), quote=True)


def identifier(index: int, prefix: str = "F") -> str:
    return f"{prefix}-{index + 1:02d}"


CONFIDENCE_BANDS = ((0.95, 4, "high"), (0.85, 3, "moderate"), (0.70, 2, "low"), (0.0, 1, "weak"))


def confidence_band(confidence: float) -> tuple[int, str]:
    """Bars and label come from one band table so they can never disagree."""
    for threshold, bars, label in CONFIDENCE_BANDS:
        if confidence >= threshold:
            return bars, label
    return 1, "weak"


def meter_html(confidence: float) -> str:
    filled, _ = confidence_band(confidence)
    return "".join(f'<i class="{"on" if slot < filled else ""}"></i>' for slot in range(4))


def confidence_label(confidence: float) -> str:
    return confidence_band(confidence)[1]


def metrics_html(review: dict) -> str:
    dropped = review["droppedCount"]
    blocking = sum(1 for f in review["findings"] if f["severity"] in {"critical", "high"})
    cells = [
        ("Raw lens findings", review["inputCount"], "before dedupe", ""),
        ("Candidates", review["candidateCount"], "after dedupe", ""),
        ("Verified", review["verifiedCount"], f"{blocking} blocking", "critical" if blocking else "ok"),
        ("Refuted", dropped, "could not be substantiated", ""),
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


def topology_html(review: dict, declared_lenses: list[str]) -> str:
    """Render the review pipeline from validated counts and context only."""
    lenses = sorted(
        {finding["lens"] for finding in review["findings"] + review["dropped"]}
        | set(declared_lenses),
        key=LENSES.index,
    )
    lens_label = ", ".join(lenses) if lenses else "none recorded"
    verdict_label = review["verdict"].replace("-", " ")
    stages = (
        ("Lenses", len(lenses), lens_label),
        ("Observations", review["inputCount"], "raw reviewer output"),
        ("Candidates", review["candidateCount"], "after deterministic dedupe"),
        ("Verified", review["verifiedCount"], "survived refutation"),
    )
    nodes = []
    for label, count, detail in stages:
        nodes.append(
            '<div class="topology-node">'
            f'<span class="topology-value">{escaped(count)}</span>'
            f'<strong>{escaped(label)}</strong><small>{escaped(detail)}</small></div>'
        )
    nodes.append(
        '<div class="topology-node topology-outcome">'
        f'<span class="topology-value">{escaped(verdict_label)}</span>'
        f'<strong>Verdict</strong><small>{escaped(review["droppedCount"])} refuted</small></div>'
    )
    verified_verb = "was" if review["verifiedCount"] == 1 else "were"
    dropped_verb = "was" if review["droppedCount"] == 1 else "were"
    accessible = (
        f'{len(lenses)} selected lenses produced {review["inputCount"]} observations; '
        f'{review["candidateCount"]} candidates remained after deduplication; '
        f'{review["verifiedCount"]} {verified_verb} verified and '
        f'{review["droppedCount"]} {dropped_verb} refuted. '
        f'The verdict is {verdict_label}.'
    )
    return (
        '<figure class="review-visual topology" aria-labelledby="topology-title" '
        'aria-describedby="topology-description">'
        '<figcaption id="topology-title">Review topology</figcaption>'
        f'<p id="topology-description" class="visual-description">{escaped(accessible)}</p>'
        f'<div class="topology-track">{"".join(nodes)}</div></figure>'
    )


def impact_html(findings: list[dict]) -> str:
    """Render verified impact by file and severity, including the zero state."""
    grouped: dict[str, dict[str, int]] = {}
    for finding in findings:
        counts = grouped.setdefault(finding["file"], {severity: 0 for severity in SEVERITIES})
        counts[finding["severity"]] += 1
    if not grouped:
        rows = (
            '<div class="impact-zero"><span aria-hidden="true">&#10003;</span>'
            '<strong>No verified impact</strong><small>No file carries a finding that survived refutation.</small></div>'
        )
        description = "No files carry verified findings."
    else:
        rows_list = []
        descriptions = []
        for path in sorted(grouped):
            counts = grouped[path]
            total = sum(counts.values())
            marks = []
            readable = []
            for severity in SEVERITIES:
                count = counts[severity]
                if count:
                    marks.append(
                        f'<span class="impact-mark bar-{escaped(severity)}">'
                        f'<b>{escaped(count)}</b><small>{escaped(severity)}</small></span>'
                    )
                    readable.append(f"{count} {severity}")
            descriptions.append(f'{path}: {", ".join(readable)}')
            rows_list.append(
                '<div class="impact-row">'
                f'<span class="impact-path">{escaped(path)}</span>'
                f'<span class="impact-total">{escaped(total)} total</span>'
                f'<span class="impact-marks">{"".join(marks)}</span></div>'
            )
        rows = "".join(rows_list)
        description = "Verified findings by file and severity. " + "; ".join(descriptions) + "."
    return (
        '<figure class="review-visual impact-map" aria-labelledby="impact-title" '
        'aria-describedby="impact-description">'
        '<figcaption id="impact-title">Verified impact map</figcaption>'
        f'<p id="impact-description" class="visual-description">{escaped(description)}</p>'
        f'<div class="impact-grid">{rows}</div></figure>'
    )


def filters_html(findings: list[dict], group: str, order: tuple[str, ...]) -> str:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding[group]] = counts.get(finding[group], 0) + 1
    buttons = []
    for value in order:
        if value not in counts:
            continue
        dot = f' <span class="dot bar-{value}"></span>' if group == "severity" else ""
        buttons.append(
            f'<button type="button" class="filter" aria-pressed="true" data-value="{escaped(value)}">'
            f'{dot}{escaped(value)} <span class="n">{counts[value]}</span></button>'
        )
    return "".join(buttons)


def finding_rows(findings: list[dict], prefix: str, refuted: bool) -> str:
    if not findings:
        message = (
            "No candidate was refuted; every candidate survived verification."
            if refuted
            else "No findings survived verification."
        )
        return f'<div class="empty">{message}</div>'
    rows = []
    for index, finding in enumerate(findings):
        severity = finding["severity"]
        proof_class = "refuted" if refuted else "proof"
        proof_label = "Why it was dropped" if refuted else "Refutation attempt"
        rows.append(
            f'<details class="row" data-severity="{escaped(severity)}" data-lens="{escaped(finding["lens"])}">'
            "<summary>"
            f'<span class="stripe bar-{escaped(severity)}"></span>'
            '<div class="row-body">'
            '<div class="row-title">'
            f'<span class="sev sev-{escaped(severity)}">{escaped(severity)}</span>'
            f'<span class="finding-id">{escaped(identifier(index, prefix))}</span>'
            f'<strong>{escaped(finding["claim"])}</strong></div>'
            '<div class="row-meta">'
            f'<span class="loc">{escaped(finding["file"])}:{escaped(finding["line"])}</span>'
            f'<span class="lens">{escaped(finding["lens"])}</span>'
            '<span class="confidence">'
            f'<span class="meter">{meter_html(finding["confidence"])}</span>'
            f'<span class="v">{escaped(f"{finding['confidence']:.2f}")}</span></span>'
            "</div></div>"
            '<span class="caret">&#9662;</span></summary>'
            '<div class="row-detail">'
            '<div class="block impact"><div class="k">Failure scenario</div>'
            f'<p>{escaped(finding["failureScenario"])}</p></div>'
            f'<div class="block {proof_class}"><div class="k">{proof_label}</div>'
            f'<p>{escaped(finding["verification"]["refutationAttempt"])}</p></div>'
            f'<div class="block {proof_class}"><div class="k">Evidence</div>'
            f'<p>{escaped(finding["verification"]["evidence"])}</p></div>'
            "</div></details>"
        )
    return "".join(rows)


def files_html(findings: list[dict]) -> str:
    grouped: dict[str, list[str]] = {}
    for finding in findings:
        grouped.setdefault(finding["file"], []).append(finding["severity"])
    if not grouped:
        return '<div class="empty">No file carries a verified finding.</div>'
    rows = []
    for path in sorted(grouped):
        severities = sorted(grouped[path], key=SEVERITIES.index)
        marks = "".join(f'<span class="mark bar-{escaped(s)}" title="{escaped(s)}"></span>' for s in severities)
        rows.append(
            f'<div class="file-row"><span class="path">{escaped(path)}</span>'
            f'<span class="marks">{marks}</span></div>'
        )
    return f'<div class="files">{"".join(rows)}</div>'


def lens_chips(findings: list[dict], declared: list[str]) -> tuple[str, int]:
    used = sorted({finding["lens"] for finding in findings} | set(declared), key=lambda l: LENSES.index(l))
    if not used:
        return '<span class="tag">none recorded</span>', 0
    return "".join(f'<span class="tag">{escaped(lens)}</span>' for lens in used), len(used)


def render(review: dict, context: dict) -> str:
    templates = ROOT / "templates"
    template = (templates / "review.html.tmpl").read_text(encoding="utf-8")
    css = (
        (templates / "report.css").read_text(encoding="utf-8")
        + "\n"
        + (templates / "review.css").read_text(encoding="utf-8")
    )
    findings = review["findings"]
    verdict_class, verdict_text = VERDICTS[review["verdict"]]
    weakest = min((f["confidence"] for f in findings), default=1.0)
    chips, lens_count = lens_chips(findings, context["lenses"])
    generated = datetime.fromisoformat(context["generatedAt"].replace("Z", "+00:00"))
    lede = (
        f"{review['verifiedCount']} verified finding(s) from {review['inputCount']} raw lens "
        f"observation(s). {review['droppedCount']} candidate(s) did not survive independent "
        "refutation and are listed separately."
    )
    replacements = {
        "DOCUMENT_TITLE": escaped(f"{context['title']} · Foundry Zero Code Review"),
        "INLINE_CSS": css,
        "TITLE": escaped(context["title"]),
        "LEDE": escaped(lede),
        "REPO": escaped(context["repo"]),
        "SUBJECT": escaped(context["subject"]),
        "BASE": escaped(context["base"]),
        "GENERATED_AT": escaped(context["generatedAt"]),
        "DISPLAY_DATE": escaped(generated.strftime("%B %d, %Y")),
        "VERDICT_CLASS": verdict_class,
        "VERDICT_TEXT": escaped(verdict_text),
        "CONFIDENCE_METER": f'<span class="meter">{meter_html(weakest)}</span>',
        "CONFIDENCE_LABEL": escaped(confidence_label(weakest) if findings else "n/a"),
        "VERIFIED_COUNT": escaped(review["verifiedCount"]),
        "DROPPED_COUNT": escaped(review["droppedCount"]),
        "FILE_COUNT": escaped(len({finding["file"] for finding in findings})),
        "LENS_COUNT": escaped(lens_count),
        "LENSES": chips,
        "METRICS": metrics_html(review),
        "TOPOLOGY": topology_html(review, context["lenses"]),
        "IMPACT_MAP": impact_html(findings),
        "SEVERITY_FILTERS": filters_html(findings, "severity", SEVERITIES),
        "LENS_FILTERS": filters_html(findings, "lens", LENSES),
        "FINDINGS": finding_rows(findings, "F", refuted=False),
        "DROPPED": f'<div class="rows dropped">{finding_rows(review["dropped"], "D", refuted=True)}</div>',
        "FILES": files_html(findings),
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
        raise ReviewError(f"unresolved template token(s): {', '.join(sorted(set(leftovers)))}")
    return rendered


def build_context(args: argparse.Namespace) -> dict:
    repo = args.repo.strip()
    if repo != "—" and not REPOSITORY.fullmatch(repo):
        raise ReviewError("--repo must be owner/name")
    lenses = [lens.strip() for lens in args.lenses.split(",") if lens.strip()] if args.lenses else []
    for lens in lenses:
        if lens not in LENSES:
            raise ReviewError(f"--lenses entry must be one of: {', '.join(LENSES)}")
    generated_at = args.generated_at or datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReviewError("--generated-at must be ISO8601") from error
    return {
        "title": args.title.strip() or "Code review",
        "repo": repo,
        "subject": args.subject.strip(),
        "base": args.base.strip(),
        "lenses": lenses,
        "generatedAt": generated_at,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path, help="merged output of merge_findings.py --verification")
    parser.add_argument("output", type=Path)
    parser.add_argument("--title", default="Code review")
    parser.add_argument("--repo", default="—", help="owner/name")
    parser.add_argument("--subject", default="working tree", help="pull request, branch, or diff range")
    parser.add_argument("--base", default="—", help="base commit or ref")
    parser.add_argument("--lenses", default="", help="comma-separated lenses actually selected")
    parser.add_argument("--generated-at", default="", help="ISO8601; defaults to now")
    args = parser.parse_args()
    try:
        context = build_context(args)
        review = validate_review(json.loads(args.review.read_text(encoding="utf-8")))
        rendered = render(review, context)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    except (OSError, json.JSONDecodeError, ReviewError) as error:
        print(f"code review render error: {error}", file=sys.stderr)
        return 1
    print(f"rendered {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
