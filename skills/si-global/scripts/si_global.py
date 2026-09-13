#!/usr/bin/env python3
"""Global self-improvement CLI for Nova.

Aggregates in-repo patterns across known projects, clusters recurring systemic
issues, and formulates candidate proposals for shared core skills.
"""

from collections import defaultdict
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys


def get_registry_path(custom_path: str | None = None) -> Path:
    if custom_path:
        return Path(custom_path).resolve()
    env_path = os.environ.get("NOVA_PROJECTS_REGISTRY")
    if env_path:
        return Path(env_path).resolve()
    return Path.home() / ".nova" / "known_projects.json"


def read_registry(registry_path: Path) -> list[Path]:
    if not registry_path.is_file():
        return []
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        raw_list = []
        if isinstance(data, list):
            raw_list = data
        elif isinstance(data, dict) and "projects" in data and isinstance(data["projects"], list):
            raw_list = data["projects"]
        return [Path(p).resolve() for p in raw_list if isinstance(p, str)]
    except Exception:
        return []


def inspect_project(proj_root: Path) -> dict:
    info = {
        "path": str(proj_root),
        "exists": proj_root.is_dir(),
        "storeExists": False,
        "patterns": 0,
        "raw": 0,
        "proposals": 0,
    }
    if not proj_root.is_dir():
        return info

    store = proj_root / ".nova" / "si"
    if (store / "project.json").is_file():
        info["storeExists"] = True
        if (store / "patterns").is_dir():
            info["patterns"] = len(list((store / "patterns").glob("*.md")))
        if (store / "raw").is_dir():
            info["raw"] = len([d for d in (store / "raw").iterdir() if d.is_dir() and not d.name.startswith(".")])
        if (store / "proposals").is_dir():
            info["proposals"] = len(list((store / "proposals").glob("*.json")))

    return info


def scan_all_patterns(projects: list[Path]) -> list[dict]:
    all_patterns = []
    for proj in projects:
        if not proj.is_dir():
            continue
        store = proj / ".nova" / "si"
        patterns_dir = store / "patterns"
        if not patterns_dir.is_dir():
            continue

        for pfile in sorted(patterns_dir.glob("*.md")):
            slug = pfile.stem
            lines = pfile.read_text(encoding="utf-8").splitlines()
            title = slug
            if lines and lines[0].startswith("# "):
                title = lines[0][2:].strip()

            evidence_lines = [l for l in lines if l.startswith("- ")]
            last_date = ""
            notes = []
            for el in evidence_lines:
                parts = el.split("—")
                if len(parts) >= 3:
                    d = parts[0].strip().lstrip("-").strip()
                    if d > last_date:
                        last_date = d
                    notes.append(parts[2].strip())

            all_patterns.append({
                "project": str(proj),
                "slug": slug,
                "title": title,
                "occurrences": len(evidence_lines),
                "lastDate": last_date,
                "notes": notes,
            })

    return all_patterns


def cluster_patterns(patterns: list[dict], min_projects: int = 2) -> list[dict]:
    # Group by slug first
    by_slug: dict[str, list[dict]] = defaultdict(list)
    for p in patterns:
        by_slug[p["slug"]].append(p)

    clusters = []
    for slug, entries in by_slug.items():
        distinct_projects = sorted(list({e["project"] for e in entries}))
        if len(distinct_projects) >= min_projects:
            total_occurrences = sum(e["occurrences"] for e in entries)
            latest_date = max((e["lastDate"] for e in entries), default="")
            sample_notes = []
            for e in entries:
                sample_notes.extend(e.get("notes", []))

            clusters.append({
                "slug": slug,
                "title": entries[0]["title"],
                "projectCount": len(distinct_projects),
                "projects": distinct_projects,
                "totalOccurrences": total_occurrences,
                "latestDate": latest_date,
                "sampleNotes": sample_notes[:5],
            })

    clusters.sort(key=lambda c: (c["projectCount"], c["totalOccurrences"]), reverse=True)
    return clusters


def command_projects(args: argparse.Namespace) -> int:
    reg_path = get_registry_path(args.registry)
    projects = read_registry(reg_path)
    inspected = [inspect_project(p) for p in projects]

    print(json.dumps({
        "registry": str(reg_path),
        "totalProjects": len(projects),
        "projects": inspected,
    }, indent=2))
    return 0


def command_scan(args: argparse.Namespace) -> int:
    reg_path = get_registry_path(args.registry)
    projects = read_registry(reg_path)
    patterns = scan_all_patterns(projects)

    print(json.dumps({
        "registry": str(reg_path),
        "totalProjects": len(projects),
        "totalPatterns": len(patterns),
        "patterns": patterns,
    }, indent=2))
    return 0


def command_cluster(args: argparse.Namespace) -> int:
    reg_path = get_registry_path(args.registry)
    projects = read_registry(reg_path)
    patterns = scan_all_patterns(projects)
    clusters = cluster_patterns(patterns, min_projects=args.min_projects)

    print(json.dumps({
        "registry": str(reg_path),
        "minProjects": args.min_projects,
        "clusterCount": len(clusters),
        "clusters": clusters,
    }, indent=2))
    return 0


def command_propose(args: argparse.Namespace) -> int:
    reg_path = get_registry_path(args.registry)
    projects = read_registry(reg_path)
    patterns = scan_all_patterns(projects)
    clusters = cluster_patterns(patterns, min_projects=args.min_projects)

    proposals = []
    for c in clusters:
        slug = c["slug"]
        target_skill = args.target_skill
        if not target_skill:
            if any(k in slug for k in ("test", "lock", "runner", "build", "sandbox")):
                target_skill = "build"
            elif any(k in slug for k in ("review", "lint", "defect", "finding")):
                target_skill = "review"
            else:
                target_skill = "build"

        proposal = {
            "id": f"global-{slug}",
            "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "targetSkill": target_skill,
            "targetPath": f"skills/{target_skill}/SKILL.md",
            "title": f"Systemic mitigation for {c['title']} across {c['projectCount']} projects",
            "cluster": {
                "slug": slug,
                "projectCount": c["projectCount"],
                "projects": c["projects"],
                "occurrences": c["totalOccurrences"],
            },
            "proposedChange": f"Add operational mitigation for recurring cross-project pattern `{slug}` into `{target_skill}` workflow.",
            "evalGate": "evals/run_evals.py",
            "status": "pending-evaluation",
        }
        proposals.append(proposal)

    if args.output:
        out_dir = Path(args.output).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        for p in proposals:
            p_path = out_dir / f"{p['id']}.json"
            p_path.write_text(json.dumps(p, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "registry": str(reg_path),
        "proposalsCount": len(proposals),
        "proposals": proposals,
        "evalGateNotice": "All proposals require verification via evals/run_evals.py before applying to shared skills.",
    }, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", help="Explicit path to known_projects.json")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    sub.add_parser("projects", help="List registered projects and store status")
    sub.add_parser("scan", help="Scan patterns across registered projects")

    cluster_p = sub.add_parser("cluster", help="Cluster recurring patterns across projects")
    cluster_p.add_argument("--min-projects", type=int, default=2, help="Minimum projects for a cluster (default 2)")

    propose_p = sub.add_parser("propose", help="Propose global shared skill updates")
    propose_p.add_argument("--min-projects", type=int, default=2, help="Minimum projects for a cluster (default 2)")
    propose_p.add_argument("--target-skill", help="Target shared skill name")
    propose_p.add_argument("--output", help="Directory to write proposal JSON files")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    handlers = {
        "projects": command_projects,
        "scan": command_scan,
        "cluster": command_cluster,
        "propose": command_propose,
    }
    handler = handlers.get(args.subcommand)
    if not handler:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
