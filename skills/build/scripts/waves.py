#!/usr/bin/env python3
"""Derive deterministic build waves from a planner sidecar and issue snapshot."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLANNER_VALIDATOR = ROOT.parent / "planner" / "scripts" / "render_plan.py"
SNAPSHOT_FIELDS = {"repo", "milestone", "issues"}
STATE_ISSUE_FIELDS = {"number", "body", "labels", "state"}
MARKER = re.compile(
    r"<!--\s*swarm-planner\s+"
    r"planId=([a-z0-9]+(?:-[a-z0-9]+)*)\s+"
    r"issue=([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)\s*-->"
)


class BuildError(ValueError):
    pass


def planner_module():
    spec = importlib.util.spec_from_file_location("v3_planner_render", PLANNER_VALIDATOR)
    if spec is None or spec.loader is None:
        raise BuildError(f"cannot load planner validator: {PLANNER_VALIDATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exact_fields(value: dict, expected: set[str], where: str) -> None:
    missing = expected - value.keys()
    unknown = value.keys() - expected
    if missing:
        raise BuildError(f"{where}: missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise BuildError(f"{where}: unknown field(s): {', '.join(sorted(unknown))}")


def issue_key(body: str, index: int, plan_id: str) -> str:
    match = MARKER.search(body)
    if not match:
        raise BuildError(f"snapshot.issues[{index}] must contain a durable planner marker")
    marker_plan, key = match.groups()
    if marker_plan != plan_id:
        raise BuildError(f"snapshot.issues[{index}] durable planner marker uses another planId")
    return key


def validate_snapshot(value: object, plan: dict) -> dict[str, dict]:
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
        exact_fields(issue, STATE_ISSUE_FIELDS, f"snapshot.issues[{index}]")
        if not isinstance(issue["number"], int) or isinstance(issue["number"], bool) or issue["number"] < 1:
            raise BuildError(f"snapshot.issues[{index}].number must be a positive integer")
        if not isinstance(issue["body"], str):
            raise BuildError(f"snapshot.issues[{index}].body must be a string")
        if issue["state"] not in {"open", "closed"}:
            raise BuildError(f"snapshot.issues[{index}].state must be open or closed")
        labels = issue["labels"]
        if not isinstance(labels, list) or any(not isinstance(label, str) or not label for label in labels):
            raise BuildError(f"snapshot.issues[{index}].labels must be an array of non-empty strings")
        if len(labels) != len(set(labels)):
            raise BuildError(f"snapshot.issues[{index}].labels contains duplicates")
        key = issue_key(issue["body"], index, plan["planId"])
        if key in by_key:
            raise BuildError(f"duplicate snapshot issue marker: {key}")
        by_key[key] = issue
    return by_key


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
    return issue["state"] == "closed" or "status:done" in issue["labels"]


def generate_witnesses(glob_pattern: str) -> list[str]:
    parts = glob_pattern.split("/")
    results = []
    def builder(idx: int, current_path_parts: list[str]):
        if idx == len(parts):
            path_str = "/".join(p for p in current_path_parts if p)
            if path_str:
                results.append(path_str)
            else:
                results.append(".")
            return
        part = parts[idx]
        if part == "**":
            builder(idx + 1, current_path_parts)
            builder(idx + 1, current_path_parts + ["sub"])
            builder(idx + 1, current_path_parts + ["sub", "sub2"])
        else:
            p = part.replace("*", "file").replace("?", "a")
            p = re.sub(r"\[[^\]]+\]", "a", p)
            builder(idx + 1, current_path_parts + [p])
    builder(0, [])
    return list(set(results))


def globs_overlap(g1: str, g2: str) -> bool:
    from pathlib import PurePath
    for w in generate_witnesses(g1):
        if PurePath(w).match(g2):
            return True
    for w in generate_witnesses(g2):
        if PurePath(w).match(g1):
            return True
    return False


def validate_ownership_overlap(plan: dict) -> None:
    waves_dict = {}
    for issue in plan["issues"]:
        waves_dict.setdefault(issue["wave"], []).append(issue)
    for wave, issues in waves_dict.items():
        for i in range(len(issues)):
            for j in range(i + 1, len(issues)):
                issue1 = issues[i]
                issue2 = issues[j]
                h1 = issue1.get("ownershipHint")
                h2 = issue2.get("ownershipHint")
                if h1 and h2 and globs_overlap(h1, h2):
                    msg = f"Parallel issues '{issue1['key']}' and '{issue2['key']}' in wave {wave} have overlapping ownershipHint paths: '{h1}' and '{h2}'"
                    print(f"Warning: {msg}", file=sys.stderr)
                    raise BuildError(msg)


def derive(plan: dict, snapshot: dict[str, dict]) -> dict:
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
    done = [issue["key"] for issue in plan["issues"] if is_done(snapshot[issue["key"]])]
    unfinished = [issue for issue in plan["issues"] if issue["key"] not in done]
    current_wave = min((issue["wave"] for issue in unfinished), default=None)
    unblocked = []
    for issue in unfinished:
        if issue["wave"] != current_wave:
            continue
        if all(is_done(snapshot[dependency]) for dependency in issue["dependsOn"]):
            state = snapshot[issue["key"]]
            unblocked.append({
                "key": issue["key"],
                "number": state["number"],
                "ownershipHint": issue["ownershipHint"],
                "wave": issue["wave"],
            })
    return {
        "planId": plan["planId"],
        "planName": plan["planName"],
        "milestone": plan["planName"],
        "waves": waves,
        "currentWave": current_wave,
        "unblocked": unblocked,
        "done": done,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sidecar", type=Path)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    try:
        validator = planner_module()
        plan = validator.validate_plan(json.loads(args.sidecar.read_text(encoding="utf-8")))
        snapshot = validate_snapshot(json.loads(args.snapshot.read_text(encoding="utf-8")), plan)
        print(json.dumps(derive(plan, snapshot), indent=2, sort_keys=False))
    except (OSError, json.JSONDecodeError, BuildError, ValueError) as error:
        print(f"build waves error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
