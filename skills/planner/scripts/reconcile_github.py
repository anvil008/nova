#!/usr/bin/env python3
"""Preview or apply idempotent GitHub milestone and issue reconciliation."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from render_plan import PlanError, validate_plan

PLAN_MARKER = "<!-- swarm-planner planId={plan_id} -->"
ISSUE_MARKER = "<!-- swarm-planner planId={plan_id} issue={key} -->"
ISSUE_MARKER_RE = re.compile(
    r"<!--\s*swarm-planner\s+"
    r"planId=([a-z0-9]+(?:-[a-z0-9]+)*)\s+"
    r"issue=([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)\s*-->"
)


class ReconcileError(PlanError):
    pass


def gh_json(args: list[str], *, payload: dict | None = None, timeout: float = 30) -> object:
    command = ["gh", "api", *args]
    try:
        result = subprocess.run(
            command,
            input=json.dumps(payload) if payload is not None else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ReconcileError(f"GitHub API call timed out after {timeout} seconds: {' '.join(command)}") from error
    if result.returncode:
        raise PlanError(f"{' '.join(command)} failed: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise PlanError(f"{' '.join(command)} returned invalid JSON") from error


def flatten_pages(value: object) -> list[dict]:
    if not isinstance(value, list):
        raise PlanError("GitHub API response must be an array")
    if value and all(isinstance(page, list) for page in value):
        return [item for page in value for item in page if isinstance(item, dict)]
    return [item for item in value if isinstance(item, dict)]


def read_state(repo: str) -> dict:
    milestones = gh_json([
        "--method", "GET", "--paginate", "--slurp",
        f"repos/{repo}/milestones?state=all&per_page=100",
    ])
    issues = gh_json([
        "--method", "GET", "--paginate", "--slurp",
        f"repos/{repo}/issues?state=all&per_page=100",
    ])
    return {"milestones": flatten_pages(milestones), "issues": flatten_pages(issues)}


def dod_block(issue: dict) -> str:
    lines = ["## Definition of Done (tests)", ""]
    for spec in issue["acceptanceTests"]:
        head = f"- [ ] **{spec['name']}** ({spec['kind']}) - {spec['oracle']}"
        if spec.get("testPath"):
            head += f" (test: `{spec['testPath']}`)"
        lines.append(head)
        if spec.get("stub"):
            lines.append("")
            lines.append("  ```")
            lines.extend("  " + line for line in spec["stub"].splitlines())
            lines.append("  ```")
    return "\n".join(lines)


def desired_issue(plan: dict, issue: dict, milestone_number: int | str) -> dict:
    marker = ISSUE_MARKER.format(plan_id=plan["planId"], key=issue["key"])
    return {
        "title": issue["title"],
        "body": issue["body"].rstrip() + "\n\n" + dod_block(issue) + "\n\n" + marker,
        "labels": issue["labels"],
        "milestone": milestone_number,
        "state": "open",
    }


def issue_marker(issue: dict) -> tuple[str, str] | None:
    match = ISSUE_MARKER_RE.search(issue.get("body") or "")
    return match.groups() if match else None


def label_names(issue: dict) -> list[str]:
    return [
        label.get("name", "") if isinstance(label, dict) else str(label)
        for label in issue.get("labels", [])
    ]


# The reconciler's own housekeeping closures carry this reason so they are never
# mistaken for finished work: GitHub defaults a bare close to "completed".
CLOSED = {"state": "closed", "state_reason": "not_planned"}


def is_done(issue: dict) -> bool:
    """Closed with status:done, or closed as completed (e.g. by a merged PR)."""
    return issue.get("state") == "closed" and (
        "status:done" in label_names(issue) or issue.get("state_reason") == "completed"
    )


def issue_differs(existing: dict, desired: dict) -> bool:
    milestone = existing.get("milestone") or {}
    return any((
        existing.get("title") != desired["title"],
        (existing.get("body") or "") != desired["body"],
        sorted(label_names(existing)) != sorted(desired["labels"]),
        milestone.get("number") != desired["milestone"],
        existing.get("state") != "open",
    ))


def milestone_description(existing: str | None, plan_marker: str) -> str:
    """Adopting a milestone by title keeps its hand-written description."""
    current = (existing or "").rstrip()
    if plan_marker in current:
        return current
    return f"{current}\n\n{plan_marker}" if current else plan_marker


def plan_actions(plan: dict, state: dict, reopen_done: bool = False) -> list[dict]:
    milestones = state.get("milestones", [])
    issues = [issue for issue in state.get("issues", []) if "pull_request" not in issue]
    if not isinstance(milestones, list) or not isinstance(issues, list):
        raise PlanError("snapshot milestones and issues must be arrays")

    plan_marker = PLAN_MARKER.format(plan_id=plan["planId"])
    matching_milestones = [m for m in milestones if plan_marker in (m.get("description") or "")]
    if not matching_milestones:
        matching_milestones = [m for m in milestones if m.get("title") == plan["planName"]]
    matching_milestones.sort(key=lambda item: item.get("number", 0))
    actions: list[dict] = []
    if matching_milestones:
        milestone = matching_milestones[0]
        milestone_number: int | str = milestone["number"]
        payload = {
            "title": plan["planName"],
            "description": milestone_description(milestone.get("description"), plan_marker),
            "state": "open",
        }
        if any((
            milestone.get("title") != payload["title"],
            milestone.get("description") != payload["description"],
            milestone.get("state") != "open",
        )):
            actions.append({"action": "update_milestone", "number": milestone_number, "payload": payload})
    else:
        milestone_number = "$MILESTONE_NUMBER"
        actions.append({
            "action": "create_milestone",
            "payload": {"title": plan["planName"], "description": plan_marker, "state": "open"},
        })

    marked: dict[str, list[dict]] = {}
    for existing in issues:
        marker = issue_marker(existing)
        if marker and marker[0] == plan["planId"]:
            marked.setdefault(marker[1], []).append(existing)
    for entries in marked.values():
        entries.sort(key=lambda item: item.get("number", 0))

    desired_keys = {issue["key"] for issue in plan["issues"]}
    for issue in plan["issues"]:
        key = issue["key"]
        desired = desired_issue(plan, issue, milestone_number)
        matches = marked.get(key, [])
        if not matches:
            actions.append({"action": "create_issue", "key": key, "payload": desired})
            continue
        canonical = matches[0]
        if issue_differs(canonical, desired) and (reopen_done or not is_done(canonical)):
            actions.append({
                "action": "update_issue", "key": key,
                "number": canonical["number"], "payload": desired,
            })
        for duplicate in matches[1:]:
            if duplicate.get("state") != "closed":
                actions.append({
                    "action": "close_duplicate_issue", "key": key,
                    "number": duplicate["number"], "payload": dict(CLOSED),
                })

    for key, matches in sorted(marked.items()):
        if key in desired_keys:
            continue
        for removed in matches:
            if removed.get("state") != "closed":
                actions.append({
                    "action": "close_removed_issue", "key": key,
                    "number": removed["number"], "payload": dict(CLOSED),
                })
    return actions


def apply_actions(repo: str, actions: list[dict]) -> list[dict]:
    milestone_number: int | None = None
    receipts = []
    for action in actions:
        name = action["action"]
        payload = dict(action["payload"])
        if payload.get("milestone") == "$MILESTONE_NUMBER":
            if milestone_number is None:
                raise PlanError("issue action appeared before milestone creation")
            payload["milestone"] = milestone_number
        if name == "create_milestone":
            response = gh_json(["--method", "POST", f"repos/{repo}/milestones", "--input", "-"], payload=payload)
            if not isinstance(response, dict) or not isinstance(response.get("number"), int):
                raise PlanError("milestone creation response did not include a number")
            milestone_number = response["number"]
        elif name == "update_milestone":
            response = gh_json(["--method", "PATCH", f"repos/{repo}/milestones/{action['number']}", "--input", "-"], payload=payload)
            milestone_number = action["number"]
        elif name == "create_issue":
            response = gh_json(["--method", "POST", f"repos/{repo}/issues", "--input", "-"], payload=payload)
        else:
            response = gh_json(["--method", "PATCH", f"repos/{repo}/issues/{action['number']}", "--input", "-"], payload=payload)
        receipts.append({"action": name, "number": response.get("number") if isinstance(response, dict) else None})
    return receipts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sidecar", type=Path)
    parser.add_argument("--snapshot", type=Path, help="use captured GitHub JSON instead of any network call")
    parser.add_argument("--apply", action="store_true", help="perform writes after explicit human approval")
    parser.add_argument("--approved-by", help="identity of the human who approved this exact sidecar")
    parser.add_argument(
        "--reopen-done", action="store_true",
        help="also reopen issues closed with status:done or as completed (default: leave them closed)",
    )
    args = parser.parse_args()
    if args.snapshot and args.apply:
        parser.error("--snapshot cannot be combined with --apply")
    if args.apply and not args.approved_by:
        parser.error("--apply requires --approved-by with the approving human identity")
    if args.approved_by and not args.apply:
        parser.error("--approved-by is only valid with --apply")
    try:
        plan = validate_plan(json.loads(args.sidecar.read_text(encoding="utf-8")))
        if args.snapshot:
            state = json.loads(args.snapshot.read_text(encoding="utf-8"))
        else:
            state = read_state(plan["repo"])
        actions = plan_actions(plan, state, reopen_done=args.reopen_done)
        output = {
            "planId": plan["planId"],
            "repo": plan["repo"],
            "mode": "apply" if args.apply else "preview",
            "actions": actions,
        }
        if args.apply:
            output["approvedBy"] = args.approved_by
            output["receipts"] = apply_actions(plan["repo"], actions)
        print(json.dumps(output, indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, PlanError, ReconcileError) as error:
        print(f"planner reconcile error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
