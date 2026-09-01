#!/usr/bin/env python3
"""Build versioned tdd-guard release binaries and verify version carrier agreement.

scripts/build-guard-release.py                   # build default matrix to dist/release/
scripts/build-guard-release.py --targets linux/amd64 darwin/arm64
scripts/build-guard-release.py --check           # verify version carrier agreement
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_TARGETS = (
    "linux/amd64",
    "linux/arm64",
    "darwin/amd64",
    "darwin/arm64",
)

CARRIERS = (
    "plugins/claude/.claude-plugin/plugin.json",
    "plugins/grok/.claude-plugin/plugin.json",
    "plugins/agy/plugin.json",
    "plugins/codex/.codex-plugin/plugin.json",
)


def get_guard_version(root: Path) -> str:
    version_file = root / "guard" / "version.go"
    if not version_file.is_file():
        raise FileNotFoundError(f"Missing version file: {version_file}")
    text = version_file.read_text(encoding="utf-8")
    match = re.search(r'const\s+Version\s*=\s*"([^"]+)"', text)
    if not match:
        raise ValueError(f"Could not find Version constant in {version_file}")
    return match.group(1)


def get_build_metadata(root: Path) -> str:
    res = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.strip()

    res = subprocess.run(
        ["jj", "log", "-r", "@", "-T", "commit_id.short(8)", "--no-graph"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.strip()

    return ""


def check_carrier_agreement(root: Path) -> int:
    try:
        expected_version = get_guard_version(root)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    errors: list[str] = []
    for relpath in CARRIERS:
        manifest_path = root / relpath
        if not manifest_path.is_file():
            errors.append(f"missing carrier manifest: {relpath}")
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            errors.append(f"invalid JSON in {relpath}: {e}")
            continue
        carrier_version = data.get("version")
        if carrier_version != expected_version:
            errors.append(
                f"version mismatch in {relpath}: expected {expected_version}, got {carrier_version}"
            )

    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        return 1

    print(f"all version carriers agree on {expected_version}")
    return 0


def resolve_targets(target_args: list[str] | None) -> list[str]:
    if not target_args:
        return list(DEFAULT_TARGETS)
    targets: list[str] = []
    for item in target_args:
        for t in item.split(","):
            t = t.strip()
            if t:
                targets.append(t)
    return targets or list(DEFAULT_TARGETS)


def build_release(root: Path, targets: list[str]) -> int:
    try:
        version = get_guard_version(root)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    metadata = get_build_metadata(root)
    dist_release = root / "dist" / "release"
    dist_release.mkdir(parents=True, exist_ok=True)

    ldflags = f"-X github.com/anvil008/workcell/guard.BuildMetadata={metadata}"

    for target in targets:
        parts = target.split("/")
        if len(parts) != 2:
            print(
                f"error: invalid target format {target!r}, expected os/arch",
                file=sys.stderr,
            )
            return 1
        os_name, arch_name = parts
        binary_name = f"tdd-guard-{version}-{os_name}-{arch_name}"
        output_path = dist_release / binary_name

        env = {
            **os.environ,
            "GOOS": os_name,
            "GOARCH": arch_name,
            "CGO_ENABLED": "0",
        }
        cmd = [
            "go",
            "build",
            "-buildvcs=false",
            "-ldflags",
            ldflags,
            "-o",
            str(output_path),
            "./cmd/tdd-guard",
        ]
        res = subprocess.run(
            cmd, cwd=root, env=env, capture_output=True, text=True, check=False
        )
        if res.returncode != 0:
            print(
                f"error building {target}:\nstdout: {res.stdout}\nstderr: {res.stderr}",
                file=sys.stderr,
            )
            return res.returncode

        print(f"built {output_path.name}")

    # Write SHA256SUMS for all binaries in dist/release
    sha_lines: list[str] = []
    for binary_file in sorted(dist_release.glob("tdd-guard-*")):
        if not binary_file.is_file():
            continue
        digest = hashlib.sha256(binary_file.read_bytes()).hexdigest()
        sha_lines.append(f"{digest}  {binary_file.name}\n")

    manifest = dist_release / "SHA256SUMS"
    manifest.write_text("".join(sha_lines), encoding="utf-8")
    print(f"wrote {manifest.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build versioned tdd-guard release binaries and verify agreement."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify every version carrier agrees with guard.Version",
    )
    parser.add_argument(
        "--targets",
        nargs="*",
        default=None,
        help="target platforms to build (e.g. linux/amd64, darwin/arm64)",
    )
    args = parser.parse_args(argv)

    if args.check:
        return check_carrier_agreement(ROOT)

    targets = resolve_targets(args.targets)
    return build_release(ROOT, targets)


if __name__ == "__main__":
    sys.exit(main())
