"""Unit tests for the si-project skill and si.py CLI."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
SI_SCRIPT = REPO / "skills" / "si-project" / "scripts" / "si.py"


def run_si(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SI_SCRIPT)] + args
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        cmd,
        cwd=cwd or REPO,
        env=full_env,
        capture_output=True,
        text=True,
        check=False,
    )


class PrimaryRootResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_resolve_root_from_primary_jj(self):
        repo_dir = self.base / "repo"
        repo_dir.mkdir(parents=True)
        jj_repo = repo_dir / ".jj" / "repo"
        jj_repo.mkdir(parents=True)

        res = run_si(["resolve-root", "--repo", str(repo_dir)])
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), str(repo_dir))

    def test_resolve_root_from_secondary_jj_workspace(self):
        primary_dir = self.base / "primary"
        primary_dir.mkdir(parents=True)
        primary_jj_repo = primary_dir / ".jj" / "repo"
        primary_jj_repo.mkdir(parents=True)

        # Secondary workspace points to primary
        secondary_dir = primary_dir / ".workspaces" / "feat-x"
        secondary_dir.mkdir(parents=True)
        (secondary_dir / ".jj").mkdir(parents=True)
        pointer_file = secondary_dir / ".jj" / "repo"
        pointer_file.write_text("../../../.jj/repo\n", encoding="utf-8")

        res = run_si(["resolve-root", "--repo", str(secondary_dir)])
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), str(primary_dir))

    def test_resolve_root_from_git_worktree(self):
        main_repo = self.base / "main-git"
        main_repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-b", "main"], cwd=main_repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=main_repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=main_repo, check=True)
        (main_repo / "README.md").write_text("initial\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=main_repo, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=main_repo, check=True)

        wt_dir = self.base / "wt-1"
        subprocess.run(["git", "worktree", "add", str(wt_dir), "-b", "branch1"], cwd=main_repo, check=True)

        res = run_si(["resolve-root", "--repo", str(wt_dir)])
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), str(main_repo))


class StoreInitAndStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name).resolve()
        self.repo = self.base / "project"
        self.repo.mkdir(parents=True)
        (self.repo / ".git").mkdir()  # simulate git repo
        self.registry = self.base / "known_projects.json"
        self.env = {
            "NOVA_PROJECTS_REGISTRY": str(self.registry),
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_status_when_not_initialized(self):
        res = run_si(["status", "--repo", str(self.repo)], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertFalse(data["present"])
        self.assertEqual(data["primaryRoot"], str(self.repo))
        self.assertEqual(data["storePath"], str(self.repo / ".nova" / "si"))

    def test_init_creates_store_and_registers(self):
        res = run_si(["init", "--repo", str(self.repo)], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertTrue(data["created"])
        store_path = Path(data["storePath"])

        self.assertTrue((store_path / "project.json").is_file())
        self.assertTrue((store_path / "index.md").is_file())
        self.assertTrue((store_path / "logs.md").is_file())
        self.assertTrue((store_path / "skill-impact.md").is_file())
        self.assertTrue((store_path / "raw").is_dir())
        self.assertTrue((store_path / "patterns").is_dir())
        self.assertTrue((store_path / "proposals").is_dir())

        # Check registry updated
        self.assertTrue(self.registry.is_file())
        reg_data = json.loads(self.registry.read_text(encoding="utf-8"))
        self.assertIn(str(self.repo), reg_data["projects"])

        # Check status after init
        s_res = run_si(["status", "--repo", str(self.repo)], env=self.env)
        self.assertEqual(s_res.returncode, 0, s_res.stderr)
        s_data = json.loads(s_res.stdout)
        self.assertTrue(s_data["present"])
        self.assertEqual(s_data["raw"], 0)
        self.assertEqual(s_data["patterns"], 0)
        self.assertEqual(s_data["proposals"], 0)

        # Idempotent init
        res2 = run_si(["init", "--repo", str(self.repo)], env=self.env)
        self.assertEqual(res2.returncode, 0, res2.stderr)
        data2 = json.loads(res2.stdout)
        self.assertFalse(data2["created"])


class InvalidRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name).resolve()
        self.repo = self.base / "project"
        self.repo.mkdir(parents=True)
        (self.repo / ".git").mkdir()
        self.registry = self.base / "known_projects.json"
        self.env = {"NOVA_PROJECTS_REGISTRY": str(self.registry)}

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_init_and_register_refuse_invalid_registry(self):
        for content in (
            "{not json",
            json.dumps({"projects": "not-a-list"}),
            json.dumps({"projects": ["/ok", 3]}),
            json.dumps({"other": ["/elsewhere"]}),
            json.dumps("just a string"),
        ):
            self.registry.write_text(content, encoding="utf-8")
            before = self.registry.read_bytes()
            for cmd in (["init"], ["register"]):
                res = run_si(cmd + ["--repo", str(self.repo)], env=self.env)
                self.assertNotEqual(res.returncode, 0, f"{cmd} accepted registry {content!r}")
                self.assertIn("si error: invalid registry", res.stderr)
                self.assertEqual(self.registry.read_bytes(), before)
            self.assertFalse((self.repo / ".nova" / "si").exists())

        # An explicit --registry path is validated the same way.
        explicit = self.base / "explicit.json"
        explicit.write_text("[1]", encoding="utf-8")
        res = run_si(["register", "--repo", str(self.repo), "--registry", str(explicit)], env=self.env)
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(explicit.read_text(encoding="utf-8"), "[1]")

    def test_register_keeps_valid_list_registry_entries(self):
        self.registry.write_text(json.dumps(["/existing/project"]), encoding="utf-8")
        res = run_si(["register", "--repo", str(self.repo)], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(self.registry.read_text(encoding="utf-8"))
        self.assertEqual(data["projects"], sorted(["/existing/project", str(self.repo)]))


class RawAndPatternTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name).resolve()
        self.repo = self.base / "project"
        self.repo.mkdir(parents=True)
        (self.repo / ".git").mkdir()
        self.registry = self.base / "known_projects.json"
        self.env = {
            "NOVA_PROJECTS_REGISTRY": str(self.registry),
        }
        run_si(["init", "--repo", str(self.repo)], env=self.env)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_record_and_pattern_accumulation(self):
        ev1 = self.base / "log1.txt"
        ev1.write_text("Integrator timed out on lock\n", encoding="utf-8")

        rec_res = run_si([
            "record",
            "--repo", str(self.repo),
            "--id", "2026-09-13-build-1",
            "--kind", "build-wave",
            "--summary", "lock timeout on wave 1",
            "--file", str(ev1),
            "--model", "claude-sonnet-5",
            "--effort", "high",
        ], env=self.env)
        self.assertEqual(rec_res.returncode, 0, rec_res.stderr)
        self.assertEqual(rec_res.stdout.strip(), "2026-09-13-build-1")

        # Duplicate ID is refused (write-once)
        rec_dup = run_si([
            "record",
            "--repo", str(self.repo),
            "--id", "2026-09-13-build-1",
            "--kind", "build-wave",
            "--summary", "another summary",
            "--file", str(ev1),
        ], env=self.env)
        self.assertNotEqual(rec_dup.returncode, 0)

        # Pattern creation
        pat_res = run_si([
            "pattern", "flaky-lock",
            "--repo", str(self.repo),
            "--evidence", "2026-09-13-build-1",
            "--note", "Timed out waiting for sandbox lock.",
            "--title", "Flaky sandbox lock",
        ], env=self.env)
        self.assertEqual(pat_res.returncode, 0, pat_res.stderr)
        self.assertEqual(pat_res.stdout.strip(), "flaky-lock")

        pattern_file = self.repo / ".nova" / "si" / "patterns" / "flaky-lock.md"
        self.assertTrue(pattern_file.is_file())
        text = pattern_file.read_text(encoding="utf-8")
        self.assertIn("# Flaky sandbox lock", text)
        self.assertIn("`2026-09-13-build-1` [claude-sonnet-5·high]", text)
        self.assertIn("Timed out waiting for sandbox lock.", text)

        # Index updated
        index_file = self.repo / ".nova" / "si" / "index.md"
        idx_text = index_file.read_text(encoding="utf-8")
        self.assertIn("[flaky-lock](patterns/flaky-lock.md)", idx_text)
        self.assertIn("| 1 |", idx_text)

        # Nonexistent evidence ID is refused
        pat_bad = run_si([
            "pattern", "flaky-lock",
            "--repo", str(self.repo),
            "--evidence", "nonexistent-id",
            "--note", "Should fail.",
        ], env=self.env)
        self.assertNotEqual(pat_bad.returncode, 0)

    def test_record_refuses_duplicate_evidence_basenames(self):
        (self.base / "d1").mkdir()
        (self.base / "d2").mkdir()
        (self.base / "d1" / "same.txt").write_text("first\n", encoding="utf-8")
        (self.base / "d2" / "same.txt").write_text("second\n", encoding="utf-8")

        res = run_si([
            "record",
            "--repo", str(self.repo),
            "--id", "t3",
            "--kind", "build-wave",
            "--summary", "duplicate names",
            "--file", str(self.base / "d1" / "same.txt"),
            "--file", str(self.base / "d2" / "same.txt"),
        ], env=self.env)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("si error:", res.stderr)
        self.assertIn("same.txt", res.stderr)

        raw_dir = self.repo / ".nova" / "si" / "raw"
        self.assertFalse((raw_dir / "t3").exists())
        self.assertEqual([p.name for p in raw_dir.iterdir()], [])

        check = run_si(["check", "--repo", str(self.repo)], env=self.env)
        self.assertEqual(check.returncode, 0, check.stderr)


class ProposeAndApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name).resolve()
        self.repo = self.base / "project"
        self.repo.mkdir(parents=True)
        (self.repo / ".git").mkdir()
        self.registry = self.base / "known_projects.json"
        self.env = {
            "NOVA_PROJECTS_REGISTRY": str(self.registry),
        }
        run_si(["init", "--repo", str(self.repo)], env=self.env)

        ev1 = self.base / "log1.txt"
        ev1.write_text("Lock contention observed\n", encoding="utf-8")
        run_si([
            "record",
            "--repo", str(self.repo),
            "--id", "2026-09-13-trace-1",
            "--kind", "test-trace",
            "--summary", "trace summary",
            "--file", str(ev1),
        ], env=self.env)
        run_si([
            "pattern", "sandbox-contention",
            "--repo", str(self.repo),
            "--evidence", "2026-09-13-trace-1",
            "--note", "Contention under parallel workers.",
        ], env=self.env)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_propose_and_apply_to_agents_md(self):
        res = run_si([
            "propose",
            "--repo", str(self.repo),
            "--id", "prop-lock-mitigation",
            "--pattern", "sandbox-contention",
            "--title", "Sandbox Lock Retry Rule",
            "--target", "agents-md",
            "--rule", "Retry sandbox lock acquisition up to 3 times with exponential backoff.",
        ], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        p_data = json.loads(res.stdout)
        self.assertFalse(p_data["applied"])

        p_file = self.repo / ".nova" / "si" / "proposals" / "prop-lock-mitigation.json"
        self.assertTrue(p_file.is_file())

        # Apply the proposal
        apply_res = run_si([
            "propose",
            "--repo", str(self.repo),
            "--id", "prop-lock-mitigation",
            "--apply",
        ], env=self.env)
        self.assertEqual(apply_res.returncode, 0, apply_res.stderr)
        app_data = json.loads(apply_res.stdout)
        self.assertTrue(app_data["applied"])

        agents_md = self.repo / "AGENTS.md"
        self.assertTrue(agents_md.is_file())
        content = agents_md.read_text(encoding="utf-8")
        self.assertIn("## Sandbox Lock Retry Rule", content)
        self.assertIn("Retry sandbox lock acquisition", content)

        # Audit trail written
        impact = (self.repo / ".nova" / "si" / "skill-impact.md").read_text(encoding="utf-8")
        self.assertIn("applied proposal prop-lock-mitigation to AGENTS.md", impact)

    def test_propose_and_apply_to_local_skill(self):
        skill_text = "---\nname: sandbox-helper\ndescription: Lock helper.\n---\n\n# Helper\n\necho helper\n"
        res = run_si([
            "propose",
            "--repo", str(self.repo),
            "--id", "prop-custom-skill",
            "--pattern", "sandbox-contention",
            "--title", "Custom Lock Helper",
            "--target", "skill",
            "--skill-name", "sandbox-helper",
            "--rule", skill_text,
            "--apply",
        ], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)

        custom_skill_md = self.repo / ".nova" / "skills" / "sandbox-helper" / "SKILL.md"
        self.assertTrue(custom_skill_md.is_file())
        # A skill proposal's text is the whole SKILL.md: frontmatter and newlines survive.
        self.assertEqual(custom_skill_md.read_text(encoding="utf-8"), skill_text)
        stored = json.loads(
            (self.repo / ".nova" / "si" / "proposals" / "prop-custom-skill.json").read_text(encoding="utf-8")
        )
        self.assertEqual(stored["proposal"], skill_text)

        # Creating first and applying later keeps the text verbatim too.
        res = run_si([
            "propose", "--repo", str(self.repo), "--id", "prop-skill-later",
            "--pattern", "sandbox-contention", "--target", "skill",
            "--skill-name", "later-helper", "--rule", skill_text,
        ], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        res = run_si(["propose", "--repo", str(self.repo), "--id", "prop-skill-later", "--apply"], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        later_md = self.repo / ".nova" / "skills" / "later-helper" / "SKILL.md"
        self.assertEqual(later_md.read_text(encoding="utf-8"), skill_text)

    def test_apply_accepts_existing_legacy_id_and_folds_agents_md_rule(self):
        proposals_dir = self.repo / ".nova" / "si" / "proposals"
        (proposals_dir / "Fix-Lock.json").write_text(json.dumps({
            "id": "Fix-Lock",
            "target": "agents-md",
            "title": "Legacy rule",
            "patterns": ["sandbox-contention"],
            "proposal": "Do X.\n## Injected heading",
            "applied": False,
        }), encoding="utf-8")

        res = run_si(["propose", "--repo", str(self.repo), "--id", "Fix-Lock", "--apply"], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = (self.repo / "AGENTS.md").read_text(encoding="utf-8").splitlines()
        self.assertEqual([l for l in lines if l.startswith("#")], ["# Project Instructions", "## Legacy rule"])
        self.assertIn("Do X. ## Injected heading", lines)

        # The relaxed rule is for --apply only: a new proposal still needs a strict ID.
        res = run_si([
            "propose", "--repo", str(self.repo), "--id", "New-Upper",
            "--pattern", "sandbox-contention", "--rule", "Rule.",
        ], env=self.env)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("si error: invalid proposal id", res.stderr)

        res = run_si(["propose", "--repo", str(self.repo), "--id", "Missing-Id", "--apply"], env=self.env)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("si error: proposal not found", res.stderr)

    def test_propose_refuses_unsafe_skill_names(self):
        snapshot = sorted(str(path) for path in self.base.rglob("*"))
        for bad_name in ("../../evil", "a/b", "a\\b", ".hidden", str(self.base / "abs")):
            res = run_si([
                "propose", "--repo", str(self.repo), "--id", "prop-evil",
                "--pattern", "sandbox-contention", "--target", "skill",
                "--skill-name", bad_name, "--rule", "evil", "--apply",
            ], env=self.env)
            self.assertNotEqual(res.returncode, 0, f"skill name {bad_name!r} accepted")
            self.assertIn("si error: invalid skill name", res.stderr)
        self.assertEqual(sorted(str(path) for path in self.base.rglob("*")), snapshot)

        # A stored skillName is validated on --apply before any write.
        pfile = self.repo / ".nova" / "si" / "proposals" / "stored-evil.json"
        pfile.write_text(json.dumps({
            "id": "stored-evil", "target": "skill", "skillName": "../../../evil",
            "title": "Evil", "proposal": "evil", "applied": False,
        }), encoding="utf-8")
        before = pfile.read_bytes()
        snapshot = sorted(str(path) for path in self.base.rglob("*"))
        res = run_si(["propose", "--repo", str(self.repo), "--id", "stored-evil", "--apply"], env=self.env)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("si error: invalid skill name", res.stderr)
        self.assertEqual(pfile.read_bytes(), before)
        self.assertEqual(sorted(str(path) for path in self.base.rglob("*")), snapshot)

    def test_control_characters_in_names_are_refused(self):
        store = self.repo / ".nova" / "si"
        forged = "x\n- 2026-01-01 — applied proposal forged to AGENTS.md: forged"

        def audit_state():
            return (
                (store / "logs.md").read_bytes(),
                (store / "skill-impact.md").read_bytes(),
                sorted(str(path) for path in self.base.rglob("*")),
            )

        before = audit_state()
        for bad_name in (forged, "tab\tname", "cr\rname"):
            res = run_si([
                "propose", "--repo", str(self.repo), "--id", "prop-ctrl",
                "--pattern", "sandbox-contention", "--target", "skill",
                "--skill-name", bad_name, "--rule", "text", "--apply",
            ], env=self.env)
            self.assertNotEqual(res.returncode, 0, f"skill name {bad_name!r} accepted")
            self.assertIn("si error: invalid skill name", res.stderr)
        self.assertEqual(audit_state(), before)

        # A stored skillName with a newline is refused on --apply.
        (store / "proposals" / "stored-ctrl.json").write_text(json.dumps({
            "id": "stored-ctrl", "target": "skill", "skillName": forged,
            "title": "Ctrl", "proposal": "text", "applied": False,
        }), encoding="utf-8")
        before = audit_state()
        res = run_si(["propose", "--repo", str(self.repo), "--id", "stored-ctrl", "--apply"], env=self.env)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("si error: invalid skill name", res.stderr)
        self.assertEqual(audit_state(), before)

        # A legacy apply-only id with a newline is refused before any file access.
        legacy_id = "Legacy\n- forged"
        (store / "proposals" / f"{legacy_id}.json").write_text(json.dumps({
            "id": legacy_id, "target": "agents-md", "title": "Forged",
            "proposal": "text", "applied": False,
        }), encoding="utf-8")
        before = audit_state()
        res = run_si(["propose", "--repo", str(self.repo), "--id", legacy_id, "--apply"], env=self.env)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("si error: invalid proposal id", res.stderr)
        self.assertEqual(audit_state(), before)
        self.assertFalse((self.repo / "AGENTS.md").exists())

    def test_apply_corrupt_proposal_is_controlled_error(self):
        proposals_dir = self.repo / ".nova" / "si" / "proposals"
        for name, content in (("empty", ""), ("broken", "{not json"), ("listy", "[]")):
            (proposals_dir / f"{name}.json").write_text(content, encoding="utf-8")
            res = run_si(["propose", "--repo", str(self.repo), "--id", name, "--apply"], env=self.env)
            self.assertEqual(res.returncode, 1, res.stderr)
            self.assertIn(f"si error: invalid proposal {name}", res.stderr)
            self.assertNotIn("Traceback", res.stderr)

    def test_propose_allocates_unique_ids_without_overwriting(self):
        proposals_dir = self.repo / ".nova" / "si" / "proposals"
        ids = []
        for extra in (
            [],
            ["--target", "skill", "--skill-name", "kept-skill"],
            ["--rule", "Third rule."],
        ):
            res = run_si([
                "propose",
                "--repo", str(self.repo),
                "--pattern", "sandbox-contention",
            ] + extra, env=self.env)
            self.assertEqual(res.returncode, 0, res.stderr)
            ids.append(json.loads(res.stdout)["id"])

        base_id = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-sandbox-contention"
        self.assertEqual(ids, [base_id, f"{base_id}-2", f"{base_id}-3"])
        self.assertEqual(len(list(proposals_dir.glob("*.json"))), 3)
        second = json.loads((proposals_dir / f"{base_id}-2.json").read_text(encoding="utf-8"))
        self.assertEqual(second["skillName"], "kept-skill")
        third = json.loads((proposals_dir / f"{base_id}-3.json").read_text(encoding="utf-8"))
        self.assertEqual(third["proposal"], "Third rule.")

        apply_res = run_si([
            "propose", "--repo", str(self.repo), "--id", f"{base_id}-3", "--apply",
        ], env=self.env)
        self.assertEqual(apply_res.returncode, 0, apply_res.stderr)
        self.assertIn("Third rule.", (self.repo / "AGENTS.md").read_text(encoding="utf-8"))

        # An explicit ID that already exists is refused and left untouched.
        before = (proposals_dir / f"{base_id}-2.json").read_text(encoding="utf-8")
        dup = run_si([
            "propose",
            "--repo", str(self.repo),
            "--id", f"{base_id}-2",
            "--pattern", "sandbox-contention",
            "--rule", "Overwrite attempt.",
        ], env=self.env)
        self.assertNotEqual(dup.returncode, 0)
        self.assertIn("si error:", dup.stderr)
        self.assertEqual((proposals_dir / f"{base_id}-2.json").read_text(encoding="utf-8"), before)

    def test_propose_refuses_unsafe_ids(self):
        outside = self.base / "outside"
        snapshot = sorted(str(path) for path in self.base.rglob("*"))
        for bad_id in ("../x", "../../outside/escape", str(outside / "abs"), "a/b", "a\\b", ".hidden", "Upper"):
            for extra in (
                ["--pattern", "sandbox-contention", "--rule", "Escape attempt."],
                ["--apply"],
            ):
                if bad_id == "Upper" and extra == ["--apply"]:
                    continue  # a safe legacy ID on --apply; covered by the legacy-id test
                res = run_si(["propose", "--repo", str(self.repo), "--id", bad_id] + extra, env=self.env)
                self.assertNotEqual(res.returncode, 0, f"id {bad_id!r} accepted with {extra}")
                self.assertIn("si error: invalid proposal id", res.stderr)
        # Nothing was created anywhere, inside or outside the store.
        self.assertEqual(sorted(str(path) for path in self.base.rglob("*")), snapshot)

    def test_multiline_rule_and_title_are_folded(self):
        res = run_si([
            "propose",
            "--repo", str(self.repo),
            "--id", "prop-multiline",
            "--pattern", "sandbox-contention",
            "--title", "Real title\n## Injected title heading",
            "--rule", "Do X.\n## Injected heading\n\n- injected item",
            "--apply",
        ], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)

        stored = json.loads(
            (self.repo / ".nova" / "si" / "proposals" / "prop-multiline.json").read_text(encoding="utf-8")
        )
        self.assertEqual(stored["proposal"], "Do X. ## Injected heading - injected item")
        self.assertEqual(stored["title"], "Real title ## Injected title heading")

        lines = (self.repo / "AGENTS.md").read_text(encoding="utf-8").splitlines()
        headings = [line for line in lines if line.startswith("#")]
        self.assertEqual(headings, ["# Project Instructions", "## Real title ## Injected title heading"])
        self.assertNotIn("- injected item", lines)


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name).resolve()
        self.repo = self.base / "project"
        self.repo.mkdir(parents=True)
        (self.repo / ".git").mkdir()
        self.registry = self.base / "known_projects.json"
        self.env = {
            "NOVA_PROJECTS_REGISTRY": str(self.registry),
        }
        run_si(["init", "--repo", str(self.repo)], env=self.env)

        ev1 = self.base / "file1.txt"
        ev1.write_text("hello evidence\n", encoding="utf-8")
        run_si([
            "record",
            "--repo", str(self.repo),
            "--id", "trace-101",
            "--kind", "check-test",
            "--summary", "trace 101",
            "--file", str(ev1),
        ], env=self.env)
        run_si([
            "pattern", "sample-pattern",
            "--repo", str(self.repo),
            "--evidence", "trace-101",
            "--note", "Sample note.",
        ], env=self.env)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_check_passes_on_healthy_store(self):
        res = run_si(["check", "--repo", str(self.repo)], env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertTrue(data["ok"])

    def test_check_fails_on_tampered_file(self):
        file_dest = self.repo / ".nova" / "si" / "raw" / "trace-101" / "files" / "file1.txt"
        file_dest.write_text("tampered content\n", encoding="utf-8")

        res = run_si(["check", "--repo", str(self.repo)], env=self.env)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("checksum mismatch", res.stderr)

    def test_check_fails_on_index_drift(self):
        index_file = self.repo / ".nova" / "si" / "index.md"
        # tamper with occurrences count
        index_file.write_text(index_file.read_text().replace("| 1 |", "| 99 |"), encoding="utf-8")

        res = run_si(["check", "--repo", str(self.repo)], env=self.env)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("count mismatch", res.stderr)


class EvalModeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name).resolve()
        self.repo = self.base / "project"
        self.repo.mkdir(parents=True)
        (self.repo / ".git").mkdir()
        (self.repo / ".nova").mkdir(parents=True)
        (self.repo / ".nova" / "eval-mode.json").write_text("{}", encoding="utf-8")
        self.registry = self.base / "known_projects.json"
        self.env = {
            "NOVA_PROJECTS_REGISTRY": str(self.registry),
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_eval_mode_refuses_operations(self):
        for cmd in (["status"], ["init"], ["check"]):
            res = run_si(cmd + ["--repo", str(self.repo)], env=self.env)
            self.assertNotEqual(res.returncode, 0, f"{cmd} should have failed in eval mode")
            self.assertIn("eval mode refused", res.stderr)

    def test_eval_mode_refuses_register_but_allows_resolve_root(self):
        res = run_si(["register", "--repo", str(self.repo)], env=self.env)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("eval mode refused", res.stderr)
        self.assertFalse(self.registry.exists())

        root = run_si(["resolve-root", "--repo", str(self.repo)], env=self.env)
        self.assertEqual(root.returncode, 0, root.stderr)
        self.assertEqual(root.stdout.strip(), str(self.repo))

    def test_eval_mode_marker_in_secondary_workspace_refuses_register(self):
        primary_dir = self.base / "primary"
        (primary_dir / ".jj" / "repo").mkdir(parents=True)
        secondary_dir = primary_dir / ".workspaces" / "eval-run"
        (secondary_dir / ".jj").mkdir(parents=True)
        (secondary_dir / ".jj" / "repo").write_text("../../../.jj/repo\n", encoding="utf-8")
        (secondary_dir / ".nova").mkdir()
        (secondary_dir / ".nova" / "eval-mode.json").write_text("{}", encoding="utf-8")

        res = run_si(["register", "--repo", str(secondary_dir)], env=self.env)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("eval mode refused", res.stderr)
        self.assertFalse(self.registry.exists())

    def test_eval_mode_marker_covers_nested_git_repo_in_jj_workspace(self):
        primary_dir = self.base / "primary"
        (primary_dir / ".jj" / "repo").mkdir(parents=True)
        secondary_dir = primary_dir / ".workspaces" / "ev"
        (secondary_dir / ".jj").mkdir(parents=True)
        (secondary_dir / ".jj" / "repo").write_text("../../../.jj/repo\n", encoding="utf-8")
        (secondary_dir / ".nova").mkdir()
        (secondary_dir / ".nova" / "eval-mode.json").write_text("{}", encoding="utf-8")
        nested = secondary_dir / "vendor" / "lib"
        (nested / ".git").mkdir(parents=True)
        sub = nested / "src"
        sub.mkdir()

        for repo in (nested, sub):
            root = run_si(["resolve-root", "--repo", str(repo)], env=self.env)
            self.assertEqual(root.stdout.strip(), str(primary_dir))
            for cmd in (["register"], ["init"], ["status"]):
                res = run_si(cmd + ["--repo", str(repo)], env=self.env)
                self.assertNotEqual(res.returncode, 0, f"{cmd} ran in a nested repo of an eval-mode workspace")
                self.assertIn("eval mode refused", res.stderr)
        self.assertFalse(self.registry.exists())
        self.assertFalse((primary_dir / ".nova").exists())

    def test_eval_mode_marker_covers_jj_workspace_subdirectory(self):
        primary_dir = self.base / "primary"
        (primary_dir / ".jj" / "repo").mkdir(parents=True)
        secondary_dir = primary_dir / ".workspaces" / "ev"
        (secondary_dir / ".jj").mkdir(parents=True)
        (secondary_dir / ".jj" / "repo").write_text("../../../.jj/repo\n", encoding="utf-8")
        (secondary_dir / ".nova").mkdir()
        (secondary_dir / ".nova" / "eval-mode.json").write_text("{}", encoding="utf-8")
        sub = secondary_dir / "sub" / "deeper"
        sub.mkdir(parents=True)

        for cmd in (["register"], ["init"], ["status"], ["check"]):
            res = run_si(cmd + ["--repo", str(sub)], env=self.env)
            self.assertNotEqual(res.returncode, 0, f"{cmd} ran in an eval-mode workspace subdirectory")
            self.assertIn("eval mode refused", res.stderr)
        self.assertFalse(self.registry.exists())
        self.assertFalse((primary_dir / ".nova").exists())

    def test_eval_mode_marker_covers_git_worktree_subdirectory(self):
        main_repo = self.base / "main-git"
        main_repo.mkdir()
        git = ["git", "-c", "user.name=Tester", "-c", "user.email=test@example.com"]
        subprocess.run(git + ["init", "-b", "main"], cwd=main_repo, capture_output=True, check=True)
        (main_repo / "README.md").write_text("initial\n", encoding="utf-8")
        subprocess.run(git + ["add", "README.md"], cwd=main_repo, capture_output=True, check=True)
        subprocess.run(git + ["commit", "-m", "init"], cwd=main_repo, capture_output=True, check=True)
        wt_dir = self.base / "wt-eval"
        subprocess.run(git + ["worktree", "add", str(wt_dir), "-b", "eval"], cwd=main_repo, capture_output=True, check=True)
        (wt_dir / ".nova").mkdir()
        (wt_dir / ".nova" / "eval-mode.json").write_text("{}", encoding="utf-8")
        sub = wt_dir / "sub"
        sub.mkdir()

        for cmd in (["register"], ["init"], ["status"]):
            res = run_si(cmd + ["--repo", str(sub)], env=self.env)
            self.assertNotEqual(res.returncode, 0, f"{cmd} ran in an eval-mode worktree subdirectory")
            self.assertIn("eval mode refused", res.stderr)
        self.assertFalse(self.registry.exists())
        self.assertFalse((main_repo / ".nova").exists())


if __name__ == "__main__":
    unittest.main()
