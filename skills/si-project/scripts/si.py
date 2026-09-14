#!/usr/bin/env python3
"""Self-improvement store CLI for Nova projects.

Manages in-repo stores at <primary-root>/.nova/si/ with write-once traces,
append-only pattern catalogs, and human-approved rule/skill proposals.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import uuid

RAW_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
KEY_PART = re.compile(r"^[a-z0-9][a-z0-9-]*$")
CITATION_RE = re.compile(r"`([a-z0-9][a-z0-9._-]*)`(?:\s*\[([^\]]+)\])?")
SANITY_RE = re.compile(r"[\r\n\t]")


class SiError(Exception):
    """Raised for controlled operational failures."""


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def sanitize_line(value: str) -> str:
    return " ".join(value.strip().split())


def sanitize_model_effort(value: str | None) -> str | None:
    if value is None:
        return None
    val = value.strip()
    if not val:
        return None
    if SANITY_RE.search(val):
        raise SiError(f"model and effort cannot contain newlines or tabs: {val!r}")
    return val


def find_up(start: Path, marker: str) -> Path | None:
    current = start.resolve()
    while True:
        if (current / marker).exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def run_result(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return None


def resolve_toplevel(repo: Path, fallback_dir: bool = False) -> Path:
    if not repo.is_dir():
        raise SiError(f"no such directory: {repo}")
    repo = repo.resolve()
    workspace = find_up(repo, ".jj")
    if workspace is not None:
        pointer = workspace / ".jj" / "repo"
        if pointer.is_dir():
            return workspace.resolve()
        if pointer.is_file():
            try:
                target = pointer.read_text(encoding="utf-8").strip()
            except OSError as error:
                raise SiError(
                    f"cannot resolve the primary workspace of {workspace}: {error}"
                ) from error
            return (workspace / ".jj" / target).parent.parent.resolve()

    git_dir = find_up(repo, ".git")
    if git_dir is not None:
        listed = run_result(["git", "worktree", "list", "--porcelain"], cwd=repo)
        first = (listed.stdout if listed else "").splitlines()[:1]
        if first and first[0].startswith("worktree "):
            return Path(first[0][len("worktree ") :]).resolve()
        return git_dir.resolve()

    if fallback_dir:
        return repo.resolve()

    raise SiError(f"not a jj or git repository: {repo}")


def refuse_eval_mode(repo: Path, toplevel: Path | None = None) -> None:
    # Check every directory from --repo up to its enclosing workspace or worktree
    # root, so a marker there also covers its subdirectories, plus the primary root.
    # The boundary matches resolve_toplevel: an enclosing jj workspace wins over any
    # nested .git (such as a vendored repository inside the workspace).
    boundary = find_up(repo, ".jj")
    if boundary is not None and not (boundary / ".jj" / "repo").exists():
        boundary = None
    if boundary is None:
        boundary = find_up(repo, ".git")
    candidates = [repo]
    if boundary is not None:
        current = repo
        while current != boundary and current != toplevel and current.parent != current:
            current = current.parent
            candidates.append(current)
    if toplevel is not None and toplevel not in candidates:
        candidates.append(toplevel)
    for candidate in candidates:
        marker = candidate / ".nova" / "eval-mode.json"
        if marker.is_file():
            raise SiError(f"eval mode refused: {marker}")


def get_registry_path() -> Path:
    env_path = os.environ.get("NOVA_PROJECTS_REGISTRY")
    if env_path:
        return Path(env_path).resolve()
    return Path.home() / ".nova" / "known_projects.json"


def read_registry(registry_path: Path) -> list[str]:
    # Same shape rules as si_global.py's reader; duplicated because skills ship separately.
    if not registry_path.exists():
        return []
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SiError(f"invalid registry {registry_path}: {error}") from error
    raw_list = data.get("projects") if isinstance(data, dict) else data
    if not isinstance(raw_list, list) or not all(isinstance(p, str) for p in raw_list):
        raise SiError(
            f"invalid registry {registry_path}: expected a list of path strings"
            " or an object whose \"projects\" is a list of path strings"
        )
    return list(raw_list)


def is_safe_component(name: object) -> bool:
    return (
        isinstance(name, str)
        and bool(name)
        and not name.startswith(".")
        and not any(ch in ("/", "\\") or unicodedata.category(ch) == "Cc" for ch in name)
    )


def validate_proposal_id(proposal_id: str, apply_only: bool = False) -> str:
    # Existing proposals may predate the strict pattern, so --apply accepts any
    # single safe path component; new proposals must match RAW_ID.
    valid = is_safe_component(proposal_id) if apply_only else bool(RAW_ID.match(proposal_id))
    if not valid:
        raise SiError(f"invalid proposal id: {proposal_id!r}")
    return proposal_id


def validate_skill_name(skill_name: object) -> str:
    if not is_safe_component(skill_name):
        raise SiError(f"invalid skill name: {skill_name!r}")
    return skill_name


def register_project(primary_root: Path, registry_path: Path | None = None) -> Path:
    if registry_path is None:
        registry_path = get_registry_path()
    existing = set(read_registry(registry_path))
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    existing.add(str(primary_root.resolve()))
    sorted_projects = sorted(existing)

    temp = registry_path.parent / f".tmp-{uuid.uuid4()}"
    try:
        temp.write_text(
            json.dumps({"projects": sorted_projects}, indent=2) + "\n",
            encoding="utf-8",
        )
        temp.replace(registry_path)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)
    return registry_path


def resolve_store_and_root(
    args: argparse.Namespace,
) -> tuple[Path, Path]:
    repo = Path(args.repo).resolve() if getattr(args, "repo", None) else Path.cwd().resolve()
    override_store = getattr(args, "store", None) or os.environ.get("NOVA_SI_STORE")
    fallback = bool(override_store)
    primary_root = resolve_toplevel(repo, fallback_dir=fallback)
    refuse_eval_mode(repo, primary_root)

    if override_store:
        store_path = Path(override_store).resolve()
    else:
        store_path = primary_root / ".nova" / "si"

    return store_path, primary_root


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def append_log(store: Path, line: str) -> None:
    logs_path = store / "logs.md"
    entry = f"- {now_utc()} {line}\n"
    if not logs_path.exists():
        logs_path.write_text(
            "# Evolution log\n\n"
            "One line per write to this store, oldest first. Appended by `si.py`; never edited.\n\n"
            + entry,
            encoding="utf-8",
        )
    else:
        with logs_path.open("a", encoding="utf-8") as handle:
            handle.write(entry)


def append_skill_impact(store: Path, line: str) -> None:
    impact_path = store / "skill-impact.md"
    entry = f"- {today_utc()} — {line}\n"
    if not impact_path.exists():
        impact_path.write_text(
            "# Skill impact\n\n"
            "The accept/reject audit trail for skill-change proposals.\n\n"
            + entry,
            encoding="utf-8",
        )
    else:
        with impact_path.open("a", encoding="utf-8") as handle:
            handle.write(entry)


def format_citation(raw_id: str, manifest: dict | None) -> str:
    if not manifest:
        return f"`{raw_id}`"
    model = manifest.get("model")
    effort = manifest.get("effort")
    if model and effort:
        return f"`{raw_id}` [{model}·{effort}]"
    if model:
        return f"`{raw_id}` [{model}]"
    return f"`{raw_id}`"


def update_pattern_index(store: Path) -> None:
    patterns_dir = store / "patterns"
    rows: list[tuple[str, int, str]] = []
    if patterns_dir.is_dir():
        for item in sorted(patterns_dir.glob("*.md")):
            slug = item.stem
            lines = item.read_text(encoding="utf-8").splitlines()
            evidence_lines = [l for l in lines if l.startswith("- ")]
            count = len(evidence_lines)
            last_seen = ""
            for el in evidence_lines:
                parts = el.split("—")
                if parts:
                    d = parts[0].strip().lstrip("-").strip()
                    if d > last_seen:
                        last_seen = d
            rows.append((slug, count, last_seen))

    rows.sort(key=lambda r: r[0])
    content = [
        "# Pattern index",
        "",
        "One row per pattern page.",
        "",
        "| Pattern | Occurrences | Last seen |",
        "| --- | ---: | --- |",
    ]
    for slug, count, last_seen in rows:
        content.append(f"| [{slug}](patterns/{slug}.md) | {count} | {last_seen} |")

    (store / "index.md").write_text("\n".join(content) + "\n", encoding="utf-8")


def command_init(args: argparse.Namespace) -> int:
    store, primary_root = resolve_store_and_root(args)
    # Refuse an invalid registry before creating anything.
    read_registry(get_registry_path())
    created = False
    if not (store / "project.json").exists():
        store.mkdir(parents=True, exist_ok=True)
        (store / "raw").mkdir(parents=True, exist_ok=True)
        (store / "patterns").mkdir(parents=True, exist_ok=True)
        (store / "proposals").mkdir(parents=True, exist_ok=True)

        meta = {
            "primaryRoot": str(primary_root),
            "createdAt": now_utc(),
        }
        (store / "project.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        update_pattern_index(store)
        (store / "logs.md").write_text(
            "# Evolution log\n\n"
            "One line per write to this store, oldest first. Appended by `si.py`; never edited.\n\n",
            encoding="utf-8",
        )
        (store / "skill-impact.md").write_text(
            "# Skill impact\n\n"
            "The accept/reject audit trail for skill-change proposals.\n\n",
            encoding="utf-8",
        )
        append_log(store, f"init {primary_root}")
        created = True

    # Register in known_projects.json
    register_project(primary_root)

    print(json.dumps({
        "primaryRoot": str(primary_root),
        "storePath": str(store),
        "created": created,
    }))
    return 0


def command_status(args: argparse.Namespace) -> int:
    store, primary_root = resolve_store_and_root(args)
    project_json = store / "project.json"
    if not project_json.exists():
        print(json.dumps({
            "present": False,
            "primaryRoot": str(primary_root),
            "storePath": str(store),
        }))
        return 0

    try:
        data = json.loads(project_json.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    raw_count = len([d for d in (store / "raw").iterdir() if d.is_dir() and not d.name.startswith(".")]) if (store / "raw").is_dir() else 0
    pattern_count = len(list((store / "patterns").glob("*.md"))) if (store / "patterns").is_dir() else 0
    proposal_count = len(list((store / "proposals").glob("*.json"))) if (store / "proposals").is_dir() else 0

    print(json.dumps({
        "present": True,
        "primaryRoot": str(primary_root),
        "storePath": str(store),
        "createdAt": data.get("createdAt"),
        "raw": raw_count,
        "patterns": pattern_count,
        "proposals": proposal_count,
    }))
    return 0


def command_record(args: argparse.Namespace) -> int:
    store, _ = resolve_store_and_root(args)
    if not (store / "project.json").exists():
        raise SiError(f"store does not exist at {store}; run init first")

    raw_id = args.id
    if not RAW_ID.match(raw_id):
        raise SiError(f"invalid raw trace id: {raw_id}")

    raw_dir = store / "raw" / raw_id
    if raw_dir.exists():
        raise SiError(f"raw trace {raw_id} already exists (traces are write-once)")

    kind = sanitize_line(args.kind)
    summary = sanitize_line(args.summary)
    model = sanitize_model_effort(args.model)
    effort = sanitize_model_effort(args.effort)

    files_to_copy = [Path(f).resolve() for f in args.file]
    for f in files_to_copy:
        if not f.is_file():
            raise SiError(f"file not found: {f}")
    seen_names: dict[str, Path] = {}
    for f in files_to_copy:
        if f.name in seen_names:
            raise SiError(
                f"duplicate evidence file name {f.name!r}: {seen_names[f.name]} and {f}"
                " would both be stored as files/" + f.name
            )
        seen_names[f.name] = f

    raw_parent = store / "raw"
    raw_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=raw_parent))

    try:
        files_dest = staging / "files"
        files_dest.mkdir(parents=True, exist_ok=True)
        manifest_files = []
        for src in files_to_copy:
            dest = files_dest / src.name
            shutil.copy2(src, dest)
            manifest_files.append({
                "path": f"files/{src.name}",
                "sha256": sha256_file(dest),
            })

        manifest = {
            "id": raw_id,
            "kind": kind,
            "recordedAt": now_utc(),
            "summary": summary,
            "files": manifest_files,
            "model": model,
            "effort": effort,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        staging.rename(raw_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    append_log(store, f"record {raw_id} ({kind}) — {summary}")
    print(raw_id)
    return 0


def command_pattern(args: argparse.Namespace) -> int:
    store, _ = resolve_store_and_root(args)
    if not (store / "project.json").exists():
        raise SiError(f"store does not exist at {store}; run init first")

    slug = args.slug
    if not KEY_PART.match(slug):
        raise SiError(f"invalid pattern slug: {slug}")

    note = sanitize_line(args.note)
    citations = []
    for raw_id in args.evidence:
        bundle = store / "raw" / raw_id
        if not bundle.is_dir():
            raise SiError(f"cited raw trace does not exist: {raw_id}")
        manifest_file = bundle / "manifest.json"
        manifest_data = None
        if manifest_file.is_file():
            try:
                manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        citations.append(format_citation(raw_id, manifest_data))

    pattern_file = store / "patterns" / f"{slug}.md"
    title = sanitize_line(args.title) if args.title else slug.replace("-", " ").capitalize()

    citation_str = ", ".join(citations)
    entry_line = f"- {today_utc()} — {citation_str} — {note}"

    if not pattern_file.exists():
        content = (
            f"# {title}\n\n"
            f"One failure mode or successful strategy of this project. Evidence accumulates below;\n"
            f"nothing already written here is rewritten to say something different.\n\n"
            f"## Evidence\n\n"
            f"{entry_line}\n"
        )
        pattern_file.write_text(content, encoding="utf-8")
    else:
        with pattern_file.open("a", encoding="utf-8") as handle:
            handle.write(entry_line + "\n")

    update_pattern_index(store)
    append_log(store, f"pattern {slug} — {', '.join(args.evidence)} — {note}")
    print(slug)
    return 0


def command_check(args: argparse.Namespace) -> int:
    store, _ = resolve_store_and_root(args)
    errors: list[str] = []

    if not (store / "project.json").is_file():
        errors.append(f"missing project.json in {store}")

    for req in ("index.md", "logs.md", "skill-impact.md"):
        if not (store / req).is_file():
            errors.append(f"missing {req} in {store}")

    for req_dir in ("raw", "patterns", "proposals"):
        if not (store / req_dir).is_dir():
            errors.append(f"missing directory {req_dir} in {store}")

    # Check for lingering staging directories
    if (store / "raw").is_dir():
        for item in (store / "raw").iterdir():
            if item.is_dir() and item.name.startswith(".staging-"):
                errors.append(f"unclean staging directory: {item}")

    # Validate raw bundles and manifests
    raw_ids = set()
    if (store / "raw").is_dir():
        for item in (store / "raw").iterdir():
            if not item.is_dir() or item.name.startswith("."):
                continue
            raw_ids.add(item.name)
            manifest_file = item / "manifest.json"
            if not manifest_file.is_file():
                errors.append(f"bundle {item.name} missing manifest.json")
                continue
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            except Exception as e:
                errors.append(f"bundle {item.name} invalid manifest.json: {e}")
                continue

            # Model and effort sanitization check
            for field in ("model", "effort"):
                val = manifest.get(field)
                if val is not None and SANITY_RE.search(str(val)):
                    errors.append(f"bundle {item.name} unsanitized {field}: {val!r}")

            # Verify files
            manifest_files = manifest.get("files", [])
            seen_files = set()
            for mf in manifest_files:
                rel_path = mf.get("path")
                expected_sha = mf.get("sha256")
                actual_file = item / rel_path
                seen_files.add(actual_file.resolve())
                if not actual_file.is_file():
                    errors.append(f"bundle {item.name} missing file {rel_path}")
                else:
                    actual_sha = sha256_file(actual_file)
                    if actual_sha != expected_sha:
                        errors.append(f"bundle {item.name} file {rel_path} checksum mismatch")

            files_dir = item / "files"
            if files_dir.is_dir():
                for real_file in files_dir.rglob("*"):
                    if real_file.is_file() and real_file.resolve() not in seen_files:
                        errors.append(f"bundle {item.name} unmanifested file {real_file.name}")

    # Validate logs.md
    if (store / "logs.md").is_file():
        logs_text = (store / "logs.md").read_text(encoding="utf-8")
        for line in logs_text.splitlines():
            if not line.startswith("- "):
                continue
            # Check recorded IDs
            match = re.search(r"record\s+([a-z0-9][a-z0-9._-]*)", line)
            if match:
                lid = match.group(1)
                if lid not in raw_ids:
                    errors.append(f"logs.md cites raw ID with no bundle: {lid}")

    # Validate patterns and index
    pattern_pages = {}
    if (store / "patterns").is_dir():
        for pfile in (store / "patterns").glob("*.md"):
            slug = pfile.stem
            lines = pfile.read_text(encoding="utf-8").splitlines()
            evidence_lines = [l for l in lines if l.startswith("- ")]
            last_date = ""
            for el in evidence_lines:
                parts = el.split("—")
                if len(parts) >= 3:
                    d = parts[0].strip().lstrip("-").strip()
                    if d > last_date:
                        last_date = d
                    cit_part = parts[1]
                    for match in CITATION_RE.finditer(cit_part):
                        cid = match.group(1)
                        tag = match.group(2)
                        if cid not in raw_ids:
                            errors.append(f"pattern {slug} cites missing raw ID: {cid}")
                        if tag and SANITY_RE.search(tag):
                            errors.append(f"pattern {slug} has unsanitized citation attribution: {tag!r}")
                else:
                    errors.append(f"pattern {slug} invalid evidence line: {el}")

            pattern_pages[slug] = (len(evidence_lines), last_date)

    if (store / "index.md").is_file():
        index_text = (store / "index.md").read_text(encoding="utf-8")
        index_rows = {}
        for line in index_text.splitlines():
            if line.startswith("| ["):
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 4:
                    match = re.search(r"\[([^\]]+)\]", parts[1])
                    if match:
                        slug = match.group(1)
                        try:
                            count = int(parts[2])
                        except ValueError:
                            count = -1
                        last_seen = parts[3]
                        index_rows[slug] = (count, last_seen)

        for slug, (count, last_date) in pattern_pages.items():
            if slug not in index_rows:
                errors.append(f"pattern {slug} has no row in index.md")
            else:
                icount, ilast = index_rows[slug]
                if icount != count:
                    errors.append(f"index.md row for {slug} count mismatch: {icount} != {count}")
                if ilast != last_date:
                    errors.append(f"index.md row for {slug} last_seen mismatch: {ilast} != {last_date}")

        for islug in index_rows:
            if islug not in pattern_pages:
                errors.append(f"index.md has row for nonexistent pattern: {islug}")

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print(json.dumps({
        "storePath": str(store),
        "ok": True,
        "raw": len(raw_ids),
        "patterns": len(pattern_pages),
    }))
    return 0


def create_proposal_file(proposals_dir: Path, base_id: str, explicit: bool) -> tuple[str, Path]:
    """Exclusively create a new proposal file, never overwriting an existing one."""
    suffix = 1
    while True:
        proposal_id = base_id if suffix == 1 else f"{base_id}-{suffix}"
        pfile = proposals_dir / f"{proposal_id}.json"
        try:
            fd = os.open(pfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            if explicit:
                raise SiError(f"proposal {proposal_id} already exists (proposals are never overwritten)")
            suffix += 1
            continue
        os.close(fd)
        return proposal_id, pfile


def command_propose(args: argparse.Namespace) -> int:
    is_apply_only = bool(args.apply and args.id and not (args.rule or args.title or args.pattern))
    proposal_id = validate_proposal_id(args.id, is_apply_only) if args.id is not None else None
    if args.skill_name is not None:
        validate_skill_name(args.skill_name)
    store, primary_root = resolve_store_and_root(args)
    if not (store / "project.json").exists():
        raise SiError(f"store does not exist at {store}; run init first")

    proposals_dir = store / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)

    target_kind = args.target or "agents-md"
    skill_name = args.skill_name

    if is_apply_only:
        # Applying an existing proposal
        pfile = proposals_dir / f"{proposal_id}.json"
        if not pfile.is_file():
            raise SiError(f"proposal not found: {proposal_id}")
        try:
            data = json.loads(pfile.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise SiError(f"invalid proposal {proposal_id}: {error}") from error
        if not isinstance(data, dict):
            raise SiError(f"invalid proposal {proposal_id}: expected a JSON object")
        if data.get("applied"):
            print(json.dumps({"message": f"proposal {proposal_id} already applied", "proposal": data}))
            return 0

        target = data.get("target", "agents-md")
        content = str(data.get("proposal", ""))
        if target == "agents-md":
            content = sanitize_line(content)
        title = sanitize_line(str(data.get("title", proposal_id))) or proposal_id

        if target == "agents-md":
            agents_md = primary_root / "AGENTS.md"
            rule_block = f"\n\n## {title}\n\n{content}\n"
            if agents_md.exists():
                with agents_md.open("a", encoding="utf-8") as h:
                    h.write(rule_block)
            else:
                agents_md.write_text(f"# Project Instructions\n{rule_block}", encoding="utf-8")
            target_file_str = "AGENTS.md"
        elif target == "skill":
            sname = validate_skill_name(data.get("skillName") or "custom-skill")
            sdir = primary_root / ".nova" / "skills" / sname
            sdir.mkdir(parents=True, exist_ok=True)
            (sdir / "SKILL.md").write_text(content, encoding="utf-8")
            target_file_str = f".nova/skills/{sname}/SKILL.md"
        else:
            raise SiError(f"unknown target: {target}")

        data["applied"] = True
        data["appliedAt"] = now_utc()
        pfile.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        append_skill_impact(store, f"applied proposal {proposal_id} to {target_file_str}: {title}")
        append_log(store, f"apply {proposal_id} to {target_file_str}")

        print(json.dumps({
            "applied": True,
            "id": proposal_id,
            "targetFile": target_file_str,
            "proposal": data,
        }))
        return 0

    # Creating a new proposal
    patterns_dir = store / "patterns"
    available_patterns = [p.stem for p in patterns_dir.glob("*.md")] if patterns_dir.is_dir() else []

    chosen_pattern = args.pattern
    if chosen_pattern:
        if chosen_pattern not in available_patterns:
            raise SiError(f"pattern {chosen_pattern} does not exist in store")
        cited_patterns = [chosen_pattern]
    else:
        cited_patterns = available_patterns

    explicit_id = bool(proposal_id)
    if not proposal_id:
        slug = chosen_pattern or "general"
        proposal_id = f"{today_utc()}-{slug}"

    # AGENTS.md rules are folded to one line; a skill's text is the whole SKILL.md, kept verbatim.
    content = args.rule or ""
    if target_kind == "agents-md":
        content = sanitize_line(content)
    if not content.strip():
        if chosen_pattern:
            ptext = (patterns_dir / f"{chosen_pattern}.md").read_text(encoding="utf-8")
            content = f"Apply project mitigation for pattern `{chosen_pattern}`."
        else:
            content = "Standardize project conventions based on observed run patterns."

    if target_kind == "skill" and not skill_name:
        skill_name = chosen_pattern or "project-skill"

    proposal_id, pfile = create_proposal_file(proposals_dir, proposal_id, explicit_id)
    title = sanitize_line(args.title) if args.title else ""
    title = title or f"Adaptation rule from {proposal_id}"

    proposal_data = {
        "id": proposal_id,
        "createdAt": now_utc(),
        "target": target_kind,
        "skillName": skill_name if target_kind == "skill" else None,
        "title": title,
        "patterns": cited_patterns,
        "proposal": content,
        "applied": False,
        "appliedAt": None,
    }

    pfile.write_text(json.dumps(proposal_data, indent=2) + "\n", encoding="utf-8")
    append_log(store, f"propose {proposal_id} — {title}")

    if args.apply:
        if target_kind == "agents-md":
            agents_md = primary_root / "AGENTS.md"
            rule_block = f"\n\n## {title}\n\n{content}\n"
            if agents_md.exists():
                with agents_md.open("a", encoding="utf-8") as h:
                    h.write(rule_block)
            else:
                agents_md.write_text(f"# Project Instructions\n{rule_block}", encoding="utf-8")
            target_file_str = "AGENTS.md"
        elif target_kind == "skill":
            sdir = primary_root / ".nova" / "skills" / skill_name
            sdir.mkdir(parents=True, exist_ok=True)
            (sdir / "SKILL.md").write_text(content, encoding="utf-8")
            target_file_str = f".nova/skills/{skill_name}/SKILL.md"

        proposal_data["applied"] = True
        proposal_data["appliedAt"] = now_utc()
        pfile.write_text(json.dumps(proposal_data, indent=2) + "\n", encoding="utf-8")

        append_skill_impact(store, f"applied proposal {proposal_id} to {target_file_str}: {title}")
        append_log(store, f"apply {proposal_id} to {target_file_str}")

    print(json.dumps({
        "id": proposal_id,
        "title": title,
        "target": target_kind,
        "proposal": content,
        "applied": proposal_data["applied"],
    }))
    return 0


def command_resolve_root(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve() if getattr(args, "repo", None) else Path.cwd().resolve()
    primary = resolve_toplevel(repo, fallback_dir=True)
    print(str(primary))
    return 0


def command_register(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve() if getattr(args, "repo", None) else Path.cwd().resolve()
    primary = resolve_toplevel(repo, fallback_dir=True)
    refuse_eval_mode(repo, primary)
    reg_path = Path(args.registry).resolve() if getattr(args, "registry", None) else get_registry_path()
    register_project(primary, reg_path)
    print(json.dumps({
        "registered": str(primary),
        "registry": str(reg_path),
    }))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="subcommand", required=True)

    init_p = sub.add_parser("init", help="Initialize in-repo store")
    init_p.add_argument("--repo", default=".", help="Target repository or workspace")
    init_p.add_argument("--store", help="Explicit store path override")

    status_p = sub.add_parser("status", help="Check store status")
    status_p.add_argument("--repo", default=".", help="Target repository or workspace")
    status_p.add_argument("--store", help="Explicit store path override")

    record_p = sub.add_parser("record", help="Record raw trace bundle")
    record_p.add_argument("--repo", default=".", help="Target repository or workspace")
    record_p.add_argument("--store", help="Explicit store path override")
    record_p.add_argument("--id", required=True, help="Unique raw trace ID")
    record_p.add_argument("--kind", required=True, help="Trace kind (e.g. build-wave)")
    record_p.add_argument("--summary", required=True, help="One-line summary")
    record_p.add_argument("--file", action="append", required=True, help="Evidence file (repeatable)")
    record_p.add_argument("--model", help="Model attribution")
    record_p.add_argument("--effort", help="Effort attribution")

    pattern_p = sub.add_parser("pattern", help="Append evidence to pattern page")
    pattern_p.add_argument("--repo", default=".", help="Target repository or workspace")
    pattern_p.add_argument("--store", help="Explicit store path override")
    pattern_p.add_argument("slug", help="Pattern slug")
    pattern_p.add_argument("--evidence", action="append", required=True, help="Cited raw trace ID (repeatable)")
    pattern_p.add_argument("--note", required=True, help="One-line note or lesson")
    pattern_p.add_argument("--title", help="Optional title for new pattern")

    check_p = sub.add_parser("check", help="Verify store integrity")
    check_p.add_argument("--repo", default=".", help="Target repository or workspace")
    check_p.add_argument("--store", help="Explicit store path override")

    propose_p = sub.add_parser("propose", help="Synthesize or apply improvement proposals")
    propose_p.add_argument("--repo", default=".", help="Target repository or workspace")
    propose_p.add_argument("--store", help="Explicit store path override")
    propose_p.add_argument("--id", help="Proposal ID")
    propose_p.add_argument("--pattern", help="Pattern slug to focus on")
    propose_p.add_argument("--title", help="Proposal title")
    propose_p.add_argument("--target", choices=["agents-md", "skill"], default="agents-md", help="Proposal target")
    propose_p.add_argument("--skill-name", help="Skill name if target is skill")
    propose_p.add_argument("--rule", "--content", dest="rule", help="Proposal rule content")
    propose_p.add_argument("--apply", action="store_true", help="Apply proposal to target file")

    root_p = sub.add_parser("resolve-root", help="Resolve primary repository root")
    root_p.add_argument("--repo", default=".", help="Target repository or workspace")

    reg_p = sub.add_parser("register", help="Register repository in global registry")
    reg_p.add_argument("--repo", default=".", help="Target repository or workspace")
    reg_p.add_argument("--registry", help="Explicit registry path")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    handlers = {
        "init": command_init,
        "status": command_status,
        "record": command_record,
        "pattern": command_pattern,
        "check": command_check,
        "propose": command_propose,
        "resolve-root": command_resolve_root,
        "register": command_register,
    }
    handler = handlers.get(args.subcommand)
    if not handler:
        parser.print_help()
        return 1

    try:
        return handler(args)
    except SiError as err:
        print(f"si error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
