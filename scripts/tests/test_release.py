"""Acceptance tests for guard release builder, version agreement, and CI workflow."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def host_target() -> tuple[str, str, str]:
    sys_name = platform.system().lower()
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "amd64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        arch = machine
    return sys_name, arch, f"{sys_name}/{arch}"


def get_guard_version() -> str:
    version_file = ROOT / "guard" / "version.go"
    text = version_file.read_text(encoding="utf-8")
    match = re.search(r'const\s+Version\s*=\s*"([^"]+)"', text)
    if not match:
        raise ValueError("Could not find Version constant in guard/version.go")
    return match.group(1)


def run_cmd(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def copy_root(*paths: str) -> tuple[tempfile.TemporaryDirectory, Path]:
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    for relative in paths:
        source = ROOT / relative
        if not source.exists():
            continue
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    return temporary, root


class ReleaseTests(unittest.TestCase):
    def test_release_builder_produces_a_stamped_binary_and_checksums(self) -> None:
        os_name, arch_name, target = host_target()
        version = get_guard_version()
        result = run_cmd(
            ROOT, "python3", "scripts/build-guard-release.py", "--targets", target
        )
        self.assertEqual(
            result.returncode,
            0,
            f"build-guard-release failed:\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )

        binary_path = (
            ROOT / "dist" / "release" / f"tdd-guard-{version}-{os_name}-{arch_name}"
        )
        self.assertTrue(binary_path.is_file(), f"Expected binary at {binary_path}")

        sha_file = ROOT / "dist" / "release" / "SHA256SUMS"
        self.assertTrue(sha_file.is_file(), f"Expected SHA256SUMS at {sha_file}")

        actual_sha = hashlib.sha256(binary_path.read_bytes()).hexdigest()
        sha_content = sha_file.read_text(encoding="utf-8")

        checksum_map: dict[str, str] = {}
        for line in sha_content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                digest, filename = parts
                clean_filename = Path(filename.lstrip("* ")).name
                checksum_map[clean_filename] = digest

        self.assertIn(
            binary_path.name,
            checksum_map,
            f"Binary {binary_path.name} not found in SHA256SUMS:\n{sha_content}",
        )
        self.assertEqual(
            checksum_map[binary_path.name],
            actual_sha,
            "Recorded SHA256 digest does not match actual binary sha256",
        )

    def test_released_binary_reports_the_release_version_without_a_repository(
        self,
    ) -> None:
        os_name, arch_name, target = host_target()
        version = get_guard_version()

        result = run_cmd(
            ROOT, "python3", "scripts/build-guard-release.py", "--targets", target
        )
        self.assertEqual(
            result.returncode,
            0,
            f"build-guard-release failed:\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )

        binary_path = (
            ROOT / "dist" / "release" / f"tdd-guard-{version}-{os_name}-{arch_name}"
        )
        self.assertTrue(binary_path.is_file(), f"Expected binary at {binary_path}")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            exec_res = run_cmd(temp_path, str(binary_path.resolve()), "version")
            self.assertEqual(
                exec_res.returncode,
                0,
                f"Binary execution failed:\nstdout: {exec_res.stdout}\nstderr: {exec_res.stderr}",
            )
            output = exec_res.stdout.strip()
            pattern = rf"^tdd-guard {re.escape(version)}(\+[0-9a-zA-Z._-]+)?$"
            self.assertRegex(
                output,
                pattern,
                f"Output {output!r} does not match expected format 'tdd-guard {version}[+<metadata>]'",
            )

    def test_version_check_fails_when_a_carrier_disagrees(self) -> None:
        version = get_guard_version()
        mutated_version = "9.9.9"

        temporary, root = copy_root(
            "guard",
            "plugins",
            "scripts",
        )
        with temporary:
            agy_manifest = root / "plugins" / "agy" / "plugin.json"
            if agy_manifest.exists():
                data = json.loads(agy_manifest.read_text(encoding="utf-8"))
                data["version"] = mutated_version
                agy_manifest.write_text(
                    json.dumps(data, indent=2) + "\n", encoding="utf-8"
                )

            res = run_cmd(root, "python3", "scripts/build-guard-release.py", "--check")
            self.assertNotEqual(
                res.returncode,
                0,
                f"Expected non-zero exit code when carrier disagrees:\nstdout: {res.stdout}\nstderr: {res.stderr}",
            )
            output = res.stdout + res.stderr
            self.assertIn(
                "plugins/agy/plugin.json",
                output,
                f"Output should name plugins/agy/plugin.json:\n{output}",
            )
            self.assertIn(
                version,
                output,
                f"Output should name expected version {version}:\n{output}",
            )
            self.assertIn(
                mutated_version,
                output,
                f"Output should name disagreed version {mutated_version}:\n{output}",
            )

        clean_res = run_cmd(
            ROOT, "python3", "scripts/build-guard-release.py", "--check"
        )
        self.assertEqual(
            clean_res.returncode,
            0,
            f"Expected 0 exit code on real tree:\nstdout: {clean_res.stdout}\nstderr: {clean_res.stderr}",
        )

    def test_codex_base_semver_is_inside_the_check(self) -> None:
        temporary, root = copy_root(
            "guard",
            "plugins",
            "scripts",
        )
        with temporary:
            codex_manifest = (
                root / "plugins" / "codex" / ".codex-plugin" / "plugin.json"
            )
            if codex_manifest.exists():
                data = json.loads(codex_manifest.read_text(encoding="utf-8"))
                data["version"] = "0.5.0"
                codex_manifest.write_text(
                    json.dumps(data, indent=2) + "\n", encoding="utf-8"
                )

            res = run_cmd(root, "python3", "scripts/build-guard-release.py", "--check")
            self.assertNotEqual(
                res.returncode,
                0,
                f"Expected non-zero exit code when codex carrier disagrees:\nstdout: {res.stdout}\nstderr: {res.stderr}",
            )
            output = res.stdout + res.stderr
            self.assertIn(
                "plugins/codex/.codex-plugin/plugin.json",
                output,
                f"Output should name plugins/codex/.codex-plugin/plugin.json:\n{output}",
            )

    def test_every_tracked_manifest_carries_the_release_version(self) -> None:
        version = get_guard_version()
        manifest_relpaths = [
            "plugins/claude/.claude-plugin/plugin.json",
            "plugins/agy/plugin.json",
            "plugins/codex/.codex-plugin/plugin.json",
        ]
        for relpath in manifest_relpaths:
            with self.subTest(manifest=relpath):
                manifest_path = ROOT / relpath
                self.assertTrue(
                    manifest_path.is_file(), f"Manifest not found: {relpath}"
                )
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest_ver = data.get("version")
                self.assertEqual(
                    manifest_ver,
                    version,
                    f"{relpath} has version {manifest_ver!r}, expected {version!r}",
                )
                self.assertNotEqual(
                    manifest_ver,
                    "0.1.0",
                    f"{relpath} has un-bumped version '0.1.0'",
                )

    def test_ci_gates_version_agreement_and_releases_on_a_tag(self) -> None:
        ci_path = ROOT / ".github" / "workflows" / "ci.yml"
        self.assertTrue(ci_path.is_file(), f"{ci_path} does not exist")

        ci_text = ci_path.read_text(encoding="utf-8")
        doc = yaml.safe_load(ci_text)
        self.assertIsInstance(doc, dict, "ci.yml must parse as YAML dict")

        # Workflow-level permissions must remain contents: read
        top_perms = doc.get("permissions", {})
        self.assertEqual(
            top_perms.get("contents"),
            "read",
            "Top-level permissions must be 'contents: read'",
        )

        jobs = doc.get("jobs", {})
        self.assertIn("test", jobs, "ci.yml missing 'test' job")
        test_job = jobs["test"]
        test_steps = test_job.get("steps", [])

        # Test job must contain step running scripts/build-guard-release.py --check
        has_check_step = any(
            "scripts/build-guard-release.py --check" in str(step.get("run", ""))
            for step in test_steps
        )
        self.assertTrue(
            has_check_step,
            "test job does not contain a step running 'scripts/build-guard-release.py --check'",
        )

        # Trigger must include push to tags matching v*
        on_trigger = doc.get("on") or doc.get(True) or {}
        push_trigger = on_trigger.get("push", {})
        tags = push_trigger.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        self.assertTrue(
            any(t == "v*" or t.startswith("v*") for t in tags),
            f"Expected push trigger for tags matching 'v*', got {tags}",
        )

        # Separate release job
        write_jobs = [
            k
            for k, v in jobs.items()
            if isinstance(v, dict)
            and v.get("permissions", {}).get("contents") == "write"
        ]
        self.assertEqual(
            len(write_jobs),
            1,
            f"Exactly one job must declare contents: write, found: {write_jobs}",
        )

        release_job_name = write_jobs[0]
        self.assertNotEqual(
            release_job_name,
            "test",
            "test job must not declare contents: write",
        )

        release_job = jobs[release_job_name]
        release_steps = release_job.get("steps", [])

        # Runs builder
        runs_builder = any(
            "scripts/build-guard-release.py" in str(step.get("run", ""))
            for step in release_steps
        )
        self.assertTrue(
            runs_builder,
            f"'{release_job_name}' job does not run 'scripts/build-guard-release.py'",
        )

        # Uploads dist/release artifacts
        uploads_artifacts = any(
            "dist/release" in str(step.get("with", {}).get("path", ""))
            or "dist/release" in str(step.get("run", ""))
            for step in release_steps
        )
        self.assertTrue(
            uploads_artifacts,
            f"'{release_job_name}' job does not upload dist/release artifacts",
        )


if __name__ == "__main__":
    unittest.main()
