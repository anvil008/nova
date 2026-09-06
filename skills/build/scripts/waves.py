#!/usr/bin/env python3
"""Derive dependency-ready build tasks from a sidecar and optional GitHub snapshot."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePath

import plan_sidecar

SNAPSHOT_FIELDS = {"repo", "milestone", "issues"}
STATE_ISSUE_FIELDS = {"number", "body", "labels", "state"}
# Optional: hand-written snapshots predate it, `gh` always supplies it.
STATE_ISSUE_OPTIONAL_FIELDS = frozenset({"state_reason"})
STATE_REASONS = frozenset({None, "completed", "not_planned", "reopened"})
MARKER = re.compile(
    r"<!--\s*workcell-planner\s+"
    r"planId=([a-z0-9]+(?:-[a-z0-9]+)*)\s+"
    r"issue=([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)\s*-->"
)


class BuildError(ValueError):
    pass


def exact_fields(value: dict, expected: set[str], where: str, optional: frozenset[str] = frozenset()) -> None:
    missing = expected - value.keys()
    unknown = value.keys() - expected - optional
    if missing:
        raise BuildError(f"{where}: missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise BuildError(f"{where}: unknown field(s): {', '.join(sorted(unknown))}")


def label_names(labels: object) -> list[str] | None:
    """gh's label shape, normalised: `gh api repos/{repo}/issues` and
    `gh issue list --json labels` both return label objects, while hand-written
    snapshots use strings. Mirrors label_names() in the sibling
    skills/plan/scripts/reconcile_github.py, duplicated because build ships
    self-contained. Returns None if any entry is neither shape."""
    if not isinstance(labels, list):
        return None
    names: list[str] = []
    for label in labels:
        name = label.get("name") if isinstance(label, dict) else label
        if not isinstance(name, str) or not name:
            return None
        names.append(name)
    return names


def issue_key(body: str, index: int, plan_id: str) -> str:
    match = MARKER.search(body)
    if not match:
        raise BuildError(f"snapshot.issues[{index}] must contain a durable planner marker")
    marker_plan, key = match.groups()
    if marker_plan != plan_id:
        raise BuildError(f"snapshot.issues[{index}] durable planner marker uses another planId")
    return key


def validate_snapshot(value: object, plan: dict) -> dict[str, dict]:
    if plan["repo"] is None:
        raise BuildError("a local-only plan has no GitHub snapshot; use --local")
    if not isinstance(value, dict):
        raise BuildError("snapshot must be a JSON object")
    exact_fields(value, SNAPSHOT_FIELDS, "snapshot")
    if value["repo"] != plan["repo"]:
        raise BuildError("snapshot.repo must match sidecar repo")
    if value["milestone"] != plan["planName"]:
        raise BuildError("snapshot.milestone must match sidecar planName")
    if not isinstance(value["issues"], list):
        raise BuildError("snapshot.issues must be an array")

    by_key: dict[str, dict] = {}
    for index, issue in enumerate(value["issues"]):
        if not isinstance(issue, dict):
            raise BuildError(f"snapshot.issues[{index}] must be an object")
        exact_fields(issue, STATE_ISSUE_FIELDS, f"snapshot.issues[{index}]", STATE_ISSUE_OPTIONAL_FIELDS)
        if not isinstance(issue["number"], int) or isinstance(issue["number"], bool) or issue["number"] < 1:
            raise BuildError(f"snapshot.issues[{index}].number must be a positive integer")
        if not isinstance(issue["body"], str):
            raise BuildError(f"snapshot.issues[{index}].body must be a string")
        if issue["state"] not in {"open", "closed"}:
            raise BuildError(f"snapshot.issues[{index}].state must be open or closed")
        if issue.get("state_reason") not in STATE_REASONS:
            reasons = ", ".join(sorted(reason for reason in STATE_REASONS if reason))
            raise BuildError(f"snapshot.issues[{index}].state_reason must be null or one of: {reasons}")
        names = label_names(issue["labels"])
        if names is None:
            raise BuildError(
                f"snapshot.issues[{index}].labels must be an array of non-empty strings "
                "or gh label objects carrying a non-empty name"
            )
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise BuildError(f"snapshot.issues[{index}].labels contains duplicates: {', '.join(duplicates)}")
        key = issue_key(issue["body"], index, plan["planId"])
        if key in by_key:
            raise BuildError(f"duplicate snapshot issue marker: {key}")
        by_key[key] = issue
    return by_key


def local_snapshot(plan: dict) -> dict[str, dict]:
    """Track real plan keys locally; only accepted receipts can complete them.

    External dependencies cannot be inferred locally. They need a GitHub state
    snapshot or a revised plan that explicitly includes the required work.
    """
    keys = {issue["key"] for issue in plan["issues"]}
    external = {dependency for issue in plan["issues"] for dependency in issue["dependsOn"]} - keys
    if external:
        raise BuildError(f"local tasks have unresolved external dependencies: {', '.join(sorted(external))}")
    return {key: {"number": None, "state": "open", "labels": []} for key in keys}


def validate_acyclic(plan: dict) -> None:
    dependencies = {issue["key"]: [key for key in issue["dependsOn"] if key in {item["key"] for item in plan["issues"]}] for issue in plan["issues"]}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visiting:
            raise BuildError(f"dependency cycle includes {key}")
        if key in visited:
            return
        visiting.add(key)
        for dependency in dependencies[key]:
            visit(dependency)
        visiting.remove(key)
        visited.add(key)

    for key in dependencies:
        visit(key)


def is_done(issue: dict) -> bool:
    """Closed with `status:done`, or closed as completed (e.g. by a merged PR).

    A `not_planned` closure is housekeeping — reconcile_github.py closes stale issues
    that way precisely so they are never mistaken for finished work — and an open
    issue is never done however it is labelled. Kept in step with
    skills/plan/scripts/reconcile_github.py:is_done."""
    return issue["state"] == "closed" and (
        # `or []` only satisfies the type checker: validate_snapshot has already rejected any
        # label shape label_names() cannot normalise, so None never reaches here.
        "status:done" in (label_names(issue["labels"]) or []) or issue.get("state_reason") == "completed"
    )


GLOB_CHARS = frozenset("*?[")


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """fnmatch-style translation mirroring PurePath.full_match: `*`/`?` stop at `/`,
    a whole `**` segment spans directories, and `**` inside a segment is just `*`."""
    out = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        segment_start = i == 0 or pattern[i - 1] == "/"
        if segment_start and pattern.startswith("**", i) and pattern[i + 2:i + 3] in ("", "/"):
            i += 2
            if i < len(pattern):
                out.append("(?:.*/)?")
                i += 1
            else:
                out.append(".*")
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            j = pattern.find("]", i + 1)
            if j == -1:
                out.append(re.escape(c))
                i += 1
            else:
                body = pattern[i + 1:j]
                negate = body.startswith("!")
                chars = re.sub(r"[\\\]\[^]", lambda m: "\\" + m.group(0), body[1:] if negate else body)
                # `[!]` and `[]` have no members; pathlib treats them literally.
                out.append(f"[{'^' if negate else ''}{chars}]" if chars else re.escape(pattern[i:j + 1]))
                i = j + 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("".join(out) + r"\Z")


def path_matches(path: str, pattern: str) -> bool:
    pure = PurePath(path)
    if hasattr(pure, "full_match"):  # Python 3.13+
        return pure.full_match(pattern)
    return _glob_to_regex(pattern).match(path) is not None


def globs_overlap(g1: str, g2: str) -> bool:
    """Prove disjointness, otherwise serialize. Sampling cannot prove it.

    Literal paths can be matched exactly. With two patterns, incompatible
    fixed prefixes or suffixes prove disjointness; uncertain intersections
    conservatively overlap, including character classes and recursive globs.
    """
    g1, g2 = str(PurePath(g1)), str(PurePath(g2))
    if not GLOB_CHARS.intersection(g1):
        return path_matches(g1, g2)
    if not GLOB_CHARS.intersection(g2):
        return path_matches(g2, g1)
    prefix1, prefix2 = (re.split(r"[*?\[]", g, maxsplit=1)[0] for g in (g1, g2))
    if not (prefix1.startswith(prefix2) or prefix2.startswith(prefix1)):
        return False
    suffix1, suffix2 = (re.split(r"[*?\[\]]", g)[-1] for g in (g1, g2))
    return suffix1.endswith(suffix2) or suffix2.endswith(suffix1)


def write_targets(issue: dict) -> list[str]:
    """Implementation ownership plus explicitly planned acceptance-test files."""
    return [issue["ownershipHint"]] + [
        test["testPath"] for test in issue.get("acceptanceTests", [])
        if test.get("testPath")
    ]


def ownership_collision(first: dict, second: dict) -> tuple[str, str] | None:
    return next(
        ((a, b) for a in write_targets(first) for b in write_targets(second)
         if globs_overlap(a, b)),
        None,
    )


def validate_ownership_overlap(plan: dict) -> None:
    """Overlapping ownership inside a grouped wave is a hard error — the planner asserted a
    parallelism the hints cannot deliver. Wave 0 is the ungrouped bucket, so an overlap there
    only warns; derive() then defers the second issue rather than dispatching the pair."""
    waves_dict: dict[int, list[dict]] = {}
    for issue in plan["issues"]:
        waves_dict.setdefault(issue["wave"], []).append(issue)
    for wave, issues in waves_dict.items():
        for i, issue1 in enumerate(issues):
            for issue2 in issues[i + 1:]:
                collision = ownership_collision(issue1, issue2)
                if collision is None:
                    continue
                h1, h2 = collision
                msg = (
                    f"Parallel issues '{issue1['key']}' and '{issue2['key']}' in wave {wave} "
                    f"have overlapping ownershipHint paths: '{h1}' and '{h2}'"
                )
                if wave == 0:
                    print(f"Warning: {msg}", file=sys.stderr)
                else:
                    raise BuildError(msg)


def derive(plan: dict, snapshot: dict[str, dict], integrated: frozenset[str] = frozenset()) -> dict:
    validate_acyclic(plan)
    validate_ownership_overlap(plan)
    planned = {issue["key"]: issue for issue in plan["issues"]}
    required = set(planned)
    required.update(dependency for issue in plan["issues"] for dependency in issue["dependsOn"])
    missing = sorted(required - snapshot.keys())
    if missing:
        raise BuildError(f"snapshot missing issue state for: {', '.join(missing)}")

    ordered_waves: dict[int, list[str]] = {}
    for issue in plan["issues"]:
        ordered_waves.setdefault(issue["wave"], []).append(issue["key"])
    waves = [{"wave": wave, "issues": keys} for wave, keys in sorted(ordered_waves.items())]
    unknown = integrated - planned.keys()
    if unknown:
        raise BuildError(f"integrated receipts name unknown issues: {sorted(unknown)}")
    done = [issue["key"] for issue in plan["issues"] if issue["key"] in integrated or is_done(snapshot[issue["key"]])]
    unfinished = [issue for issue in plan["issues"] if issue["key"] not in done]
    # Reporting only: the earliest declared wave still holding an unfinished issue. It is what
    # `pulledForward` is measured against, never a filter on selection.
    current_wave = min((issue["wave"] for issue in unfinished), default=None)
    # Dependency-gated: a candidate is any not-done issue whose dependencies are all done,
    # whatever wave declared it, so one straggler cannot freeze work that is already ready.
    # Ordered by declared wave first, so a deliberately coarse late hint (a whole-repository
    # documentation pass, say) defers itself rather than starving the issues it overlaps;
    # sorted() is stable, so sidecar order breaks ties inside a wave.
    ready = sorted(
        (issue for issue in unfinished if all(dep in integrated or is_done(snapshot[dep]) for dep in issue["dependsOn"])),
        key=lambda issue: issue["wave"],
    )
    unblocked: list[dict] = []
    deferred: list[dict] = []
    for issue in ready:
        entry = {
            "key": issue["key"],
            "number": snapshot[issue["key"]]["number"],
            "ownershipHint": issue["ownershipHint"],
            "wave": issue["wave"],
        }
        # Ownership is checked across the whole in-flight set, not per declared wave: an
        # overlapping candidate is deferred to a later round, never dispatched concurrently.
        clash = next(
            (chosen for chosen in unblocked
             if ownership_collision(planned[chosen["key"]], issue)),
            None,
        )
        if clash:
            deferred.append({**entry, "overlapsWith": clash["key"]})
        else:
            unblocked.append({**entry, "pulledForward": issue["wave"] > current_wave})
    return {
        "planId": plan["planId"],
        "planName": plan["planName"],
        "milestone": plan["planName"],
        "waves": waves,
        "currentWave": current_wave,
        "unblocked": unblocked,
        "deferred": deferred,
        "done": done,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sidecar", type=Path)
    parser.add_argument("snapshot", type=Path, nargs="?")
    parser.add_argument("--local", action="store_true", help="select local task keys without GitHub issues")
    args = parser.parse_args()
    try:
        plan = plan_sidecar.validate_plan(json.loads(args.sidecar.read_text(encoding="utf-8")))
        if args.local == bool(args.snapshot):
            raise BuildError("provide a snapshot or --local, exclusively")
        snapshot = local_snapshot(plan) if args.local else validate_snapshot(json.loads(args.snapshot.read_text(encoding="utf-8")), plan)
        print(json.dumps(derive(plan, snapshot), indent=2, sort_keys=False))
    except (OSError, json.JSONDecodeError, BuildError, ValueError) as error:
        print(f"build waves error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
