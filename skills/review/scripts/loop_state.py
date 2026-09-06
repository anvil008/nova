#!/usr/bin/env python3
"""Record review progress and orchestrator decisions, honoring explicit user limits."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
VERDICTS = {"block", "approve-with-nits", "approve"}
# Same enum and order as review's merge_findings.py.
SEVERITIES = ("critical", "high", "medium", "low", "nit")
SEVERITY_RANK = {severity: rank for rank, severity in enumerate(SEVERITIES)}
STATE_FIELDS = {"branch", "maxIterations", "minSeverity", "iteration", "status", "history"}
STATUSES = {"running", "converged", "stalled", "exhausted", "abandoned"}


class LoopError(ValueError):
    pass


def fingerprint(findings: list[dict]) -> str:
    """Identity of a finding *set*, order-independent.

    Keyed on (file, claim) — the same identity the review reconciler uses, and
    deliberately not the line, so a fix elsewhere in the file does not read as
    progress on a finding that is still there.
    """
    keys = sorted(
        hashlib.sha256(f"{f['file']}\0{f['claim']}".encode()).hexdigest()
        for f in findings
    )
    return hashlib.sha256("\n".join(keys).encode()).hexdigest()[:16]


def read_review(path: Path) -> tuple[str, list[dict]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise LoopError("review must be a JSON object")
    verdict = value.get("verdict")
    if verdict not in VERDICTS:
        raise LoopError(f"review.verdict must be one of: {', '.join(sorted(VERDICTS))}")
    findings = value.get("findings")
    if not isinstance(findings, list):
        raise LoopError("review.findings must be an array")
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise LoopError(f"review.findings[{index}] must be an object")
        for field in ("file", "claim", "severity"):
            if not isinstance(finding.get(field), str) or not finding[field].strip():
                raise LoopError(f"review.findings[{index}].{field} must be a non-empty string")
        if finding["severity"] not in SEVERITY_RANK:
            raise LoopError(
                f"review.findings[{index}].severity must be one of: {', '.join(SEVERITIES)}"
            )
    return verdict, findings


def blocking(findings: list[dict], min_severity: str) -> list[dict]:
    """Findings at or above the threshold; anything below is reported but never blocks."""
    threshold = SEVERITY_RANK[min_severity]
    return [f for f in findings if SEVERITY_RANK[f["severity"]] <= threshold]


def load(path: Path) -> dict:
    if not path.exists():
        raise LoopError(f"no loop state at {path} — run `init` first")
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise LoopError("loop state must be a JSON object")
    missing = STATE_FIELDS - state.keys()
    if missing:
        raise LoopError(f"loop state missing field(s): {', '.join(sorted(missing))}")
    if state["minSeverity"] not in SEVERITY_RANK:
        raise LoopError(f"loop state minSeverity must be one of: {', '.join(SEVERITIES)}")
    limit = state["maxIterations"]
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
        raise LoopError("loop state maxIterations must be a positive integer or null")
    if state["status"] not in STATUSES:
        raise LoopError("loop state status is invalid")
    return state


def save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def do_init(args: argparse.Namespace) -> dict:
    if not BRANCH.fullmatch(args.branch):
        raise LoopError("--branch must be a plain branch name")
    if args.max_iterations is not None and args.max_iterations < 1:
        raise LoopError("--max-iterations must be at least 1")
    if args.min_severity not in SEVERITY_RANK:
        raise LoopError(f"--min-severity must be one of: {', '.join(SEVERITIES)}")
    if args.state.exists() and not args.force:
        raise LoopError(f"loop state already exists at {args.state} — pass --force to restart")
    state = {
        "branch": args.branch,
        "maxIterations": args.max_iterations,
        "minSeverity": args.min_severity,
        "iteration": 0,
        "status": "running",
        "history": [],
        "decisions": [],
    }
    save(args.state, state)
    return state


def do_record(args: argparse.Namespace) -> dict:
    state = load(args.state)
    if state["status"] != "running":
        raise LoopError(f"loop already finished with status {state['status']}")
    verdict, findings = read_review(args.review)

    blockers = blocking(findings, state["minSeverity"])
    # Track the unresolved set without deciding whether another approach is useful.
    mark = fingerprint(blockers)
    state["iteration"] += 1
    state["history"].append({
        "iteration": state["iteration"],
        "verdict": verdict,
        "findings": len(findings),
        "blocking": len(blockers),
        "fingerprint": mark,
    })

    repeats = 1
    for entry in reversed(state["history"][:-1]):
        if entry["fingerprint"] != mark:
            break
        repeats += 1

    if not blockers:
        state["status"] = "converged"
    elif state["maxIterations"] is not None and state["iteration"] >= state["maxIterations"]:
        state["status"] = "exhausted"
    state["history"][-1]["repeatedCount"] = repeats
    save(args.state, state)
    return state


def do_decide(args: argparse.Namespace) -> dict:
    state = load(args.state)
    if not args.reason.strip():
        raise LoopError("a decision requires a non-empty --reason")
    if args.status == "running" and state["maxIterations"] is not None and state["iteration"] >= state["maxIterations"]:
        raise LoopError("cannot resume beyond the explicit iteration limit")
    if state["status"] in {"converged", "abandoned"}:
        raise LoopError(f"loop already finished with status {state['status']}")
    state.setdefault("decisions", []).append({
        "iteration": state["iteration"], "status": args.status, "reason": args.reason.strip(),
    })
    state["status"] = args.status
    save(args.state, state)
    return state


def summary(state: dict) -> dict:
    latest = state["history"][-1] if state["history"] else None
    reasons = {
        "running": "unresolved findings remain; the orchestrator chooses the next authorized action",
        "converged": (
            f"stop — the review reported no findings at or above {state['minSeverity']}"
        ),
        "stalled": "the orchestrator recorded stalled work; inspect the decision and evidence",
        "exhausted": f"stop — reached the explicit {state['maxIterations']}-iteration limit",
        "abandoned": "the orchestrator recorded abandonment; retain the evidence",
    }
    return {
        "branch": state["branch"],
        "iteration": state["iteration"],
        "maxIterations": state["maxIterations"],
        "minSeverity": state["minSeverity"],
        "status": state["status"],
        "continue": state["status"] == "running",
        "reason": reasons[state["status"]],
        "latest": latest,
        "progress": "unchanged" if latest and latest.get("repeatedCount", 1) > 1 else "changed" if latest else "unmeasured",
        "decision": state.get("decisions", [])[-1] if state.get("decisions") else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True, help="durable state path outside source workspaces")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="start a loop")
    init.add_argument("--branch", default="loop-branch")
    init.add_argument("--max-iterations", type=int, help="optional explicit user limit; no default cap")
    init.add_argument(
        "--min-severity", default="high",
        help="lowest severity that blocks convergence; one of " + ", ".join(SEVERITIES),
    )
    init.add_argument("--force", action="store_true", help="restart an existing loop")

    record = sub.add_parser("record", help="record one review pass and decide what happens next")
    record.add_argument("review", type=Path, help="merged output of merge_findings.py --verification")

    decide = sub.add_parser("decide", help="record the orchestrator's next-action decision")
    decide.add_argument("--status", choices=("running", "stalled", "abandoned"), required=True)
    decide.add_argument("--reason", required=True)

    sub.add_parser("status", help="show the current decision without changing anything")

    args = parser.parse_args()
    try:
        if args.command == "init":
            state = do_init(args)
        elif args.command == "record":
            state = do_record(args)
        elif args.command == "decide":
            state = do_decide(args)
        else:
            state = load(args.state)
        print(json.dumps(summary(state), indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, LoopError) as error:
        print(f"review progress error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
