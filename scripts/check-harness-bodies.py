#!/usr/bin/env python3
"""Mechanical harness-body checker.

Validates harness-owned bodies against their shared sources across all harness families.
Checks:
  (a) headings (##/###) present in the source but absent in the body (allowlisted via
      <!-- body-check: drop-heading "<heading>" reason -->);
  (b) fenced command blocks and script paths (skills/*/scripts/*.py|sh, scripts/*.py|sh,
      tdd-guard/jj/gh invocations) present in the source but absent in the body;
  (c) markdown tables (by header row) present in the source but absent in the body;
  (d) links whose text is a path differing from resolved target, and broken relative links;
  (e) required contract strings per role and skill as detected by existing parity code.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

HARNESSES = ("claude", "codex", "agy", "grok")
HARNESS_OWNED_SKILLS = frozenset({"claude", "codex"})

# Conditionals used in agent shared bodies
ONLY_OPEN = re.compile(r"^<!--\s*only:([a-z0-9_,-]+)\s*-->$")
ONLY_CLOSE = "<!-- end -->"

# Heading pattern (level 2 and 3)
HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$")

# Allowlist pattern for dropped headings
ALLOWLIST_RE = re.compile(
    r"""<!--\s*body-check:\s*drop-heading\s+["\x27]([^"\x27]+)["\x27]\s*(.*?)\s*-->"""
)

# Markdown link pattern: [text](target)
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+?)(?:\s+\"[^\"]*\")?\)")
EXTERNAL_LINK_PREFIXES = ("http://", "https://", "mailto:", "#", "<")

# Script paths and tool invocations
SCRIPT_PATH_RE = re.compile(
    r"\b(?:skills/[a-zA-Z0-9_-]+/scripts/[a-zA-Z0-9_.-]+\.(?:py|sh)|scripts/[a-zA-Z0-9_.-]+\.(?:py|sh))\b"
)
TOOL_INVOCATION_RE = re.compile(
    r"\b(tdd-guard\s+[a-z0-9_-]+|jj\s+[a-z0-9_-]+|gh\s+[a-z0-9_-]+)\b"
)

# Table separator row pattern
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*[-:]+[-| :]*\|?\s*$")


@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    rule: str
    detail: str


def apply_conditionals(text: str, harness: str) -> str:
    """Filter <!-- only:<harnesses> --> ... <!-- end --> blocks in shared source."""
    kept: list[str] = []
    skipping = False
    for line in text.splitlines():
        stripped = line.strip()
        opened = ONLY_OPEN.match(stripped)
        if opened:
            allowed = [h.strip() for h in opened.group(1).split(",")]
            skipping = harness not in allowed
            continue
        if stripped == ONLY_CLOSE:
            skipping = False
            continue
        if not skipping:
            kept.append(line)
    return "\n".join(kept)


def extract_headings(text: str) -> list[tuple[int, str, str]]:
    """Extract (line_no, level, heading_text) for ## and ### outside code blocks and frontmatter."""
    headings: list[tuple[int, str, str]] = []
    in_code = False
    in_frontmatter = False
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if i == 1 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        match = HEADING_RE.match(line)
        if match:
            headings.append((i, match.group(1), match.group(2).strip()))
    return headings


def extract_allowlisted_headings(text: str) -> set[str]:
    """Parse <!-- body-check: drop-heading "<heading>" reason --> comments."""
    allowed: set[str] = set()
    for match in ALLOWLIST_RE.finditer(text):
        h = match.group(1).strip().lstrip("#").strip().lower()
        allowed.add(h)
    return allowed


def extract_tables(text: str) -> list[tuple[int, tuple[str, ...], str]]:
    """Extract markdown table header rows outside code blocks."""
    tables: list[tuple[int, tuple[str, ...], str]] = []
    in_code = False
    in_frontmatter = False
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if i == 0 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if "|" in line and i + 1 < len(lines) and TABLE_SEP_RE.match(lines[i + 1]):
            cols = tuple(c.strip().lower() for c in line.split("|") if c.strip())
            if cols:
                tables.append((i + 1, cols, line.strip()))
    return tables


def extract_command_blocks(text: str) -> list[tuple[int, list[str]]]:
    """Extract fenced command blocks and their active command lines."""
    blocks: list[tuple[int, list[str]]] = []
    in_code = False
    current_lines: list[str] = []
    start_line = 0
    is_command_block = False
    lines = text.splitlines()

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                start_line = i
                lang = stripped.lstrip("`").strip().lower()
                is_command_block = lang in ("bash", "sh", "zsh", "shell", "console", "")
                current_lines = []
            else:
                in_code = False
                if is_command_block and current_lines:
                    blocks.append((start_line, current_lines))
                current_lines = []
                is_command_block = False
            continue

        if in_code and is_command_block and stripped and not stripped.startswith("#"):
            current_lines.append(stripped)

    return blocks


def extract_script_paths(text: str) -> list[tuple[int, str]]:
    """Extract script paths with line numbers outside comments in code blocks."""
    paths: list[tuple[int, str]] = []
    in_code = False
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code and stripped.startswith("#"):
            continue
        for match in SCRIPT_PATH_RE.finditer(line):
            paths.append((i, match.group(0)))
    return paths


def extract_tool_invocations(text: str) -> list[tuple[int, str]]:
    """Extract invocations of tdd-guard, jj, and gh with line numbers outside comments in code."""
    invocations: list[tuple[int, str]] = []
    in_code = False
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code and stripped.startswith("#"):
            continue
        for match in TOOL_INVOCATION_RE.finditer(line):
            invocations.append((i, match.group(0)))
    return invocations


def is_path_like(text: str) -> bool:
    """Return True if text resembles a relative file path."""
    clean = text.strip("` \t'\"")
    if (
        not clean
        or clean.startswith(EXTERNAL_LINK_PREFIXES)
        or clean.startswith("anvil.")
    ):
        return False
    if clean.startswith(("./", "../")):
        return True
    extensions = (
        ".md",
        ".py",
        ".sh",
        ".json",
        ".html",
        ".css",
        ".toml",
        ".yaml",
        ".yml",
        ".txt",
    )
    return any(clean.endswith(ext) for ext in extensions)


def check_links(body_file: Path, root: Path, text: str) -> list[Violation]:
    """Check broken links and text-vs-target path mismatches in body file."""
    violations: list[Violation] = []
    rel_body = str(body_file.relative_to(root))

    for i, line in enumerate(text.splitlines(), 1):
        for match in LINK_RE.finditer(line):
            link_text = match.group(1).strip()
            target = match.group(2).strip()
            if target.startswith(EXTERNAL_LINK_PREFIXES):
                continue
            path_part = target.split("#", 1)[0]
            if not path_part:
                continue

            # (1) Does target exist relative to body file?
            target_file = body_file.parent / path_part
            if not target_file.exists():
                violations.append(
                    Violation(
                        file=rel_body,
                        line=i,
                        rule="broken-link",
                        detail=f"link target '{target}' does not exist relative to body file",
                    )
                )

            # (2) Does link text look like a path that differs from resolved target?
            if is_path_like(link_text):
                clean_text = link_text.strip("` \t'\"")
                text_name = Path(clean_text).name
                target_name = Path(path_part).name
                if text_name != target_name:
                    violations.append(
                        Violation(
                            file=rel_body,
                            line=i,
                            rule="link-text-mismatch",
                            detail=(
                                f"link text '{link_text}' has name '{text_name}' "
                                f"which differs from target '{path_part}'"
                            ),
                        )
                    )

    return violations


def check_contracts(
    body_file: Path,
    root: Path,
    harness: str,
    kind: str,
    name: str,
    body_text: str,
    registry: dict | None,
) -> list[Violation]:
    """Check required contract strings per role and skill as detected by existing parity code."""
    violations: list[Violation] = []
    rel_body = str(body_file.relative_to(root))
    normalized_body = re.sub(r"\s+", " ", body_text)

    if kind == "skill":
        if name == "use-other-harness":
            prohibition = "Do not guess a model or effort, and do not pick a harness on the user's behalf."
            if prohibition not in normalized_body:
                violations.append(
                    Violation(
                        file=rel_body,
                        line=1,
                        rule="missing-contract-string",
                        detail=f"missing required contract string: {prohibition!r}",
                    )
                )
            if "silently fall back" in normalized_body.lower():
                violations.append(
                    Violation(
                        file=rel_body,
                        line=1,
                        rule="missing-contract-string",
                        detail="forbidden string 'silently fall back' found in use-other-harness",
                    )
                )

        if registry and harness in HARNESS_OWNED_SKILLS:
            skill_entry = next(
                (s for s in registry.get("skills", []) if s["name"] == name), None
            )
            if skill_entry:
                inv = skill_entry.get("invocation")
                if inv and inv not in body_text:
                    violations.append(
                        Violation(
                            file=rel_body,
                            line=1,
                            rule="missing-contract-string",
                            detail=f"missing required invocation contract string: {inv!r}",
                        )
                    )
                if name != "jj":
                    handoff = skill_entry.get("handoffSchema")
                    if handoff and handoff not in body_text:
                        violations.append(
                            Violation(
                                file=rel_body,
                                line=1,
                                rule="missing-contract-string",
                                detail=f"missing required handoff schema string: {handoff!r}",
                            )
                        )

    elif kind == "agent":
        if registry:
            agent_entry = next(
                (a for a in registry.get("agents", []) if a["name"] == name), None
            )
            if agent_entry:
                handoff = agent_entry.get("handoffSchema")
                if handoff and handoff not in body_text:
                    violations.append(
                        Violation(
                            file=rel_body,
                            line=1,
                            rule="missing-contract-string",
                            detail=f"missing required handoff schema string: {handoff!r}",
                        )
                    )

        if name == "builder":
            for req in ("jj workspace list", "diff-review record"):
                if req not in body_text:
                    violations.append(
                        Violation(
                            file=rel_body,
                            line=1,
                            rule="missing-contract-string",
                            detail=f"missing required builder contract string: {req!r}",
                        )
                    )
        elif name == "researcher":
            if "Never edit" not in body_text and "never edit" not in body_text.lower():
                violations.append(
                    Violation(
                        file=rel_body,
                        line=1,
                        rule="missing-contract-string",
                        detail="missing required researcher contract string: 'Never edit'",
                    )
                )
        elif name == "documenter" and "what the repository does" not in body_text:
            violations.append(
                Violation(
                    file=rel_body,
                    line=1,
                    rule="missing-contract-string",
                    detail="missing required documenter contract string: 'what the repository does'",
                )
            )

    return violations


def discover_bodies(
    root: Path, harness_filter: str | None = None
) -> list[tuple[str, str, str, Path, Path]]:
    """Discover all (harness, kind, name, body_path, source_path) tuples."""
    harnesses = [harness_filter] if harness_filter else list(HARNESSES)
    discovered: list[tuple[str, str, str, Path, Path]] = []

    for h in harnesses:
        # Skills
        skill_dir = root / "harnesses" / h / "skills"
        if skill_dir.is_dir():
            for sp in sorted(skill_dir.iterdir()):
                if not sp.is_dir():
                    continue
                body_file = sp / "SKILL.md"
                source_file = root / "skills" / sp.name / "SKILL.md"
                if body_file.is_file() and source_file.is_file():
                    discovered.append((h, "skill", sp.name, body_file, source_file))

        # Agents
        agent_dir = root / "harnesses" / h / "agents"
        if agent_dir.is_dir():
            for ap in sorted(agent_dir.iterdir()):
                if ap.is_file() and ap.suffix == ".md":
                    source_file = root / "agents" / "bodies" / f"{ap.stem}.md"
                    if source_file.is_file():
                        discovered.append((h, "agent", ap.stem, ap, source_file))
                elif ap.is_dir():
                    body_file = ap / "agent.md"
                    source_file = root / "agents" / "bodies" / f"{ap.name}.md"
                    if body_file.is_file() and source_file.is_file():
                        discovered.append((h, "agent", ap.name, body_file, source_file))

    return discovered


def check_body(
    root: Path,
    harness: str,
    kind: str,
    name: str,
    body_file: Path,
    source_file: Path,
    registry: dict | None,
) -> list[Violation]:
    """Check a single harness-owned body against its shared source."""
    violations: list[Violation] = []
    rel_body = str(body_file.relative_to(root))

    source_text = source_file.read_text(encoding="utf-8")
    if kind == "agent":
        source_text = apply_conditionals(source_text, harness)

    body_text = body_file.read_text(encoding="utf-8")

    # (a) Headings
    source_headings = extract_headings(source_text)
    body_headings = extract_headings(body_text)
    body_heading_set = {h[2].lstrip("#").strip().lower() for h in body_headings}
    allowlist = extract_allowlisted_headings(body_text)

    for line_no, level, h_text in source_headings:
        norm = h_text.lstrip("#").strip().lower()
        if norm not in body_heading_set and norm not in allowlist:
            violations.append(
                Violation(
                    file=rel_body,
                    line=1,
                    rule="lost-heading",
                    detail=f"heading '{level} {h_text}' (source line {line_no}) is absent in body",
                )
            )

    # (b) Commands and script paths
    # 1. Script paths
    source_scripts = extract_script_paths(source_text)
    for line_no, script in source_scripts:
        script_name = Path(script).name
        if script not in body_text and script_name not in body_text:
            violations.append(
                Violation(
                    file=rel_body,
                    line=1,
                    rule="lost-command",
                    detail=f"script path '{script}' (source line {line_no}) is absent in body",
                )
            )

    # 2. Tool invocations
    source_invocations = extract_tool_invocations(source_text)
    body_lower = body_text.lower()
    for line_no, inv in source_invocations:
        if inv.lower() not in body_lower:
            violations.append(
                Violation(
                    file=rel_body,
                    line=1,
                    rule="lost-command",
                    detail=f"tool invocation '{inv}' (source line {line_no}) is absent in body",
                )
            )

    # 3. Fenced command blocks
    source_command_blocks = extract_command_blocks(source_text)
    for start_line, cmd_lines in source_command_blocks:
        represented = False
        for cmd in cmd_lines:
            for match in SCRIPT_PATH_RE.finditer(cmd):
                if (
                    match.group(0) in body_text
                    or Path(match.group(0)).name in body_text
                ):
                    represented = True
                    break
            if represented:
                break
            for match in TOOL_INVOCATION_RE.finditer(cmd):
                if match.group(0).lower() in body_lower:
                    represented = True
                    break
            if represented:
                break
            first_cmd = cmd.split(";")[0].split("|")[0].strip()
            if len(first_cmd) > 5 and first_cmd in body_text:
                represented = True
                break
        if not represented:
            sample = cmd_lines[0] if cmd_lines else "empty"
            violations.append(
                Violation(
                    file=rel_body,
                    line=1,
                    rule="lost-command",
                    detail=f"fenced command block at source line {start_line} ('{sample}...') is absent in body",
                )
            )

    # (c) Tables
    source_tables = extract_tables(source_text)
    body_tables = extract_tables(body_text)
    body_table_cols = {t[1] for t in body_tables}

    for line_no, cols, header_line in source_tables:
        if cols not in body_table_cols:
            violations.append(
                Violation(
                    file=rel_body,
                    line=1,
                    rule="lost-table",
                    detail=f"table with header '{header_line}' (source line {line_no}) is absent in body",
                )
            )

    # (d) Links
    violations.extend(check_links(body_file, root, body_text))

    # (e) Contracts
    violations.extend(
        check_contracts(body_file, root, harness, kind, name, body_text, registry)
    )

    return violations


def run_check(root: Path, harness_filter: str | None = None) -> list[Violation]:
    """Discover all bodies and collect violations."""
    registry_file = root / "contracts" / "harness-contracts.json"
    registry = None
    if registry_file.is_file():
        try:
            registry = json.loads(registry_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            registry = None

    bodies = discover_bodies(root, harness_filter)
    all_violations: list[Violation] = []
    for harness, kind, name, body_file, source_file in bodies:
        all_violations.extend(
            check_body(root, harness, kind, name, body_file, source_file, registry)
        )

    return all_violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check harness bodies against shared sources for lost procedure, links, and contract strings."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (defaults to current working directory).",
    )
    parser.add_argument(
        "--harness",
        choices=HARNESSES,
        default=None,
        help="Filter check to a specific harness family.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output violations as JSON.",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    violations = run_check(root, args.harness)

    if args.json:
        data = [asdict(v) for v in violations]
        print(json.dumps(data, indent=2))
    else:
        for v in violations:
            print(f"{v.file}:{v.line}: [{v.rule}] {v.detail}")
        if violations:
            print(f"\nFound {len(violations)} violation(s) across harness bodies.")
        else:
            print("All harness bodies match shared sources cleanly.")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
