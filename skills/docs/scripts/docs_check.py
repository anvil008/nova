#!/usr/bin/env python3
"""Mechanical documentation-hygiene check.

Enforces three rules the way tdd-guard enforces TDD — as a check a machine ran, not
prose an agent claims:
  1. Instruction files (CLAUDE.md / AGENTS.md / GEMINI.md) stay under a line budget.
  2. ADRs under docs/adr/ are named NNNN-title.md, carry Status/Context/Decision/
     Consequences, and use unique numbers.
  3. Every skill an agent definition names (a `skills:` frontmatter list or a
     `## Skills` section under agents/**/*.md) exists as a directory under skills/.
Exits non-zero when any rule is violated.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


INSTRUCTION_FILES = ("CLAUDE.md", "AGENTS.md", "GEMINI.md")
ADR_NAME = re.compile(r"^(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
ADR_SECTIONS = ("Status", "Context", "Decision", "Consequences")
SKIP_DIRS = {".git", "node_modules", ".venv", "dist", "build", "v1", "v2"}
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
FRONTMATTER_SKILLS = re.compile(r"^skills:[ \t]*(\[.*\])?[ \t]*(?:\n((?:[ \t]+-[^\n]*\n)*))?", re.M)
SKILLS_SECTION = re.compile(r"(?ms)^## Skills\s*\n(.*?)(?=^## |\Z)")
SECTION_SKILL = re.compile(r"^[ \t]*-\s+(.*?)(?:\s+—|$)", re.M)  # a bullet's head: the names before the em dash


def _iter_instruction_files(root: Path):
    seen = set()
    for name in INSTRUCTION_FILES:
        for path in sorted(root.rglob(name)):
            if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
                continue
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path


def _skill_refs(text: str) -> list[str]:
    """Skill names an agent definition declares, in frontmatter and its `## Skills` section."""
    refs = []
    text = text.replace("\r\n", "\n")
    front = FRONTMATTER.match(text)
    if front:
        for match in FRONTMATTER_SKILLS.finditer(front.group(1) + "\n"):
            inline, block = match.groups()
            items = inline.strip("[]").split(",") if inline else (block or "").split("\n")
            refs += [item.split(" #", 1)[0].strip().lstrip("-").strip().strip("'\"") for item in items]
    body = text[front.end():] if front else text
    for section in SKILLS_SECTION.finditer(body):
        for bullet in SECTION_SKILL.finditer(section.group(1)):
            refs += re.findall(r"`([^`]+)`", bullet.group(1))
    return [Path(ref).name for ref in refs if ref]


def check(root: Path, max_lines: int) -> dict:
    instruction, adrs, skills, violations = [], [], [], []

    for path in _iter_instruction_files(root):
        lines = len(path.read_text(encoding="utf-8").splitlines())
        ok = lines <= max_lines
        rel = path.relative_to(root).as_posix()
        instruction.append({"path": rel, "lines": lines, "budget": max_lines, "ok": ok})
        if not ok:
            violations.append(f"{rel} exceeds the {max_lines}-line budget ({lines}) — relocate role material into the relevant agent")

    adr_dir = root / "docs" / "adr"
    numbers: dict[int, list[str]] = {}
    if adr_dir.is_dir():
        for path in sorted(adr_dir.glob("*.md")):
            rel = path.relative_to(root).as_posix()
            match = ADR_NAME.match(path.name)
            if not match:
                violations.append(f"{rel} is not a valid ADR filename (expected NNNN-title.md)")
                adrs.append({"path": rel, "number": None, "ok": False, "missing": []})
                continue
            number = int(match.group(1))
            text = path.read_text(encoding="utf-8")
            missing = [s for s in ADR_SECTIONS if not re.search(rf"(?mi)^#+\s*{s}\b", text)]
            adrs.append({"path": rel, "number": number, "ok": not missing, "missing": missing})
            if missing:
                violations.append(f"{rel} missing sections: {', '.join(missing)}")
            numbers.setdefault(number, []).append(rel)
        for number, paths in sorted(numbers.items()):
            if len(paths) > 1:
                violations.append(f"duplicate ADR number: {number} ({', '.join(paths)})")

    agents_dir = root / "agents"
    if agents_dir.is_dir():
        for path in sorted(agents_dir.rglob("*.md")):
            rel = path.relative_to(root).as_posix()
            for name in _skill_refs(path.read_text(encoding="utf-8")):
                ok = (root / "skills" / name).is_dir()
                skills.append({"agent": rel, "skill": name, "ok": ok})
                if not ok:
                    violations.append(f"{rel} references skill `{name}` which does not exist under skills/")

    return {"instructionFiles": instruction, "adrs": adrs, "skillRefs": skills, "violations": violations, "ok": not violations}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--max-instruction-lines", type=int, default=120)
    args = parser.parse_args()
    try:
        result = check(args.root, args.max_instruction_lines)
    except OSError as error:
        print(f"docs check error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
