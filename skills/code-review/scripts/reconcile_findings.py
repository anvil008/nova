#!/usr/bin/env python3
"""Preview or apply idempotent GitHub issue reconciliation for verified review findings."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from render_review import SEVERITIES, ReviewError, validate_review


FINDING_MARKER = "<!-- swarm-review reviewId={review_id} finding={key} severity={severity} -->"
FINDING_MARKER_RE = re.compile(
    r"<!--\s*swarm-review\s+"
    r"reviewId=([a-z0-9]+(?:-[a-z0-9]+)*)\s+"
    r"finding=([0-9a-f]{12})"
    r"(?:\s+severity=([a-z]+))?\s*-->"
)
SEVERITY_LABEL_RE = re.compile(r"^severity:([a-z]+)$")
REVIEW_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SEVERITY_RANK = {severity: rank for rank, severity in enumerate(SEVERITIES)}


class ReconcileError(ReviewError):
    pass


def finding_key(finding: dict) -> str:
    """Identity is (file, claim) — deliberately not line.

    A line number moves whenever anything above it changes, so keying on it
    would file a fresh duplicate issue for the same defect after any unrelated
    edit, and would strand the original as never-fixed. The claim is what the
    finding *is*; the line is where it happened to sit at review time and lives
    in the body instead.
    """
    digest = hashlib.sha256(f"{finding['file']}\0{finding['claim']}".encode("utf-8"))
    return digest.hexdigest()[:12]


def gh_json(args: list[str], *, payload: dict | None = None, timeout: float = 30) -> object:
    command = ["gh", "api", *args]
    try:
        result = subprocess.run(
            command,
            input=json.dumps(payload) if payload is not None else None,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise ReconcileError(
            f"GitHub API call timed out after {timeout} seconds: {' '.join(command)}"
        ) from error
    if result.returncode:
        raise ReviewError(f"{' '.join(command)} failed: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ReviewError(f"{' '.join(command)} returned invalid JSON") from error


def flatten_pages(value: object) -> list[dict]:
    if not isinstance(value, list):
        raise ReviewError("GitHub API response must be an array")
    if value and all(isinstance(page, list) for page in value):
        return [item for page in value for item in page if isinstance(item, dict)]
    return [item for item in value if isinstance(item, dict)]


def read_state(repo: str) -> dict:
    issues = gh_json([
        "--method", "GET", "--paginate", "--slurp",
        f"repos/{repo}/issues?state=all&per_page=100",
    ])
    return {"issues": flatten_pages(issues)}


def reportable(review: dict, min_severity: str) -> list[dict]:
    ceiling = SEVERITY_RANK[min_severity]
    return [f for f in review["findings"] if SEVERITY_RANK[f["severity"]] <= ceiling]


def issue_body(finding: dict, key: str, review_id: str, subject: str) -> str:
    verification = finding["verification"]
    lines = [
        f"**{finding['file']}:{finding['line']}** · `{finding['lens']}` lens · "
        f"severity `{finding['severity']}` · confidence {finding['confidence']:.2f}",
        "",
        "## Failure scenario",
        "",
        finding["failureScenario"],
        "",
        "## Independent verification",
        "",
        f"- **Refutation attempt** — {verification['refutationAttempt']}",
        f"- **Evidence** — {verification['evidence']}",
        "",
        f"Raised by the `{finding['lens']}` lens reviewing {subject} and substantiated by an "
        "independent verifier that tried to refute it.",
        "",
        FINDING_MARKER.format(review_id=review_id, key=key, severity=finding["severity"]),
    ]
    return "\n".join(lines)


def desired_issue(
    finding: dict, key: str, review_id: str, subject: str,
    extra_labels: list[str], milestone: int | None,
) -> dict:
    labels = sorted({
        "code-review",
        f"severity:{finding['severity']}",
        f"lens:{finding['lens']}",
        *extra_labels,
    })
    return {
        "title": f"[{finding['severity']}] {finding['claim']}",
        "body": issue_body(finding, key, review_id, subject),
        "labels": labels,
        "milestone": milestone,
        "state": "open",
    }


def existing_marker(issue: dict) -> tuple[str, str] | None:
    match = FINDING_MARKER_RE.search(issue.get("body") or "")
    return (match.group(1), match.group(2)) if match else None


def label_names(issue: dict) -> list[str]:
    return [
        label.get("name", "") if isinstance(label, dict) else str(label)
        for label in issue.get("labels", [])
    ]


def recorded_severity(issue: dict) -> str | None:
    """Severity the issue was filed at: the marker first, then the severity label."""
    match = FINDING_MARKER_RE.search(issue.get("body") or "")
    if match and match.group(3) in SEVERITY_RANK:
        return match.group(3)
    for name in label_names(issue):
        label = SEVERITY_LABEL_RE.match(name)
        if label and label.group(1) in SEVERITY_RANK:
            return label.group(1)
    return None


def closable(issue: dict, min_severity: str) -> bool:
    """Only findings this run could have reported may be declared resolved.

    A stricter --min-severity than the one an issue was filed at means the
    finding was filtered out, not fixed, so the issue stays open. An issue with
    no recorded severity is left alone for the same reason.
    """
    severity = recorded_severity(issue)
    return severity is not None and SEVERITY_RANK[severity] <= SEVERITY_RANK[min_severity]


def issue_differs(existing: dict, desired: dict) -> bool:
    milestone = existing.get("milestone") or {}
    return any((
        existing.get("title") != desired["title"],
        (existing.get("body") or "") != desired["body"],
        sorted(label_names(existing)) != sorted(desired["labels"]),
        milestone.get("number") != desired["milestone"],
        existing.get("state") != "open",
    ))


def review_actions(
    review: dict, state: dict, review_id: str, subject: str,
    min_severity: str, extra_labels: list[str], milestone: int | None,
) -> list[dict]:
    issues = [issue for issue in state.get("issues", []) if "pull_request" not in issue]
    if not isinstance(issues, list):
        raise ReviewError("snapshot issues must be an array")

    marked: dict[str, list[dict]] = {}
    for existing in issues:
        marker = existing_marker(existing)
        if marker and marker[0] == review_id:
            marked.setdefault(marker[1], []).append(existing)
    for entries in marked.values():
        entries.sort(key=lambda item: item.get("number", 0))

    actions: list[dict] = []
    desired_keys: set[str] = set()
    for finding in reportable(review, min_severity):
        key = finding_key(finding)
        desired_keys.add(key)
        desired = desired_issue(finding, key, review_id, subject, extra_labels, milestone)
        matches = marked.get(key, [])
        if not matches:
            actions.append({"action": "create_issue", "key": key, "payload": desired})
            continue
        canonical = matches[0]
        if issue_differs(canonical, desired):
            actions.append({
                "action": "update_issue", "key": key,
                "number": canonical["number"], "payload": desired,
            })
        for duplicate in matches[1:]:
            if duplicate.get("state") != "closed":
                actions.append({
                    "action": "close_duplicate_issue", "key": key,
                    "number": duplicate["number"], "payload": {"state": "closed"},
                })

    # A finding this review no longer reports has been fixed (or refuted on a
    # re-run), so its issue closes. This is what makes re-reviewing after a fix
    # converge instead of accumulating stale issues.
    for key, matches in sorted(marked.items()):
        if key in desired_keys:
            continue
        for removed in matches:
            if removed.get("state") != "closed" and closable(removed, min_severity):
                actions.append({
                    "action": "close_resolved_issue", "key": key,
                    "number": removed["number"], "payload": {"state": "closed"},
                })
    return actions


def apply_actions(repo: str, actions: list[dict]) -> list[dict]:
    receipts = []
    for action in actions:
        payload = action["payload"]
        if action["action"] == "create_issue":
            response = gh_json(
                ["--method", "POST", f"repos/{repo}/issues", "--input", "-"], payload=payload
            )
        else:
            response = gh_json(
                ["--method", "PATCH", f"repos/{repo}/issues/{action['number']}", "--input", "-"],
                payload=payload,
            )
        receipts.append({
            "action": action["action"],
            "key": action["key"],
            "number": response.get("number") if isinstance(response, dict) else None,
        })
    return receipts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path, help="merged output of merge_findings.py --verification")
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--review-id", required=True, help="stable lowercase slug identifying this review")
    parser.add_argument("--subject", default="this change-set", help="what was reviewed, e.g. 'PR #4821'")
    parser.add_argument(
        "--min-severity", default="medium", choices=SEVERITIES,
        help="file issues at this severity and above (default: medium)",
    )
    parser.add_argument("--label", action="append", default=[], help="extra label; repeatable")
    parser.add_argument("--milestone", type=int, help="attach issues to this milestone number")
    parser.add_argument("--snapshot", type=Path, help="use captured GitHub JSON instead of any network call")
    parser.add_argument("--apply", action="store_true", help="perform writes after explicit human approval")
    parser.add_argument("--approved-by", help="identity of the human who approved this exact review")
    args = parser.parse_args()
    if args.snapshot and args.apply:
        parser.error("--snapshot cannot be combined with --apply")
    if args.apply and not args.approved_by:
        parser.error("--apply requires --approved-by with the approving human identity")
    if args.approved_by and not args.apply:
        parser.error("--approved-by is only valid with --apply")
    try:
        if not REVIEW_ID.fullmatch(args.review_id):
            raise ReviewError("--review-id must be a stable lowercase slug")
        if not REPOSITORY.fullmatch(args.repo):
            raise ReviewError("--repo must be owner/name")
        review = validate_review(json.loads(args.review.read_text(encoding="utf-8")))
        state = (
            json.loads(args.snapshot.read_text(encoding="utf-8"))
            if args.snapshot
            else read_state(args.repo)
        )
        actions = review_actions(
            review, state, args.review_id, args.subject,
            args.min_severity, args.label, args.milestone,
        )
        output = {
            "reviewId": args.review_id,
            "repo": args.repo,
            "minSeverity": args.min_severity,
            "mode": "apply" if args.apply else "preview",
            "actions": actions,
        }
        if args.apply:
            output["approvedBy"] = args.approved_by
            output["receipts"] = apply_actions(args.repo, actions)
        print(json.dumps(output, indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, ReviewError) as error:
        print(f"code review reconcile error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
