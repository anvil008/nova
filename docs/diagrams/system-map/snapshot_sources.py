#!/usr/bin/env python3
"""Validate map coverage, then refresh or check its local source snapshot."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PLANNING_STAGES = (
    "planning-choice", "planner-brief", "planner-investigate", "research-team",
    "synthesize-plan", "review-plan",
)


def read_catalog(path, variable="workflowCatalog"):
    body = path.read_text(encoding="utf-8").split(f"const {variable} = ", 1)[1]
    return json.loads(body.rstrip().removesuffix(";"))


def validate_catalog(catalog, registry, root=ROOT):
    """Reject missing workflows, dangling paths, unknown roles, and chain cycles."""
    workflows = catalog["workflows"]
    expected = {item["name"] for item in registry["skills"]}
    names = [item["name"] for item in workflows]
    if len(names) != len(set(names)):
        raise ValueError("duplicate workflow names")
    if set(names) != expected:
        raise ValueError(
            f"workflow coverage mismatch; missing={sorted(expected - set(names))}, "
            f"extra={sorted(set(names) - expected)}"
        )
    groups = [item["id"] for item in catalog["groups"]]
    if len(groups) != len(set(groups)):
        raise ValueError("duplicate workflow groups")
    roles = {item["name"] for item in registry["agents"]}
    used_roles, used_stages, sources = set(), set(), set()
    stages = catalog["stages"]

    def visit(stage_id, ancestors=()):
        if stage_id not in stages:
            raise ValueError(f"unknown stage: {stage_id}")
        if stage_id in ancestors:
            raise ValueError(f"stage chain cycle: {' -> '.join((*ancestors, stage_id))}")
        stage = stages[stage_id]
        for field in ("title", "detail", "kind"):
            if not stage.get(field):
                raise ValueError(f"stage {stage_id} is missing {field}")
        if stage["kind"] not in {"human", "agent", "artifact", "gate"}:
            raise ValueError(f"unknown stage kind: {stage_id}")
        role = stage.get("role")
        if role is not None:
            if role not in roles:
                raise ValueError(f"unknown agent role in {stage_id}: {role}")
            used_roles.add(role)
        used_stages.add(stage_id)
        for child in stage.get("chain", []):
            visit(child, (*ancestors, stage_id))

    for workflow in workflows:
        name = workflow["name"]
        if workflow["group"] not in groups:
            raise ValueError(f"unknown group for {name}: {workflow['group']}")
        if workflow["source"] != f"skills/{name}/SKILL.md":
            raise ValueError(f"noncanonical skill source for {name}")
        for field in ("title", "summary", "outcome"):
            if not workflow.get(field):
                raise ValueError(f"workflow {name} is missing {field}")
        sources.add(workflow["source"])
        for role in workflow.get("support", []):
            if role not in roles:
                raise ValueError(f"unknown supporting role for {name}: {role}")
            used_roles.add(role)
        for related in workflow.get("related", []):
            if related not in expected:
                raise ValueError(f"unknown related workflow for {name}: {related}")
        paths = workflow["paths"]
        path_ids = [path["id"] for path in paths]
        if not paths or len(path_ids) != len(set(path_ids)):
            raise ValueError(f"missing or duplicate execution paths for {name}")
        for path in paths:
            if not path.get("stages") or not path.get("label"):
                raise ValueError(f"empty execution path for {name}/{path['id']}")
            for stage_id in path["stages"]:
                for expanded in PLANNING_STAGES if stage_id == "$planning" else (stage_id,):
                    visit(expanded)
    if used_roles != roles:
        raise ValueError(f"unmapped agent roles: {sorted(roles - used_roles)}")
    if used_stages != set(stages):
        raise ValueError(f"unreachable stages: {sorted(set(stages) - used_stages)}")
    if set(groups) != {workflow["group"] for workflow in workflows}:
        raise ValueError("empty workflow group")
    sources.update(f"agents/bodies/{role}.md" for role in roles)
    for path in sources:
        source = (root / path).resolve(strict=True)
        if not source.is_relative_to(root):
            raise ValueError(f"source leaves repository: {path}")
    return sources


def validate_design(design, catalog, registry):
    """Check that the proposed surface maps every current skill to valid paths."""
    current = {workflow["name"]: workflow for workflow in catalog["workflows"]}
    stages = {name: dict(stage) for name, stage in catalog["stages"].items()}
    for name, changes in design["stages"].items():
        stages[name] = {**stages.get(name, {}), **changes}
    roles = {agent["name"] for agent in registry["agents"]}
    groups = [group["id"] for group in design["groups"]]
    if len(groups) != len(set(groups)) or "auxiliary" in groups:
        raise ValueError("invalid proposed workflow groups")
    entries = design["workflows"] + design["auxiliaries"]
    names = [entry["name"] for entry in entries]
    if len(names) != len(set(names)):
        raise ValueError("duplicate proposed workflow or auxiliary names")
    resolved, covered, used_stages, used_roles = {}, set(), set(), set()

    def visit(name, ancestors=()):
        if name not in stages or name in ancestors:
            raise ValueError(f"invalid proposed stage path: {' -> '.join((*ancestors, name))}")
        stage = stages[name]
        if not stage.get("title") or not stage.get("detail") or stage.get("kind") not in {"human", "agent", "artifact", "gate"}:
            raise ValueError(f"incomplete proposed stage: {name}")
        if stage.get("role") is not None:
            if stage["role"] not in roles:
                raise ValueError(f"unknown proposed agent role: {stage['role']}")
            used_roles.add(stage["role"])
        used_stages.add(name)
        for child in stage.get("chain", []):
            visit(child, (*ancestors, name))

    for entry in entries:
        name, source = entry["name"], entry.get("source", entry["name"])
        if source not in current:
            raise ValueError(f"unknown current source for proposed workflow {name}: {source}")
        allowed_groups = {"auxiliary"} if entry in design["auxiliaries"] else set(groups)
        if entry["group"] not in allowed_groups:
            raise ValueError(f"invalid proposed workflow group for {name}")
        paths = entry.get("paths", current[source]["paths"])
        ids = [path["id"] for path in paths]
        if not paths or len(ids) != len(set(ids)):
            raise ValueError(f"missing or duplicate proposed paths: {name}")
        for path in paths:
            if not path.get("label") or not path.get("stages"):
                raise ValueError(f"empty proposed path: {name}/{path['id']}")
            for stage in path["stages"]:
                for expanded in PLANNING_STAGES if stage == "$planning" else (stage,):
                    visit(expanded)
        for role in entry.get("support", current[source].get("support", [])):
            if role not in roles:
                raise ValueError(f"unknown proposed supporting role: {role}")
            used_roles.add(role)
        for tree_path in entry.get("treePaths", []):
            if tree_path["id"] not in ids:
                raise ValueError(f"tree links to a missing execution path: {name}/{tree_path['id']}")
        resolved[name] = paths
        covered.add(source)
    for old, target in design["aliases"].items():
        paths = resolved.get(target["workflow"], [])
        if old in resolved or target["path"] not in {path["id"] for path in paths}:
            raise ValueError(f"invalid legacy workflow route: {old}")
        if old in current:
            covered.add(old)
    if covered != set(current):
        raise ValueError(f"current skills missing from the proposed design: {sorted(set(current) - covered)}")
    if used_roles != roles:
        raise ValueError(f"agent roles missing from the proposed design: {sorted(roles - used_roles)}")
    if not set(design["stages"]).issubset(used_stages):
        raise ValueError(f"unreachable proposed stages: {sorted(set(design['stages']) - used_stages)}")
    return sum(len(paths) for paths in resolved.values())


def source_files(catalog, registry):
    paths = validate_catalog(catalog, registry)
    paths.update(re.findall(r'"path": "([^"]+)"', (HERE / "app.js").read_text(encoding="utf-8")))
    paths.add("contracts/harness-contracts.json")
    paths.add("docs/diagrams/system-map/workflow-design.js")
    paths.add("docs/diagrams/system-map/execution-diagrams.js")
    files = {}
    for path in sorted(paths):
        source = (ROOT / path).resolve(strict=True)
        if not source.is_relative_to(ROOT):
            raise ValueError(f"source leaves repository: {path}")
        files[path] = source.read_text(encoding="utf-8")
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check coverage and source freshness without writing")
    args = parser.parse_args()
    catalog = read_catalog(HERE / "workflows.js")
    registry = json.loads((ROOT / "contracts/harness-contracts.json").read_text(encoding="utf-8"))
    design = read_catalog(HERE / "workflow-design.js", "workflowDesign")
    design_paths = validate_design(design, catalog, registry)
    files = source_files(catalog, registry)
    revision = subprocess.check_output(
        ["git", "-c", "core.fsmonitor=false", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
    ).strip()
    snapshot_path = HERE / "sources.json"
    if args.check:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        previous = snapshot["files"]
        changed = sorted(path for path in set(files) | set(previous) if files.get(path) != previous.get(path))
        if changed or snapshot["baseRevision"] != revision:
            raise ValueError(
                f"source snapshot is stale: {', '.join(changed) or 'base revision'}; "
                "run python3 docs/diagrams/system-map/snapshot_sources.py"
            )
    else:
        snapshot = {"baseRevision": revision, "capturedAt": datetime.now(timezone.utc).isoformat(), "files": files}
        snapshot_path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(
        f"Validated {len(catalog['workflows'])} skills, {len(registry['agents'])} roles, "
        f"{sum(len(workflow['paths']) for workflow in catalog['workflows'])} paths; "
        f"{'checked' if args.check else 'captured'} {len(files)} source files"
    )
    print(f"Workflow design: {len(design['workflows'])} workflows, {len(design['auxiliaries'])} auxiliaries, {design_paths} paths")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, IndexError, OSError) as error:
        raise SystemExit(str(error)) from error
