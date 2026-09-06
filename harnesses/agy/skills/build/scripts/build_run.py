#!/usr/bin/env python3
"""Prepare, verify, accept, and resume local Jujutsu integration rounds.

The ledger and evidence live outside working copies. Integrators prepare a
candidate; orchestrators accept it. Neither operation pushes or closes issues.
Requires Python 3.10+ and jj with `duplicate --onto` (tested with jj 0.45).
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

import plan_sidecar
import waves


class RunError(ValueError):
    pass


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def command(argv: list[str], cwd: Path, timeout: int = 60) -> str:
    result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        raise RunError(f"{argv!r} exited {result.returncode}: {result.stderr.strip()}")
    return result.stdout.strip()


def jj(repo: Path, *args: str) -> str:
    return command(["jj", "--color=never", *args], repo)


def commit(repo: Path, revision: str) -> str:
    value = jj(repo, "log", "--no-graph", "-r", revision, "-T", 'commit_id ++ "\\n"')
    if not re.fullmatch(r"[0-9a-f]{40,64}", value):
        raise RunError(f"{revision!r} must resolve to exactly one commit (got {value!r})")
    return value


def identity(repo: Path) -> str:
    return str(Path(jj(repo, "git", "root")).resolve())


@contextmanager
def ledger(directory: Path, plan: dict):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "run.lock").open("a") as lock:
        # Reject competing integration/acceptance immediately; never hold an
        # agent waiting behind a long suite and then apply its stale request.
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RunError("another operation owns this run; retry after it finishes") from error
        path = directory / "run.json"
        state = read(path) if path.exists() else None
        if state and (state.get("schema") != "workcell.build-run/v1" or state.get("planDigest") != digest(plan)):
            raise RunError("ledger belongs to another plan or the approved sidecar changed")
        yield state, path


def check_head(state: dict) -> Path:
    repo = Path(state["repo"])
    if identity(repo) != state["repositoryId"]:
        raise RunError("repository identity changed")
    if commit(repo, state["bookmark"]) != state["head"]:
        raise RunError("integration bookmark moved outside the ledger; reconcile it before resuming")
    return repo


def source_evidence(repo: Path, state: dict, plan: dict, item: dict, guard: str) -> dict:
    planned = {issue["key"]: issue for issue in plan["issues"]}
    key = item["key"]
    if key not in planned or key in state["integrated"]:
        raise RunError(f"{key}: unknown or already integrated issue")
    handoff_path = Path(item["handoff"])
    if not handoff_path.is_absolute():
        raise RunError(f"{key}: handoff path must be absolute so resume is independent of cwd")
    handoff = read(handoff_path)
    if (handoff.get("schema") != "anvil.agent-handoff/v1" or handoff.get("agent") != "builder"
            or handoff.get("disposition") != "done" or handoff.get("pr") is not None):
        raise RunError(f"{key}: expected a completed local builder handoff")
    workspace = Path(handoff["workspace"]).resolve(strict=True)
    if identity(workspace) != state["repositoryId"]:
        raise RunError(f"{key}: workspace belongs to another repository")
    source = commit(workspace, "@")
    if handoff.get("commitId") != source or commit(workspace, handoff["changeId"]) != source:
        raise RunError(f"{key}: handoff does not pin the current immutable commitId")
    if commit(workspace, "@-") != state["head"]:
        raise RunError(f"{key}: source has a different base; rebase, verify, and review it again")
    status = json.loads(command([guard, "status", "--json"], workspace))
    if status.get("ready") is not True or status.get("greenStale") is not False:
        raise RunError(f"{key}: guard evidence is missing or stale")
    green_id = status["green"]["commandId"]
    if green_id not in {entry.get("commandId") for entry in handoff.get("commands", [])}:
        raise RunError(f"{key}: handoff does not cite the current GREEN commandId")
    if commit(workspace, "@") != source:
        raise RunError(f"{key}: source changed while collecting evidence")
    changed = jj(repo, "diff", "--from", state["head"], "--to", source, "--name-only").splitlines()
    if sorted(changed) != sorted(handoff["changedFiles"]):
        raise RunError(f"{key}: changedFiles does not match the actual source diff")
    amendments = status["seal"].get("amendments", [])
    sealed_tests = amendments[-1]["after"] if amendments else status["seal"]["tests"]
    # A seal attests test integrity; it cannot expand the approved writer scope.
    planned_tests = {test["testPath"] for test in planned[key].get("acceptanceTests", []) if test.get("testPath")}
    approved_sealed_tests = planned_tests.intersection(entry["path"] for entry in sealed_tests)
    outside = [path for path in changed
               if path not in approved_sealed_tests and not waves.path_matches(path, planned[key]["ownershipHint"])]
    if outside:
        raise RunError(f"{key}: changed files outside ownership: {outside}")
    return {"key": key, "commitId": source, "workspace": str(workspace), "handoff": item["handoff"],
            "changedFiles": changed, "guard": status}


def run_check(argv: list[str], workspace: Path, timeout: int) -> dict:
    started = datetime.now(timezone.utc).isoformat()
    clock = time.monotonic()
    try:
        result = subprocess.run(argv, cwd=workspace, text=True, capture_output=True, timeout=timeout, check=False)
        code, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as error:
        code, stdout, stderr = 124, str(error.stdout or ""), f"Timed out after {timeout}s: {error.stderr or ''}"
    except OSError as error:
        code, stdout, stderr = 127, "", str(error)
    return {"commandId": "wc-" + uuid.uuid4().hex, "argv": argv, "exitCode": code,
            "startedAt": started, "finishedAt": datetime.now(timezone.utc).isoformat(),
            "durationSeconds": round(time.monotonic() - clock, 3), "stdout": stdout, "stderr": stderr}


def prepare(state: dict, path: Path, plan: dict, sources: list, checks: list, workspace: Path,
            guard: str, timeout: int) -> dict:
    repo = check_head(state)
    if path.resolve().is_relative_to(workspace.resolve()):
        raise RunError("candidate workspace must not contain the run ledger")
    if not sources or len({item["key"] for item in sources}) != len(sources):
        raise RunError("sources must contain distinct issue keys")
    if not checks or not all(isinstance(argv, list) and argv and all(isinstance(a, str) and a for a in argv) for argv in checks):
        raise RunError("checks must be a non-empty array of argv arrays")
    if timeout < 1:
        raise RunError("timeout must be positive")
    evidence = [source_evidence(repo, state, plan, item, guard) for item in sources]
    seen: set[str] = set()
    for source in evidence:
        overlap = seen.intersection(source["changedFiles"])
        if overlap:
            raise RunError(f"wave sources both change {sorted(overlap)}; serialize and reverify them")
        seen.update(source["changedFiles"])
    identifier = uuid.uuid4().hex
    candidate = "workcell-candidate-" + identifier[:12]
    receipt = {"id": identifier, "status": "preparing", "base": state["head"], "candidate": candidate,
               "workspace": str(workspace.resolve()), "sources": evidence, "checks": []}
    state["rounds"][identifier] = receipt
    # Write intent first. A crash leaves a visible preparing round and all source
    # workspaces intact; a fresh prepare uses a fresh candidate and workspace.
    write(path, state)
    try:
        jj(repo, "workspace", "add", "--name", candidate, "--revision", state["head"], str(workspace))
        previous = state["head"]
        for source in evidence:
            marker = f"Workcell integration: {identifier}:{source['key']}"
            template = 'description ++ "\\n' + marker + '\\n"'
            jj(repo, "--ignore-working-copy", "--config", "templates.duplicate_description=" + json.dumps(template),
               "duplicate", source["commitId"], "--onto", previous)
            # The unique description marker identifies our duplicate without
            # parsing human CLI output or racing other writers' new commits.
            previous = commit(repo, f'children({previous}) & description(substring:"{marker}")')
            jj(repo, "bookmark", "set", candidate, "-r", previous)
            if jj(repo, "log", "--no-graph", "-r", f"{previous} & conflicts()", "-T", "commit_id"):
                raise RunError(f"conflicts incorporating {source['key']}; original source preserved")
        jj(workspace, "edit", previous)
        receipt["commitId"] = commit(workspace, "@")
        for argv in checks:
            record = run_check(argv, workspace, timeout)
            receipt["checks"].append(record)
            write(path, state)
            if record["exitCode"]:
                raise RunError(f"combined check failed: {record['commandId']}")
            if commit(workspace, "@") != receipt["commitId"]:
                raise RunError("candidate source changed during verification")
        receipt["status"] = "prepared"
    except (RunError, OSError, subprocess.TimeoutExpired) as error:
        receipt["status"], receipt["error"] = "failed", str(error)
    write(path, state)
    return receipt


def accept(state: dict, path: Path, plan: dict, identifier: str, guard: str) -> dict:
    receipt = state["rounds"][identifier]
    if receipt["status"] == "accepted":
        check_head(state)
        return receipt
    if receipt["status"] != "prepared" or receipt["base"] != state["head"]:
        raise RunError("only a prepared candidate on the current integration base can be accepted")
    repo = Path(state["repo"])
    if identity(repo) != state["repositoryId"]:
        raise RunError("repository identity changed")
    if not receipt["checks"] or any(check["exitCode"] != 0 for check in receipt["checks"]):
        raise RunError("candidate has no passing combined verification")
    # Handles a crash after bookmark advancement but before ledger persistence.
    head = commit(repo, state["bookmark"])
    if head not in (state["head"], receipt["commitId"]):
        raise RunError("integration bookmark moved outside this acceptance")
    if commit(Path(receipt["workspace"]), "@") != receipt["commitId"]:
        raise RunError("prepared candidate changed; prepare and test it again")
    for source in receipt["sources"]:
        fresh = source_evidence(repo, state, plan, source, guard)
        if fresh["commitId"] != source["commitId"]:
            raise RunError("builder source changed since preparation")
    jj(repo, "bookmark", "set", state["bookmark"], "-r", receipt["commitId"])
    state["head"] = receipt["commitId"]
    state["integrated"].update({source["key"]: identifier for source in receipt["sources"]})
    receipt["status"] = "accepted"
    receipt["acceptedAt"] = datetime.now(timezone.utc).isoformat()
    write(path, state)
    return receipt


def select(state: dict, path: Path, plan: dict, snapshot: dict | None = None, local: bool = False) -> dict:
    if local == (snapshot is not None):
        raise RunError("select requires --snapshot or --local, exclusively")
    check_head(state)
    mode = "local" if local else "github"
    # Old ledgers with recorded rounds predate local tracking and used GitHub.
    saved = state.get("trackingMode") or ("github" if state.get("rounds") or state.get("integrated") else None)
    if saved and saved != mode:
        raise RunError(f"run uses {saved} tracking; preserve that mode on resume")
    by_key = waves.local_snapshot(plan) if local else waves.validate_snapshot(snapshot, plan)
    result = waves.derive(plan, by_key, frozenset(state["integrated"]))
    if state.get("trackingMode") != mode:
        state["trackingMode"] = mode
        write(path, state)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "prepare", "accept", "select", "status"))
    parser.add_argument("sidecar", type=Path)
    parser.add_argument("--state", type=Path, required=True, help="durable run directory outside all working copies")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--base", default="trunk()")
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--checks", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--receipt")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--local", action="store_true", help="select local tasks without GitHub issue tracking")
    parser.add_argument("--guard", default="tdd-guard")
    parser.add_argument("--timeout", type=int, default=600, help="seconds per combined verification command")
    args = parser.parse_args()
    try:
        plan = plan_sidecar.validate_plan(read(args.sidecar))
        repo = args.repo.resolve()
        if args.state.resolve().is_relative_to(repo):
            raise RunError("state must be outside the repository working copy")
        with ledger(args.state, plan) as (state, path):
            if args.action == "init":
                if state is None:
                    base = commit(repo, args.base)
                    if set(base) == {"0"}:
                        raise RunError("base resolved to the empty root; pass --base with the real project bookmark")
                    bookmark = plan["planId"] + "-integration"
                    existing = jj(repo, "bookmark", "list", bookmark, "-T", "name")
                    if existing:
                        raise RunError("integration bookmark already exists; restore its ledger instead of overwriting it")
                    state = {"schema": "workcell.build-run/v1", "planDigest": digest(plan),
                             "repo": str(repo), "repositoryId": identity(repo), "bookmark": bookmark,
                             "head": base, "integrated": {}, "rounds": {}, "initializing": True}
                    # Intent precedes ref mutation, so retry can finish an
                    # interrupted init without overwriting an unrelated bookmark.
                    write(path, state)
                if state.get("initializing"):
                    repo = Path(state["repo"])
                    existing = jj(repo, "bookmark", "list", state["bookmark"], "-T", "name")
                    if not existing:
                        jj(repo, "bookmark", "create", state["bookmark"], "-r", state["head"])
                    check_head(state)
                    state.pop("initializing")
                    write(path, state)
                check_head(state)
                result = state
            elif state is None:
                raise RunError("run is not initialized")
            elif args.action == "prepare":
                if not args.sources or not args.checks or not args.workspace:
                    raise RunError("prepare requires --sources, --checks, and --workspace")
                result = prepare(state, path, plan, read(args.sources), read(args.checks),
                                 args.workspace.resolve(), args.guard, args.timeout)
            elif args.action == "accept":
                if not args.receipt:
                    raise RunError("accept requires --receipt")
                result = accept(state, path, plan, args.receipt, args.guard)
            elif args.action == "select":
                result = select(state, path, plan, read(args.snapshot) if args.snapshot else None, args.local)
            else:
                result = state
            print(json.dumps(result, indent=2))
            return 1 if result.get("status") == "failed" else 0
    except (RunError, ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired) as error:
        print(f"build run error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
