#!/usr/bin/env python3
"""The persistent per-project knowledge store, and its only writer.

One store lives outside every repository — `$NOVA_WIKI_HOME`, defaulting to
`~/.nova/wiki/` — with one namespace per project at `<root>/<project-key>/`. This
script is the only thing that writes into a namespace: an agent that edits a page with an
editor tool bypasses the write-once, append-only, and identity rules enforced here.

    wiki.py key      [--repo <dir> | --namespace <dir>]
    wiki.py init     [--repo <dir> | --namespace <dir>]
    wiki.py status   [--repo <dir> | --namespace <dir>]
    wiki.py record   --id <id> --kind <kind> --summary <text> --file <path> [--file ...] [--model <model>] [--effort <effort>]
    wiki.py pattern  <slug> --evidence <raw-id> [--evidence ...] --note <text> [--title <text>]
    wiki.py check    [--repo <dir> | --namespace <dir>]

`--repo` names the *target repository* (default the working directory); the project key,
the eval-mode marker, and the identity check are all read from it. `--namespace` names a
namespace directory outright, bypassing both resolutions, for the shipped demonstration
and the tests. Nothing here deletes: there is no reset and no rollback, `record` refuses
an id it already wrote, and `check` re-hashes every recorded file against its manifest.

The artifact contract — key derivation, page shapes, and the rule that a pattern page
accumulates evidence rather than being rewritten — is
`skills/wiki/references/wiki-layout.md`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

KEY_PART = re.compile(r"^[a-z0-9][a-z0-9-]*$")
RAW_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")
USERINFO = re.compile(r"^[^/@]*@")
REMOTE_PARTS = re.compile(r"^([^/:]+)(?::(\d+))?[:/]?(.*)$")
# `- <date> — <citations> — <prose>`: the citations are read out of their own field, so
# a backtick in the prose cannot forge one.
EVIDENCE_LINE = re.compile(r"^-\s+(\d{4}-\d{2}-\d{2})\s+—\s+(.*?)\s+—\s+\S")
CITATION = re.compile(r"`([^`]+)`")
CITATION_ITEM = re.compile(r"^`([^`]+)`(?:\s*\[([^\]]*)\])?$")
INDEX_ROW = re.compile(r"^\|\s*\[?([a-z0-9][a-z0-9-]*)\]?")
# `- <timestamp> record <id> (<kind>) — <summary>`, anchored so a summary cannot forge one.
LOGGED_RECORD = re.compile(r"^-\s+\S+\s+record\s+(\S+)\s+\(")

LAYOUT_DIRS = ("raw", "patterns")
STAGING_PREFIX = ".staging-"

INDEX_HEADING = "# Pattern index\n\nOne row per pattern page.\n\n"
INDEX_COLUMNS = "| Pattern | Occurrences | Last seen |\n| --- | ---: | --- |\n"
LOGS_TEXT = (
    "# Evolution log\n\n"
    "One line per write to this namespace, oldest first. Appended by `wiki.py`; never\n"
    "edited.\n\n"
)
SKILL_IMPACT_TEXT = (
    "# Skill impact\n\n"
    "The accept/reject audit trail for skill-change proposals. Nothing writes an entry\n"
    "in v1 — this file exists so the trail has one home from the start. The entry shape\n"
    "is in `skills/wiki/references/wiki-layout.md`.\n"
)
PAGE_PREAMBLE = (
    "One failure mode or successful strategy of this project. Evidence accumulates "
    "below;\nnothing already written here is rewritten to say something different.\n\n"
    "## Evidence\n\n"
)


class WikiError(Exception):
    """A refusal the operator is meant to read: printed, then exit non-zero."""


# --- small helpers ------------------------------------------------------------------


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def run_result(
    argv: list[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str] | None:
    """The completed process, or None when the binary is not there to run.

    `LC_ALL=C` because a diagnostic is read here, not just an exit code, and git
    translates its messages.
    """
    try:
        return subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            env={**os.environ, "LC_ALL": "C"},
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None


def run(argv: list[str], cwd: Path | None = None) -> str | None:
    """stdout of a successful command, or None — never a raised CalledProcessError."""
    result = run_result(argv, cwd)
    if result is None or result.returncode != 0:
        return None
    return result.stdout


def read_json(path: Path, what: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WikiError(f"cannot read {what} at {path}: {error}") from error
    if not isinstance(value, dict):
        raise WikiError(f"{what} at {path} must be a JSON object")
    return value


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_if_absent(path: Path, text: str) -> bool:
    """Create the file, or leave an existing one byte-identical. `init` is idempotent."""
    if path.exists():
        return False
    path.write_text(text, encoding="utf-8")
    return True


def one_line(text: str) -> str:
    """Every field the CLI writes into a page or a log is folded to one line, so no
    argument can smuggle a second line into an append-only file."""
    return " ".join(text.split())


def is_sanitized_string(val: object) -> bool:
    """Validate that val is a sanitized single-line string without newlines, tabs, or carriage returns."""
    if not isinstance(val, str):
        return False
    if any(ch in val for ch in ("\n", "\r", "\t")):
        return False
    if val != one_line(val):
        return False
    return bool(val.strip())


def append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(one_line(line) + "\n")


# --- the project key ------------------------------------------------------------------


def key_part(text: str) -> str:
    """The character class `nova-ws` enforces: `[a-z0-9][a-z0-9-]*`, no separator."""
    reduced = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return reduced


def find_up(start: Path, name: str) -> Path | None:
    for directory in (start, *start.parents):
        if (directory / name).exists():
            return directory
    return None


def resolve_toplevel(repo: Path) -> Path:
    """The repository's *primary* toplevel, resolved exactly as `nova-ws` does.

    A secondary jj workspace carries a `.jj/repo` *file* holding the path of the
    primary's `.jj/repo`; a git worktree is named by the first `git worktree list
    --porcelain` entry. Either indirection is what makes every per-issue workspace of one
    repository answer with one key.
    """
    if not repo.is_dir():
        raise WikiError(f"no such directory: {repo}")
    workspace = find_up(repo, ".jj")
    if workspace is not None:
        pointer = workspace / ".jj" / "repo"
        if pointer.is_dir():
            return workspace.resolve()
        try:
            target = pointer.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise WikiError(
                f"cannot resolve the primary workspace of {workspace}: {error}"
            ) from error
        return (workspace / ".jj" / target).parent.parent.resolve()
    listed = run_result(["git", "worktree", "list", "--porcelain"], cwd=repo)
    first = (listed.stdout if listed else "").splitlines()[:1]
    if not first or not first[0].startswith("worktree "):
        complaint = (listed.stderr or "").strip() if listed else "git is not installed"
        raise WikiError(
            f"not a jj or git repository: {repo}"
            + (f" ({complaint.splitlines()[-1]})" if complaint else "")
        )
    return Path(first[0][len("worktree ") :]).resolve()


def has_git_repository(toplevel: Path) -> bool:
    """A `.git` directory or file for an ordinary checkout or worktree, and the loose
    contents of a bare repository, which has no `.git` of its own."""
    if (toplevel / ".git").exists():
        return True
    return (toplevel / "HEAD").is_file() and (toplevel / "objects").is_dir()


def origin_url(toplevel: Path) -> str | None:
    """The `origin` remote, asked of git first and of jj where git cannot answer.

    A git repository that *cannot* answer — dubious ownership, an unreadable config — is an
    error rather than "no origin": keying it by path instead would quietly open a second
    namespace for a project that already has one.
    """
    git = run_result(["git", "-C", str(toplevel), "remote", "get-url", "origin"])
    if git is not None and git.returncode == 0 and git.stdout.strip():
        return git.stdout.strip()
    if (
        git is not None
        and git.returncode not in (0, 2)
        and has_git_repository(toplevel)
    ):
        # Exit 2 is git's "no such remote"; the message is checked too, in case a future
        # git spells that outcome with a different code.
        complaint = (git.stderr or "").strip()
        if "no such remote" not in complaint.lower():
            raise WikiError(
                f"git could not read the remotes of {toplevel}, so the project key "
                f"cannot be derived: {complaint or f'git exited {git.returncode}'}"
            )
    listed = run(
        ["jj", "-R", str(toplevel), "--ignore-working-copy", "git", "remote", "list"]
    )
    for line in (listed or "").splitlines():
        name, _, remainder = line.partition(" ")
        if name == "origin" and remainder.strip():
            return remainder.strip()
    return None


def normalize_remote(url: str) -> str:
    """`git@github.com:anvil008/nova.git` and `https://github.com/anvil008/nova`
    are one project, so both collapse to `github-com-anvil008-nova`."""
    text = SCHEME.sub("", url.strip())
    text = USERINFO.sub("", text)
    text = text.removesuffix(".git")
    match = REMOTE_PARTS.match(text)
    if not match:
        return key_part(text)
    host, _port, path = match.group(1), match.group(2), match.group(3)
    return key_part(f"{host}-{path}")


def derive_key(toplevel: Path) -> tuple[str, str, str]:
    """(project key, source, what it was derived from) for one primary toplevel."""
    url = origin_url(toplevel)
    if url:
        key = normalize_remote(url)
        if KEY_PART.match(key):
            return key, "remote", url
        raise WikiError(
            f"the origin remote {url!r} of {toplevel} does not reduce to a usable "
            "project key; give the namespace a --namespace path instead"
        )
    digest = hashlib.sha256(str(toplevel).encode("utf-8")).hexdigest()[:8]
    key = f"{key_part(toplevel.name) or 'repository'}-{digest}"
    return key, "path", str(toplevel)


# --- the store ------------------------------------------------------------------------


def store_root() -> Path:
    configured = os.environ.get("NOVA_WIKI_HOME", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".nova" / "wiki"


class Target:
    """Which namespace a subcommand acts on, and what the repository behind it resolves
    to. `--namespace` leaves `repo` unset: no key derivation, no eval-mode marker, and no
    identity check, which is what makes the shipped demonstration runnable anywhere."""

    def __init__(
        self,
        namespace: Path,
        *,
        repo: Path | None = None,
        project_key: str | None = None,
        source: str | None = None,
        derived_from: str | None = None,
    ) -> None:
        self.namespace = namespace
        self.repo = repo
        self.project_key = project_key or namespace.name
        self.source = source or "namespace"
        self.derived_from = derived_from or str(namespace)

    @property
    def direct(self) -> bool:
        return self.repo is None

    @property
    def identity(self) -> Path:
        return self.namespace / "project.json"


def refuse_eval_mode(repo: Path, toplevel: Path) -> None:
    """A benchmark run neither records into nor reads from a persistent namespace. The
    marker is read from the repository `--repo` names, never from the store."""
    for candidate in dict.fromkeys((repo, toplevel)):
        marker = candidate / ".nova" / "eval-mode.json"
        if marker.is_file():
            raise WikiError(
                f"refusing: {candidate} is in eval mode ({marker}). A repository in "
                "eval mode neither records into nor consolidates a wiki namespace; "
                "leaving eval mode is a human act."
            )


def resolve_target(args: argparse.Namespace) -> Target:
    if args.namespace:
        # Recorded as typed, so a namespace shipped for a demonstration carries a
        # portable path rather than the absolute one of whoever generated it.
        return Target(
            Path(args.namespace).expanduser().resolve(), derived_from=args.namespace
        )
    repo = Path(args.repo).expanduser().resolve()
    toplevel = resolve_toplevel(repo)
    refuse_eval_mode(repo, toplevel)
    key, source, derived_from = derive_key(toplevel)
    return Target(
        store_root() / key,
        repo=toplevel,
        project_key=key,
        source=source,
        derived_from=derived_from,
    )


def assert_identity(target: Target) -> None:
    """Collisions are refused, not resolved: a namespace answers only to the repository
    it was created for, and a mismatch names both sources."""
    if target.direct or not target.identity.is_file():
        return
    recorded = read_json(target.identity, "project.json")
    same_key = recorded.get("projectKey") == target.project_key
    same_source = recorded.get("derivedFrom") == target.derived_from
    if same_key and same_source:
        return
    raise WikiError(
        f"refusing: the namespace at {target.namespace} was created for project "
        f"{recorded.get('projectKey')!r} derived from "
        f"{recorded.get('derivedFrom')!r}, but {target.repo} resolves to project "
        f"{target.project_key!r} derived from {target.derived_from!r}. Renaming or "
        "retiring a namespace is a human act."
    )


def require_namespace(target: Target) -> Path:
    if not target.identity.is_file():
        raise WikiError(
            f"no namespace at {target.namespace}: run `wiki.py init` for this project "
            "first (a project that never opted in is not an error, it is untracked)"
        )
    return target.namespace


# --- pages ----------------------------------------------------------------------------


def evidence_entries(page: str) -> list[tuple[str, list[str]]]:
    """(date, cited raw ids) for every evidence line of a pattern page."""
    entries = []
    for line in page.splitlines():
        match = EVIDENCE_LINE.match(line.strip())
        if match:
            entries.append((match.group(1), CITATION.findall(match.group(2))))
    return entries


def index_state(namespace: Path) -> dict[str, tuple[int, str]]:
    """slug -> (occurrences, last seen), computed from the pattern pages themselves, so
    the catalog is derived rather than accumulated out of step with what it catalogs."""
    state: dict[str, tuple[int, str]] = {}
    for page in sorted((namespace / "patterns").glob("*.md")):
        entries = evidence_entries(page.read_text(encoding="utf-8"))
        last_seen = max((date for date, _ in entries), default="—")
        state[page.stem] = (len(entries), last_seen)
    return state


def write_index(namespace: Path) -> None:
    rows = "".join(
        f"| [{slug}](patterns/{slug}.md) | {count} | {last_seen} |\n"
        for slug, (count, last_seen) in sorted(index_state(namespace).items())
    )
    (namespace / "index.md").write_text(
        INDEX_HEADING + INDEX_COLUMNS + rows, encoding="utf-8"
    )


def index_rows(namespace: Path) -> dict[str, str]:
    """slug -> the row that names it, as `index.md` currently reads."""
    rows: dict[str, str] = {}
    for line in (namespace / "index.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("| ---"):
            continue
        match = INDEX_ROW.match(line)
        if match:
            rows[match.group(1)] = line
    return rows


def log(namespace: Path, message: str) -> None:
    append_line(namespace / "logs.md", f"- {now()} {message}")


# --- subcommands ----------------------------------------------------------------------


def command_key(target: Target) -> int:
    if target.direct:
        recorded = (
            read_json(target.identity, "project.json")
            if target.identity.is_file()
            else {}
        )
        payload = {
            "projectKey": recorded.get("projectKey", target.project_key),
            "source": recorded.get("source", target.source),
            "derivedFrom": recorded.get("derivedFrom", target.derived_from),
        }
    else:
        payload = {
            "projectKey": target.project_key,
            "source": target.source,
            "derivedFrom": target.derived_from,
        }
    print(json.dumps(payload))
    return 0


def command_init(target: Target) -> int:
    assert_identity(target)
    namespace = target.namespace
    namespace.mkdir(parents=True, exist_ok=True)
    for name in LAYOUT_DIRS:
        (namespace / name).mkdir(exist_ok=True)
    created = write_if_absent(
        target.identity,
        json.dumps(
            {
                "projectKey": target.project_key,
                "source": target.source,
                "derivedFrom": target.derived_from,
                "createdAt": now(),
            },
            indent=2,
        )
        + "\n",
    )
    write_if_absent(namespace / "index.md", INDEX_HEADING + INDEX_COLUMNS)
    write_if_absent(namespace / "logs.md", LOGS_TEXT)
    write_if_absent(namespace / "skill-impact.md", SKILL_IMPACT_TEXT)
    if created:
        log(namespace, f"init {target.project_key} ({target.source})")
    print(
        json.dumps(
            {
                "projectKey": target.project_key,
                "namespace": str(namespace),
                "created": created,
            }
        )
    )
    return 0


def command_status(target: Target) -> int:
    payload: dict[str, object] = {"projectKey": target.project_key, "present": False}
    if not target.identity.is_file():
        payload["namespace"] = str(target.namespace)
        print(json.dumps(payload))
        return 0
    assert_identity(target)
    recorded = read_json(target.identity, "project.json")
    namespace = target.namespace
    payload.update(
        {
            "projectKey": recorded.get("projectKey", target.project_key),
            "present": True,
            "namespace": str(namespace),
            "source": recorded.get("source"),
            "derivedFrom": recorded.get("derivedFrom"),
            "createdAt": recorded.get("createdAt"),
            "raw": len(raw_bundles(namespace)),
            "patterns": len(index_state(namespace)),
        }
    )
    print(json.dumps(payload))
    return 0


def command_record(target: Target, args: argparse.Namespace) -> int:
    raw_id = (args.raw_id or "").strip()
    if not RAW_ID.match(raw_id):
        raise WikiError(
            f"refusing the raw id {raw_id!r}: an id is lower-case letters, digits, "
            "dashes, dots, and underscores, starting with a letter or a digit"
        )
    kind, summary = one_line(args.kind or ""), one_line(args.summary or "")
    for field, value in (("--kind", kind), ("--summary", summary)):
        if not value:
            raise WikiError(f"record needs {field}")
    if not args.files:
        raise WikiError("record needs at least one --file to copy into the bundle")
    sources = [Path(name).expanduser() for name in args.files]
    for source in sources:
        if not source.is_file():
            raise WikiError(f"no such evidence file: {source}")

    model = one_line(args.model) if args.model is not None else None
    if model == "":
        model = None
    effort = one_line(args.effort) if args.effort is not None else None
    if effort == "":
        effort = None

    assert_identity(target)
    namespace = require_namespace(target)
    bundle = namespace / "raw" / raw_id
    if bundle.exists():
        raise WikiError(
            f"refusing: the raw trace {raw_id!r} is already recorded at {bundle}. A raw "
            "bundle is written once and never rewritten; record the new evidence under "
            "a new id."
        )

    try:
        staging = Path(tempfile.mkdtemp(dir=namespace / "raw", prefix=STAGING_PREFIX))
    except OSError as error:
        raise WikiError(
            f"cannot stage a raw bundle under {namespace}: {error}"
        ) from error
    staged = False
    try:
        files_dir = staging / "files"
        files_dir.mkdir()
        entries = []
        taken: set[str] = set()
        for source in sources:
            name = source.name
            stem, suffix = Path(name).stem, Path(name).suffix
            index = 1
            while name in taken:
                name = f"{stem}-{index}{suffix}"
                index += 1
            taken.add(name)
            shutil.copy2(source, files_dir / name)
            entries.append(
                {
                    "path": f"files/{name}",
                    "sha256": sha256_file(files_dir / name),
                }
            )
        write_json(
            staging / "manifest.json",
            {
                "id": raw_id,
                "kind": kind,
                "recordedAt": now(),
                "summary": summary,
                "files": sorted(entries, key=lambda entry: entry["path"]),
                "model": model,
                "effort": effort,
            },
        )
        staging.rename(bundle)
        staged = True
    except OSError as error:
        raise WikiError(
            f"could not write the raw bundle {raw_id!r} at {bundle}: {error}"
        ) from error
    finally:
        if not staged:
            shutil.rmtree(staging, ignore_errors=True)

    log(namespace, f"record {raw_id} ({kind}) — {summary}")
    print(raw_id)
    return 0


def command_pattern(target: Target, args: argparse.Namespace) -> int:
    slug = (args.slug or "").strip()
    if not KEY_PART.match(slug):
        raise WikiError(
            f"refusing the slug {slug!r}: a slug is lower-case letters, digits, and "
            "dashes, starting with a letter or a digit"
        )
    note = one_line(args.note or "")
    if not note:
        raise WikiError("pattern needs --note: the prose this evidence is filed under")
    if not args.evidence:
        raise WikiError(
            "pattern needs at least one --evidence: a page cites the raw bundles it was "
            "read from"
        )

    cited = list(dict.fromkeys(args.evidence))
    for raw_id in cited:
        if not RAW_ID.match(raw_id):
            raise WikiError(f"refusing the evidence id {raw_id!r}: it is not a raw id")

    assert_identity(target)
    namespace = require_namespace(target)
    for raw_id in cited:
        if not (namespace / "raw" / raw_id).is_dir():
            raise WikiError(
                f"no raw bundle {raw_id!r} under {namespace / 'raw'}: record the "
                "evidence before citing it"
            )

    page = namespace / "patterns" / f"{slug}.md"
    if not page.exists():
        # Folded to one line like every other field: a heading spanning two lines could
        # otherwise carry a second one that reads as an evidence entry nothing recorded.
        title = one_line(args.title or "") or slug.replace("-", " ").capitalize()
        page.write_text(f"# {title}\n\n{PAGE_PREAMBLE}", encoding="utf-8")
    citation_parts = []
    for raw_id in cited:
        manifest_path = namespace / "raw" / raw_id / "manifest.json"
        model = None
        effort = None
        if manifest_path.is_file():
            try:
                manifest = read_json(manifest_path, "manifest.json")
                model = manifest.get("model")
                effort = manifest.get("effort")
            except WikiError:
                pass
        if model:
            if effort:
                citation_parts.append(f"`{raw_id}` [{model}·{effort}]")
            else:
                citation_parts.append(f"`{raw_id}` [{model}]")
        else:
            citation_parts.append(f"`{raw_id}`")
    citations = ", ".join(citation_parts)
    append_line(page, f"- {today()} — {citations} — {note}")
    write_index(namespace)
    log(namespace, f"pattern {slug} — {citations.replace('`', '')} — {note}")
    print(slug)
    return 0


def raw_bundles(namespace: Path) -> list[Path]:
    return sorted(
        path
        for path in (namespace / "raw").iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )


def check_ledger(namespace: Path) -> list[str]:
    """`logs.md` is the only record of what was *ever* written, so it is what catches a
    bundle deleted wholesale — nothing else would miss one no page happens to cite."""
    problems: list[str] = []
    for line in (namespace / "logs.md").read_text(encoding="utf-8").splitlines():
        match = LOGGED_RECORD.match(line.strip())
        if match and not (namespace / "raw" / match.group(1)).is_dir():
            problems.append(
                f"{match.group(1)}: logs.md records it, but there is no bundle under "
                "raw/ — nothing here deletes, so it was removed out of band"
            )
    for path in sorted((namespace / "raw").iterdir()):
        if path.name.startswith(STAGING_PREFIX):
            problems.append(
                f"{path.name}: a raw bundle left half-staged by an interrupted record; "
                "it holds no manifest, and it is the one thing here safe to delete"
            )
    return problems


def check_raw(namespace: Path) -> list[str]:
    """Re-hash every recorded file against its manifest: the immutability proof."""
    problems: list[str] = []
    for bundle in raw_bundles(namespace):
        manifest_path = bundle / "manifest.json"
        if not manifest_path.is_file():
            problems.append(f"{bundle.name}: no manifest.json in the raw bundle")
            continue
        try:
            manifest = read_json(manifest_path, "manifest.json")
        except WikiError as error:
            problems.append(f"{bundle.name}: {error}")
            continue
        entries = manifest.get("files")
        if not isinstance(entries, list):
            problems.append(f"{bundle.name}: manifest.json lists no files")
            continue
        listed = set()
        for entry in entries:
            relative = entry.get("path") if isinstance(entry, dict) else None
            if not isinstance(relative, str):
                problems.append(f"{bundle.name}: a manifest entry has no path")
                continue
            listed.add(relative)
            copied = bundle / relative
            if not copied.is_file():
                problems.append(
                    f"{bundle.name}: {relative} is listed in manifest.json but missing "
                    "from the bundle"
                )
            elif sha256_file(copied) != entry.get("sha256"):
                problems.append(
                    f"{bundle.name}: {relative} no longer matches the sha256 recorded "
                    "for it in manifest.json — a raw trace was mutated after it was "
                    "written"
                )
        for path in sorted(bundle.rglob("*")):
            relative = path.relative_to(bundle).as_posix()
            if (
                path.is_file()
                and relative != "manifest.json"
                and relative not in listed
            ):
                problems.append(
                    f"{bundle.name}: {relative} is in the bundle but not in "
                    "manifest.json"
                )
        for field in ("model", "effort"):
            val = manifest.get(field)
            if val is not None and not is_sanitized_string(val):
                problems.append(
                    f"{bundle.name}: manifest.json has unsanitized {field}: {val!r}"
                )
    return problems


def check_patterns(namespace: Path) -> list[str]:
    problems: list[str] = []
    rows = index_rows(namespace)
    computed = index_state(namespace)
    for slug, (count, last_seen) in sorted(computed.items()):
        row = rows.get(slug)
        if row is None:
            problems.append(
                f"{slug}: the pattern page has no row in index.md — the catalog drifted "
                "from what it catalogs"
            )
        elif f"| {count} |" not in row or last_seen not in row:
            problems.append(
                f"{slug}: index.md records {row.strip()!r}, but the page carries "
                f"{count} evidence entries, last seen {last_seen}"
            )
        page = (namespace / "patterns" / f"{slug}.md").read_text(encoding="utf-8")
        for line in page.splitlines():
            line_str = line.strip()
            if not line_str.startswith("- "):
                continue
            match = EVIDENCE_LINE.match(line_str)
            if not match:
                continue
            citations_field = match.group(2)
            parts = [p.strip() for p in citations_field.split(",")]
            for part in parts:
                if not part:
                    problems.append(
                        f"{slug}: empty citation in evidence line: {line_str!r}"
                    )
                    continue
                c_match = CITATION_ITEM.match(part)
                if not c_match:
                    problems.append(
                        f"{slug}: cites {part!r}, which is not a valid citation"
                    )
                    continue
                raw_id, tag = c_match.group(1), c_match.group(2)
                if not RAW_ID.match(raw_id):
                    problems.append(
                        f"{slug}: cites {raw_id}, which is not a raw id — a citation "
                        "names a bundle under raw/, not a path"
                    )
                elif not (namespace / "raw" / raw_id).is_dir():
                    problems.append(
                        f"{slug}: cites the raw id {raw_id}, which has no directory "
                        "under raw/"
                    )
                if tag is not None:
                    if any(ch in tag for ch in ("\n", "\r", "\t")):
                        problems.append(
                            f"{slug}: citation tag [{tag}] for raw id {raw_id!r} contains unsanitized characters"
                        )
                    elif "·" in tag:
                        if tag.count("·") > 1:
                            problems.append(
                                f"{slug}: citation tag [{tag}] for raw id {raw_id!r} has invalid middle dot format"
                            )
                        else:
                            model, _, effort = tag.partition("·")
                            if not is_sanitized_string(model):
                                problems.append(
                                    f"{slug}: citation tag [{tag}] for raw id {raw_id!r} has unsanitized model: {model!r}"
                                )
                            if not is_sanitized_string(effort):
                                problems.append(
                                    f"{slug}: citation tag [{tag}] for raw id {raw_id!r} has unsanitized effort: {effort!r}"
                                )
                    else:
                        model = tag
                        if not is_sanitized_string(model):
                            problems.append(
                                f"{slug}: citation tag [{tag}] for raw id {raw_id!r} has unsanitized model: {model!r}"
                            )
    for slug in sorted(set(rows) - set(computed)):
        problems.append(f"{slug}: index.md carries a row with no page under patterns/")
    return problems


def command_check(target: Target) -> int:
    assert_identity(target)
    namespace = require_namespace(target)
    for name in LAYOUT_DIRS:
        if not (namespace / name).is_dir():
            raise WikiError(f"the namespace at {namespace} has no {name}/ directory")
    for name in ("index.md", "logs.md", "skill-impact.md"):
        if not (namespace / name).is_file():
            raise WikiError(f"the namespace at {namespace} has no {name}")

    problems = (
        check_ledger(namespace) + check_raw(namespace) + check_patterns(namespace)
    )
    if problems:
        print(
            f"wiki.py check: {len(problems)} problem(s) in {namespace}", file=sys.stderr
        )
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "namespace": str(namespace),
                "ok": True,
                "raw": len(raw_bundles(namespace)),
                "patterns": len(index_state(namespace)),
            }
        )
    )
    return 0


# --- entry point ----------------------------------------------------------------------


def _common(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """The two ways every subcommand is pointed at a namespace."""
    parser.add_argument(
        "--repo",
        default=".",
        help="the target repository (default: the working directory)",
    )
    parser.add_argument(
        "--namespace",
        default=None,
        help="a namespace directory outright, bypassing key and eval-mode resolution",
    )
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wiki.py", description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    _common(subcommands.add_parser("key", help="print the resolved project key"))
    _common(subcommands.add_parser("init", help="create the namespace, idempotently"))
    _common(subcommands.add_parser("status", help="report whether a namespace exists"))
    _common(subcommands.add_parser("check", help="re-hash and re-link the namespace"))

    record = _common(
        subcommands.add_parser("record", help="write one raw bundle, once")
    )
    record.add_argument("--id", dest="raw_id", default=None)
    record.add_argument("--kind", default=None)
    record.add_argument("--summary", default=None)
    record.add_argument("--file", dest="files", action="append", default=[])
    record.add_argument("--model", default=None, help="the model string that produced the trace")
    record.add_argument("--effort", default=None, help="the reasoning effort level (e.g. low, medium, high)")

    pattern = _common(
        subcommands.add_parser("pattern", help="append evidence to a pattern page")
    )
    pattern.add_argument("slug")
    pattern.add_argument("--evidence", dest="evidence", action="append", default=[])
    pattern.add_argument("--note", default=None)
    pattern.add_argument("--title", default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        target = resolve_target(args)
        if args.command == "key":
            return command_key(target)
        if args.command == "init":
            return command_init(target)
        if args.command == "status":
            return command_status(target)
        if args.command == "record":
            return command_record(target, args)
        if args.command == "pattern":
            return command_pattern(target, args)
        return command_check(target)
    except WikiError as error:
        print(f"wiki.py {args.command}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
