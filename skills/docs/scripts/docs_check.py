#!/usr/bin/env python3
"""Mechanical documentation-hygiene check.

Enforces two rules the way tdd-guard enforces TDD — as a check a machine ran, not
prose an agent claims:
  1. Instruction files (CLAUDE.md / AGENTS.md) stay under a line budget (no bloat).
  2. ADRs under docs/adr/ are named NNNN-title.md, carry Status/Context/Decision/
     Consequences, and use unique numbers.
Exits non-zero when any rule is violated.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


INSTRUCTION_FILES = ("CLAUDE.md", "AGENTS.md")
ADR_NAME = re.compile(r"^(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
ADR_SECTIONS = ("Status", "Context", "Decision", "Consequences")
SKIP_DIRS = {".git", "node_modules", ".venv", "dist", "build", "v1", "v2"}


def _iter_instruction_files(root: Path):
    seen = set()
    for name in INSTRUCTION_FILES:
        for path in sorted(root.rglob(name)):
            if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
                continue
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path


def check(root: Path, max_lines: int) -> dict:
    instruction, adrs, violations = [], [], []

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

    return {"instructionFiles": instruction, "adrs": adrs, "violations": violations, "ok": not violations}


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
