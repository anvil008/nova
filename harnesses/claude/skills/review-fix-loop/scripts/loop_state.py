#!/usr/bin/env python3
"""Track and bound a review-then-fix loop: record each pass, decide whether to continue."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
VERDICTS = {"block", "approve-with-nits", "approve"}
# Same enum and order as the code-review skill's merge_findings.py.
SEVERITIES = ("critical", "high", "medium", "low", "nit")
SEVERITY_RANK = {severity: rank for rank, severity in enumerate(SEVERITIES)}
STATE_FIELDS = {"branch", "maxIterations", "minSeverity", "iteration", "status", "history"}
# A pass that reports exactly what the previous pass reported means the fixer
# changed nothing that mattered. One repeat is enough to call it: a second
# identical pass would just burn another review for the same answer.
STALL_REPEATS = 2


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
    return state


def save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def do_init(args: argparse.Namespace) -> dict:
    if not BRANCH.fullmatch(args.branch):
        raise LoopError("--branch must be a plain branch name")
    if args.max_iterations < 1:
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
    }
    save(args.state, state)
    return state


def do_record(args: argparse.Namespace) -> dict:
    state = load(args.state)
    if state["status"] != "running":
        raise LoopError(f"loop already finished with status {state['status']}")
    verdict, findings = read_review(args.review)

    blockers = blocking(findings, state["minSeverity"])
    # Stall detection tracks the blocking set only: clearing a nit while the
    # same high finding stays put is not progress the loop should credit.
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
    elif repeats >= STALL_REPEATS:
        state["status"] = "stalled"
    elif state["iteration"] >= state["maxIterations"]:
        state["status"] = "exhausted"
    save(args.state, state)
    return state


def summary(state: dict) -> dict:
    latest = state["history"][-1] if state["history"] else None
    reasons = {
        "running": "continue — dispatch the builder to fix the reported findings",
        "converged": (
            f"stop — the review reported no findings at or above {state['minSeverity']}"
        ),
        "stalled": (
            "stop — two consecutive passes reported an identical finding set at or above "
            f"{state['minSeverity']}"
        ),
        "exhausted": f"stop — reached the {state['maxIterations']}-iteration bound",
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
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=Path(".workcell/review-fix-loop.json"))
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="start a loop")
    init.add_argument("--branch", default="loop-branch")
    init.add_argument("--max-iterations", type=int, default=10)
    init.add_argument(
        "--min-severity", default="high",
        help="lowest severity that blocks convergence; one of " + ", ".join(SEVERITIES),
    )
    init.add_argument("--force", action="store_true", help="restart an existing loop")

    record = sub.add_parser("record", help="record one review pass and decide what happens next")
    record.add_argument("review", type=Path, help="merged output of merge_findings.py --verification")

    sub.add_parser("status", help="show the current decision without changing anything")

    args = parser.parse_args()
    try:
        if args.command == "init":
            state = do_init(args)
        elif args.command == "record":
            state = do_record(args)
        else:
            state = load(args.state)
        print(json.dumps(summary(state), indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, LoopError) as error:
        print(f"review-fix-loop error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
