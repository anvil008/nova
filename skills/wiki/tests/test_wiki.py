"""The wiki layer: global per-project store, layout contract, and the `wiki` skill (#111).

Nothing here touches the developer's real home. Every subprocess runs with `HOME` and
`WORKCELL_WIKI_HOME` pointed at a throwaway directory, git and jj configuration is
redirected at throwaway files, and
`test_init_creates_the_namespace_under_the_configured_root` asserts that the real
`~/.workcell` is exactly as it was before the suite ran.

Beyond the issue body, these tests pin the shape the CLI answers in, because a test cannot
assert on an oracle it cannot read:

* `key` and `status` each print exactly one JSON object on stdout. `key` carries
  `projectKey` and `source` (`remote` or `path`); `status` carries `projectKey` and
  `present`.
* `project.json` carries `projectKey`, `source`, `derivedFrom` — the origin URL or the
  resolved toplevel the namespace was created from — and `createdAt`.
* `raw/<id>/manifest.json` carries `id`, `kind`, `recordedAt`, `summary`, and `files`: one
  entry per copied file, each with `path` (relative to the bundle directory) and `sha256`.
* `record` takes `--id`, `--kind`, `--summary`, and a repeatable `--file`, and prints the
  raw id it wrote. `pattern` takes the slug positionally plus a repeatable `--evidence`
  and a `--note` carrying the prose.
* A pattern page's evidence entries are one per line, each carrying an ISO `YYYY-MM-DD`
  date and the raw id it cites; `index.md` carries one line per pattern page, naming the
  slug and its occurrence count.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILL_DIR = REPO / "skills" / "wiki"
WIKI = SKILL_DIR / "scripts" / "wiki.py"
SKILL_MD = SKILL_DIR / "SKILL.md"
SAMPLE_NAMESPACE = SKILL_DIR / "examples" / "sample-namespace"
WORKCELL_WS = REPO / "scripts" / "workcell-ws"

KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
INTEGER_RE = re.compile(r"(?<![\w.-])\d+(?![\w.-])")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[*_`\"')\]]*\s+")

# Captured at import, before any test runs, so the "nothing under the real home" oracle is
# read against the state the suite started from.
REAL_HOME = Path(os.path.expanduser("~")).resolve()
REAL_HOME_STORE = REAL_HOME / ".workcell"


def _real_home_state() -> list[str] | None:
    if not REAL_HOME_STORE.is_dir():
        return None
    return sorted(path.name for path in REAL_HOME_STORE.iterdir())


REAL_HOME_STATE = _real_home_state()

# The paragraph every orchestrator skill carries verbatim (ADR 0007).
CANONICAL_BOUNDARY = (
    "You are the orchestrator ([ADR 0007](../../docs/adr/"
    "0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents, hold the human "
    "gates, run `git` / `jj` / `gh` for branch, merge, and issue-state operations, and read "
    "gate output and handoff records. You never read or edit the target project's code, run "
    "its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch "
    "is orchestration; reading a file's contents to judge it is not."
)

PROSE_ONE = "The integrator timed out waiting on the sandbox lock."
PROSE_TWO = "The same lock starved a second wave on a slower runner."


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_tree(root: Path) -> dict[str, str]:
    """Every path under root with a digest of its bytes, so `unchanged` is checkable."""
    state: dict[str, str] = {}
    if not root.exists():
        return state
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        relative = str(path.relative_to(root))
        if path.is_dir():
            state[relative + "/"] = "<dir>"
        else:
            state[relative] = sha256_bytes(path.read_bytes())
    return state


def section_body(text: str, title: str) -> str | None:
    """The body of the markdown section whose heading names `title`, up to the next
    heading of the same or a higher level."""
    lines = text.splitlines()
    start = None
    level = 0
    for number, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if match and title.lower() in match.group(2).lower():
            start = number + 1
            level = len(match.group(1))
            break
    if start is None:
        return None
    body: list[str] = []
    for line in lines[start:]:
        match = re.match(r"^(#{1,6})\s+", line)
        if match and len(match.group(1)) <= level:
            break
        body.append(line)
    return "\n".join(body)


class WikiTestCase(unittest.TestCase):
    """Throwaway home, throwaway store, throwaway repositories."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="wiki-tests-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.store = self.tmp / "wiki-home"
        self.store.mkdir()
        self.repos = self.tmp / "repos"
        self.repos.mkdir()
        self.jj_config = self.tmp / "jj.toml"
        self.jj_config.write_text(
            '[user]\nname = "wiki test"\nemail = "wiki@example.invalid"\n',
            encoding="utf-8",
        )

    # --- environment ------------------------------------------------------------------
    def env(self, **extra: str) -> dict[str, str]:
        environment = dict(os.environ)
        environment.update(
            {
                "HOME": str(self.home),
                "WORKCELL_WIKI_HOME": str(self.store),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_SYSTEM": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1",
                "JJ_CONFIG": str(self.jj_config),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        environment.update(extra)
        self.assertNotEqual(
            Path(environment["HOME"]).resolve(),
            REAL_HOME,
            "a wiki test must never run against the developer's real home",
        )
        return environment

    # --- process helpers --------------------------------------------------------------
    def run_command(self, argv, cwd: Path | None = None, env=None):
        return subprocess.run(
            [str(part) for part in argv],
            cwd=str(cwd or REPO),
            env=env or self.env(),
            text=True,
            capture_output=True,
            check=False,
        )

    def wiki(self, *args, cwd: Path | None = None, env=None):
        return self.run_command(
            [sys.executable, "-B", str(WIKI), *args], cwd=cwd, env=env
        )

    @staticmethod
    def output(result) -> str:
        return (result.stdout or "") + (result.stderr or "")

    def json_payload(self, result, what: str) -> dict:
        if result.returncode != 0:
            self.fail(
                f"{what} must exit 0; it exited {result.returncode}\n"
                f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
            )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail(
                f"{what} must print one JSON object on stdout; it printed "
                f"{result.stdout!r} (stderr: {result.stderr!r})"
            )
        self.assertIsInstance(payload, dict, f"{what} must print a JSON object")
        return payload

    def key_of(self, repo: Path) -> dict:
        return self.json_payload(
            self.wiki("key", "--repo", repo), f"wiki.py key --repo {repo}"
        )

    def refuses(self, result, what: str, *needles: str) -> None:
        self.assertNotEqual(
            result.returncode,
            0,
            f"{what} must exit non-zero\nstdout: {result.stdout!r}\n"
            f"stderr: {result.stderr!r}",
        )
        text = self.output(result)
        for needle in needles:
            self.assertIn(
                needle.lower(),
                text.lower(),
                f"{what} must name {needle!r} in its refusal; it said:\n{text}",
            )

    # --- repository fixtures ----------------------------------------------------------
    def git_repo(self, name: str, origin: str | None = None) -> Path:
        path = self.repos / name
        path.mkdir(parents=True)
        env = self.env()

        def run(*argv: str) -> None:
            subprocess.run(
                argv, cwd=str(path), env=env, text=True, capture_output=True, check=True
            )

        run("git", "-c", "init.defaultBranch=main", "init", "-q", ".")
        run("git", "config", "user.email", "wiki@example.invalid")
        run("git", "config", "user.name", "wiki test")
        (path / "seed.txt").write_text("seed\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "-c", "commit.gpgsign=false", "commit", "-qm", "init")
        if origin:
            run("git", "remote", "add", "origin", origin)
            # A remote-tracking ref so trunk() resolves without a network.
            run("git", "update-ref", "refs/remotes/origin/main", "HEAD")
            run(
                "git",
                "symbolic-ref",
                "refs/remotes/origin/HEAD",
                "refs/remotes/origin/main",
            )
        return path

    def jj_repo(self, name: str, origin: str) -> Path:
        path = self.git_repo(name, origin=origin)
        result = self.run_command(["jj", "git", "init", "--colocate", "."], cwd=path)
        self.assertEqual(
            result.returncode,
            0,
            f"jj git init --colocate failed: {self.output(result)}",
        )
        return path

    def evidence_file(self, repo: Path, name: str, body: str) -> Path:
        path = repo / name
        path.write_text(body, encoding="utf-8")
        return path

    def eval_mode(self, repo: Path) -> Path:
        marker = repo / ".workcell" / "eval-mode.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps({"mode": "eval", "task": "wiki-fixture"}), encoding="utf-8"
        )
        return marker

    # --- namespace helpers ------------------------------------------------------------
    def namespace_of(self, repo: Path) -> Path:
        return self.store / self.key_of(repo)["projectKey"]

    def init_namespace(self, repo: Path) -> Path:
        result = self.wiki("init", "--repo", repo)
        self.assertEqual(
            result.returncode, 0, f"wiki.py init must exit 0: {self.output(result)}"
        )
        return self.namespace_of(repo)

    def build_namespace(self, name: str, slug: str = "flaky-sandbox-lock"):
        """A repository, its namespace, one recorded raw bundle, and one pattern page."""
        repo = self.git_repo(name)
        namespace = self.init_namespace(repo)
        evidence = self.evidence_file(repo, "evidence.json", '{"gate": "green"}\n')
        recorded = self.wiki(
            "record",
            "--repo",
            repo,
            "--id",
            "raw-one",
            "--kind",
            "build-wave",
            "--summary",
            "wave 1 accepted",
            "--file",
            evidence,
        )
        self.assertEqual(
            recorded.returncode,
            0,
            f"wiki.py record must exit 0: {self.output(recorded)}",
        )
        written = self.wiki(
            "pattern",
            slug,
            "--repo",
            repo,
            "--evidence",
            "raw-one",
            "--note",
            PROSE_ONE,
        )
        self.assertEqual(
            written.returncode,
            0,
            f"wiki.py pattern must exit 0: {self.output(written)}",
        )
        return repo, namespace

    def read(self, path: Path, what: str) -> str:
        if not path.is_file():
            self.fail(f"{what} must exist at {path}")
        return path.read_text(encoding="utf-8")

    def pattern_page(self, namespace: Path, slug: str) -> str:
        return self.read(
            namespace / "patterns" / f"{slug}.md", f"the pattern page for {slug}"
        )

    @staticmethod
    def nonempty_lines(text: str) -> list[str]:
        return [line for line in text.splitlines() if line.strip()]


class ProjectKeyTests(WikiTestCase):
    def test_the_project_key_is_the_normalized_remote_and_falls_back_to_the_path(self):
        ssh = self.git_repo(
            "ssh-spelling", origin="git@github.com:anvil008/workcell.git"
        )
        https = self.git_repo(
            "https-spelling", origin="https://github.com/anvil008/workcell"
        )
        ssh_key = self.key_of(ssh)
        https_key = self.key_of(https)

        self.assertEqual(
            ssh_key.get("projectKey"),
            "github-com-anvil008-workcell",
            f"an ssh origin must normalize to the host-and-path key: {ssh_key}",
        )
        self.assertEqual(
            ssh_key.get("source"),
            "remote",
            f"a repository with an origin is keyed from the remote: {ssh_key}",
        )
        self.assertEqual(
            https_key.get("projectKey"),
            ssh_key.get("projectKey"),
            "the ssh and https spellings of one origin must collapse to one key: "
            f"{https_key} vs {ssh_key}",
        )
        self.assertEqual(https_key.get("source"), "remote", str(https_key))

        # No remote: the toplevel basename, reduced to the key character class, plus a
        # hash of the resolved absolute toplevel.
        remoteless = self.git_repo("Odd Repo.Name")
        payload = self.key_of(remoteless)
        key = payload.get("projectKey", "")
        self.assertEqual(
            payload.get("source"),
            "path",
            f"a repository with no origin falls back to the path source: {payload}",
        )
        self.assertRegex(
            key,
            r"^odd-repo-name-[0-9a-f]{8}$",
            "a remoteless key is the normalized toplevel basename plus 8 lowercase hex "
            f"digits; got {key!r}",
        )
        self.assertEqual(
            self.key_of(remoteless).get("projectKey"),
            key,
            "the path key must be stable across runs",
        )
        elsewhere = self.git_repo("Odd Repo.Name-copy")
        self.assertNotEqual(
            self.key_of(elsewhere).get("projectKey"),
            key,
            "two different toplevels must not collapse to one key",
        )

        for candidate in (ssh_key, https_key, payload, self.key_of(elsewhere)):
            printed = candidate.get("projectKey", "")
            self.assertRegex(
                printed,
                KEY_RE,
                "every key must obey the character class workcell-ws enforces "
                f"(^[a-z0-9][a-z0-9-]*$); got {printed!r}",
            )

    def test_every_workspace_of_one_repository_resolves_to_one_key(self):
        # git-only: workcell-ws makes a worktree, and the key must resolve through the
        # first `git worktree list --porcelain` entry back to the primary toplevel.
        git_primary = self.git_repo("git-fixture")
        git_sibling = self.add_workspace(git_primary)
        self.assert_one_key(git_primary, git_sibling, "git worktree")

        if shutil.which("jj") is None:
            self.skipTest("jj is not installed; the git half of this oracle ran")
        jj_primary = self.jj_repo(
            "jj-fixture", origin="https://example.invalid/anvil008/jj-fixture.git"
        )
        jj_sibling = self.add_workspace(jj_primary)
        self.assert_one_key(jj_primary, jj_sibling, "jj workspace")

    def add_workspace(self, primary: Path) -> Path:
        result = self.run_command(
            ["bash", str(WORKCELL_WS), "add", "feature/x", "--repo", str(primary)],
            cwd=primary,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"workcell-ws add feature/x failed: {self.output(result)}",
        )
        sibling = primary.parent / f"{primary.name}-feature-x"
        self.assertTrue(
            sibling.is_dir(),
            f"workcell-ws must have created {sibling}: {self.output(result)}",
        )
        return sibling

    def assert_one_key(self, primary: Path, sibling: Path, what: str) -> None:
        primary_key = self.key_of(primary)
        sibling_key = self.key_of(sibling)
        self.assertRegex(primary_key.get("projectKey", ""), KEY_RE, str(primary_key))
        self.assertEqual(
            sibling_key.get("projectKey"),
            primary_key.get("projectKey"),
            f"a {what} of one repository must answer with the primary's key: "
            f"{sibling_key} vs {primary_key}",
        )
        self.assertEqual(
            sibling_key.get("source"),
            primary_key.get("source"),
            f"a {what} must resolve the same source as its primary: "
            f"{sibling_key} vs {primary_key}",
        )


class NamespaceTests(WikiTestCase):
    def test_init_creates_the_namespace_under_the_configured_root(self):
        repo = self.git_repo("init-fixture")
        key = self.key_of(repo)["projectKey"]
        namespace = self.store / key

        first = self.wiki("init", "--repo", repo)
        self.assertEqual(
            first.returncode, 0, f"wiki.py init must exit 0: {self.output(first)}"
        )
        self.assertTrue(
            namespace.is_dir(),
            f"init must create the namespace at {namespace}; the store holds "
            f"{sorted(path.name for path in self.store.iterdir())}",
        )
        for relative in ("raw", "patterns"):
            self.assertTrue(
                (namespace / relative).is_dir(),
                f"init must create {relative}/ inside the namespace",
            )
        for relative in ("project.json", "index.md", "logs.md", "skill-impact.md"):
            self.assertTrue(
                (namespace / relative).is_file(),
                f"init must create {relative} inside the namespace",
            )

        identity = json.loads((namespace / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(identity.get("projectKey"), key, str(identity))
        self.assertEqual(identity.get("source"), "path", str(identity))
        self.assertEqual(
            identity.get("derivedFrom"),
            str(repo.resolve()),
            "project.json must record the toplevel the namespace was derived from: "
            f"{identity}",
        )
        self.assertTrue(
            isinstance(identity.get("createdAt"), str)
            and identity["createdAt"].strip(),
            f"project.json must record createdAt: {identity}",
        )

        before = digest_tree(namespace)
        second = self.wiki("init", "--repo", repo)
        self.assertEqual(
            second.returncode,
            0,
            f"a second init must exit 0: {self.output(second)}",
        )
        self.assertEqual(
            digest_tree(namespace),
            before,
            "a second init must leave every existing file byte-identical",
        )

        self.assertEqual(
            _real_home_state(),
            REAL_HOME_STATE,
            "the suite must never create anything under the real ~/.workcell",
        )

    def test_a_namespace_refuses_a_repository_it_was_not_created_for(self):
        origin = "git@github.com:anvil008/workcell.git"
        repo = self.git_repo("identity-fixture", origin=origin)
        namespace = self.init_namespace(repo)
        evidence = self.evidence_file(repo, "evidence.json", '{"gate": "green"}\n')

        identity_path = namespace / "project.json"
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        recorded = "git@github.com:someone-else/other-project.git"
        identity["derivedFrom"] = recorded
        identity_path.write_text(
            json.dumps(identity, indent=2) + "\n", encoding="utf-8"
        )

        before = digest_tree(namespace)
        commands = {
            "record": (
                "record",
                "--repo",
                repo,
                "--id",
                "raw-one",
                "--kind",
                "build-wave",
                "--summary",
                "wave 1",
                "--file",
                evidence,
            ),
            "pattern": (
                "pattern",
                "flaky-sandbox-lock",
                "--repo",
                repo,
                "--evidence",
                "raw-one",
                "--note",
                PROSE_ONE,
            ),
            "check": ("check", "--repo", repo),
        }
        for name, argv in commands.items():
            with self.subTest(command=name):
                result = self.wiki(*argv)
                self.refuses(
                    result, f"wiki.py {name} on a mismatched namespace", recorded
                )
                text = self.output(result)
                self.assertTrue(
                    origin in text or "github-com-anvil008-workcell" in text,
                    f"wiki.py {name} must name the resolved source as well as the "
                    f"recorded one; it said:\n{text}",
                )
                self.assertEqual(
                    digest_tree(namespace),
                    before,
                    f"a refused {name} must create and modify nothing in the namespace",
                )

    def test_eval_mode_neither_records_nor_consolidates(self):
        repo = self.git_repo("eval-mode-fixture")
        namespace = self.init_namespace(repo)
        evidence = self.evidence_file(repo, "evidence.json", '{"gate": "green"}\n')
        self.eval_mode(repo)
        before = digest_tree(namespace)

        commands = {
            "init": ("init", "--repo", repo),
            "record": (
                "record",
                "--repo",
                repo,
                "--id",
                "raw-one",
                "--kind",
                "build-wave",
                "--summary",
                "wave 1",
                "--file",
                evidence,
            ),
            "pattern": (
                "pattern",
                "flaky-sandbox-lock",
                "--repo",
                repo,
                "--evidence",
                "raw-one",
                "--note",
                PROSE_ONE,
            ),
        }
        for name, argv in commands.items():
            with self.subTest(command=name):
                result = self.wiki(*argv)
                self.refuses(result, f"wiki.py {name} in eval mode", "eval mode")
                self.assertEqual(
                    digest_tree(namespace),
                    before,
                    f"a refused {name} must create, modify, and remove nothing",
                )

        # The marker is read from the repository --repo names, not from the store: a
        # never-initialised repository in eval mode gains no namespace at all.
        fresh = self.git_repo("eval-mode-fresh")
        self.eval_mode(fresh)
        stores = sorted(path.name for path in self.store.iterdir())
        result = self.wiki("init", "--repo", fresh)
        self.refuses(
            result, "wiki.py init in a fresh eval-mode repository", "eval mode"
        )
        self.assertEqual(
            sorted(path.name for path in self.store.iterdir()),
            stores,
            "a refused init must create no namespace under the store",
        )

    def test_a_project_without_a_namespace_is_not_an_error(self):
        repo = self.git_repo("never-opted-in")
        key = self.key_of(repo)["projectKey"]

        result = self.wiki("status", "--repo", repo)
        payload = self.json_payload(
            result, "wiki.py status on a project with no namespace"
        )
        self.assertIs(
            payload.get("present"),
            False,
            f"status must report present: false rather than failing: {payload}",
        )
        self.assertEqual(
            payload.get("projectKey"),
            key,
            f"status must still carry the resolved project key: {payload}",
        )
        self.assertFalse(
            (self.store / key).exists(),
            "status must not create the namespace it reports as absent",
        )


class RawAndPatternTests(WikiTestCase):
    def test_raw_traces_are_write_once(self):
        repo = self.git_repo("raw-fixture")
        namespace = self.init_namespace(repo)
        first_file = self.evidence_file(repo, "gate.json", '{"gate": "green"}\n')
        second_file = self.evidence_file(repo, "handoff.json", '{"result": "ok"}\n')

        first = self.wiki(
            "record",
            "--repo",
            repo,
            "--id",
            "trace-alpha",
            "--kind",
            "build-wave",
            "--summary",
            "wave 1 accepted",
            "--file",
            first_file,
            "--file",
            second_file,
        )
        self.assertEqual(
            first.returncode, 0, f"wiki.py record must exit 0: {self.output(first)}"
        )
        self.assertIn(
            "trace-alpha",
            first.stdout,
            f"record must print the raw id it wrote; it printed {first.stdout!r}",
        )

        bundle = namespace / "raw" / "trace-alpha"
        self.assertTrue(bundle.is_dir(), f"record must create {bundle}")
        manifest = json.loads(
            self.read(bundle / "manifest.json", "the bundle manifest")
        )
        self.assertEqual(manifest.get("id"), "trace-alpha", str(manifest))
        self.assertEqual(manifest.get("kind"), "build-wave", str(manifest))
        self.assertEqual(manifest.get("summary"), "wave 1 accepted", str(manifest))
        self.assertTrue(
            isinstance(manifest.get("recordedAt"), str)
            and manifest["recordedAt"].strip(),
            f"the manifest must record recordedAt: {manifest}",
        )
        entries = manifest.get("files")
        self.assertIsInstance(
            entries, list, f"the manifest must list files: {manifest}"
        )
        self.assertEqual(
            sorted(Path(entry["path"]).name for entry in entries),
            sorted([first_file.name, second_file.name]),
            f"every supplied --file must be copied and listed: {manifest}",
        )
        for entry in entries:
            copied = bundle / entry["path"]
            self.assertTrue(copied.is_file(), f"{copied} must exist in the bundle")
            self.assertEqual(
                entry.get("sha256"),
                sha256_bytes(copied.read_bytes()),
                f"the manifest hash must match the copied bytes for {entry['path']}",
            )

        before = digest_tree(bundle)
        first_file.write_text('{"gate": "tampered"}\n', encoding="utf-8")
        second = self.wiki(
            "record",
            "--repo",
            repo,
            "--id",
            "trace-alpha",
            "--kind",
            "review-fix-loop",
            "--summary",
            "a different summary",
            "--file",
            first_file,
        )
        self.refuses(second, "a second record under an existing id", "trace-alpha")
        self.assertEqual(
            digest_tree(bundle),
            before,
            "a refused record must leave the manifest and every copied file "
            "byte-identical",
        )
        self.assertEqual(
            sorted(path.name for path in (namespace / "raw").iterdir()),
            ["trace-alpha"],
            "a refused record must create no second directory under raw/",
        )

    def test_a_pattern_page_accumulates_evidence_rather_than_being_rewritten(self):
        repo = self.git_repo("pattern-fixture")
        namespace = self.init_namespace(repo)
        evidence = self.evidence_file(repo, "evidence.json", '{"gate": "green"}\n')
        for raw_id in ("raw-one", "raw-two"):
            recorded = self.wiki(
                "record",
                "--repo",
                repo,
                "--id",
                raw_id,
                "--kind",
                "build-wave",
                "--summary",
                f"summary for {raw_id}",
                "--file",
                evidence,
            )
            self.assertEqual(
                recorded.returncode,
                0,
                f"wiki.py record {raw_id} must exit 0: {self.output(recorded)}",
            )

        slug = "flaky-sandbox-lock"
        logs = namespace / "logs.md"
        before_logs = len(self.nonempty_lines(self.read(logs, "logs.md")))

        first = self.wiki(
            "pattern",
            slug,
            "--repo",
            repo,
            "--evidence",
            "raw-one",
            "--note",
            PROSE_ONE,
        )
        self.assertEqual(
            first.returncode, 0, f"wiki.py pattern must exit 0: {self.output(first)}"
        )
        page_after_first = self.pattern_page(namespace, slug)
        self.assertIn(
            PROSE_ONE, page_after_first, "the first call's prose must be written"
        )
        rows = self.index_rows(namespace, slug)
        self.assertEqual(
            len(rows), 1, f"index.md must carry exactly one row for {slug}: {rows}"
        )
        self.assertIn(
            1,
            self.integers(rows[0]),
            f"the index row must show an occurrence count of 1 after one call: {rows[0]!r}",
        )
        after_first_logs = len(self.nonempty_lines(self.read(logs, "logs.md")))
        self.assertEqual(
            after_first_logs,
            before_logs + 1,
            "a pattern write must append exactly one line to logs.md",
        )

        second = self.wiki(
            "pattern",
            slug,
            "--repo",
            repo,
            "--evidence",
            "raw-two",
            "--note",
            PROSE_TWO,
        )
        self.assertEqual(
            second.returncode, 0, f"wiki.py pattern must exit 0: {self.output(second)}"
        )
        page = self.pattern_page(namespace, slug)
        self.assertIn(
            PROSE_ONE,
            page,
            "a second call must leave the first call's prose present verbatim; the page "
            f"now reads:\n{page}",
        )
        self.assertIn(
            PROSE_TWO, page, f"the second call's prose must be added:\n{page}"
        )

        cited = {
            raw_id: [
                line
                for line in page.splitlines()
                if raw_id in line and DATE_RE.search(line)
            ]
            for raw_id in ("raw-one", "raw-two")
        }
        for raw_id, lines in cited.items():
            self.assertEqual(
                len(lines),
                1,
                f"the page must carry exactly one dated evidence entry citing {raw_id}; "
                f"found {lines} in:\n{page}",
            )

        rows = self.index_rows(namespace, slug)
        self.assertEqual(
            len(rows), 1, f"index.md must carry exactly one row for {slug}: {rows}"
        )
        self.assertIn(
            2,
            self.integers(rows[0]),
            f"the index row must show an occurrence count of 2 for {slug}: {rows[0]!r}",
        )
        self.assertEqual(
            len(self.nonempty_lines(self.read(logs, "logs.md"))),
            after_first_logs + 1,
            "the second pattern write must append exactly one further line to logs.md",
        )

    def index_rows(self, namespace: Path, slug: str) -> list[str]:
        text = self.read(namespace / "index.md", "index.md")
        return [line for line in text.splitlines() if slug in line]

    @staticmethod
    def integers(line: str) -> set[int]:
        return {int(token) for token in INTEGER_RE.findall(line)}


class CheckTests(WikiTestCase):
    def test_check_names_index_drift_a_dangling_citation_and_a_mutated_trace(self):
        slug = "flaky-sandbox-lock"

        repo, namespace = self.build_namespace("check-clean", slug=slug)
        clean = self.wiki("check", "--repo", repo)
        self.assertEqual(
            clean.returncode,
            0,
            f"check must exit 0 on a freshly built namespace: {self.output(clean)}",
        )

        # 1. A pattern page whose row was deleted from index.md.
        repo, namespace = self.build_namespace("check-index-drift", slug=slug)
        index = namespace / "index.md"
        kept = [
            line
            for line in self.read(index, "index.md").splitlines()
            if slug not in line
        ]
        index.write_text("\n".join(kept) + "\n", encoding="utf-8")
        self.refuses(
            self.wiki("check", "--repo", repo),
            "check on a namespace whose index lost a pattern row",
            slug,
        )

        # 2. A page citing a raw id with no directory under raw/.
        repo, namespace = self.build_namespace("check-dangling", slug=slug)
        page_path = namespace / "patterns" / f"{slug}.md"
        page = self.read(page_path, "the pattern page")
        page_path.write_text(page.replace("raw-one", "raw-missing-9"), encoding="utf-8")
        self.refuses(
            self.wiki("check", "--repo", repo),
            "check on a page citing a raw id with no bundle",
            "raw-missing-9",
        )

        # 3. A recorded evidence file whose bytes changed after its hash was written.
        repo, namespace = self.build_namespace("check-mutated", slug=slug)
        bundle = namespace / "raw" / "raw-one"
        manifest = json.loads(
            self.read(bundle / "manifest.json", "the bundle manifest")
        )
        entries = manifest.get("files")
        self.assertTrue(entries, f"the manifest must list the copied files: {manifest}")
        target = bundle / entries[0]["path"]
        target.write_bytes(target.read_bytes() + b"tampered\n")
        result = self.wiki("check", "--repo", repo)
        self.refuses(result, "check on a mutated raw trace", "raw-one")
        self.assertIn(
            Path(entries[0]["path"]).name,
            self.output(result),
            "check must name the mutated file, not only the bundle",
        )


class SkillContractTests(WikiTestCase):
    def skill_text(self) -> str:
        return self.read(SKILL_MD, "skills/wiki/SKILL.md")

    @staticmethod
    def sentences(text: str) -> list[str]:
        flat = re.sub(r"\s+", " ", text).strip()
        return [part for part in SENTENCE_SPLIT.split(flat) if part]

    def sentence(self, text: str, patterns, why: str) -> str:
        matches = [
            candidate
            for candidate in self.sentences(text)
            if all(re.search(pattern, candidate, re.IGNORECASE) for pattern in patterns)
        ]
        self.assertTrue(
            matches,
            f"{why}\nNo single statement in skills/wiki/SKILL.md matched all of "
            f"{patterns!r}.",
        )
        return matches[0]

    def test_the_skill_contract_states_its_boundaries(self):
        text = self.skill_text()
        self.assertIn(
            CANONICAL_BOUNDARY,
            text,
            "skills/wiki/SKILL.md must carry the canonical ADR-0007 orchestrator "
            "paragraph verbatim",
        )
        self.sentence(
            text,
            [r"(no|without a|absent) namespace", r"(no|never|not) dispatch"],
            "the opt-in rule: a project with no namespace means no dispatch at all",
        )
        self.sentence(
            text,
            [
                r"\b(one|single|exactly one)\b",
                r"documenter",
                r"agents/handoff\.md",
                r"ownership",
                r"namespace",
            ],
            "consolidation is one `documenter` dispatch conforming to `agents/handoff.md` "
            "whose `ownership` is the resolved namespace path",
        )
        self.sentence(
            text,
            [r"wiki\.py", r"never", r"editor"],
            "the agent writes only through `wiki.py` and never with an editor tool",
        )
        self.sentence(
            text,
            [r"wiki\.py check|`check`", r"(exit|exits|exiting) (zero|0)", r"gate"],
            "`wiki.py check` exiting zero is the completion gate",
        )
        self.sentence(
            text,
            [r"specifier", r"builder", r"reviewer", r"integrator", r"never", r"wiki"],
            "the standing boundary: runtime agents are never given the wiki",
        )
        self.sentence(
            text,
            [r"pattern", r"(never|not)", r"shared", r"skills/"],
            "project patterns never amend Workcell's shared `skills/`",
        )

    def test_the_shipped_offline_demonstration_runs(self):
        text = self.skill_text()
        section = section_body(text, "Offline demonstration")
        self.assertIsNotNone(
            section,
            "skills/wiki/SKILL.md must carry an `Offline demonstration` section",
        )
        commands = [
            line.strip()
            for block in re.findall(r"```[a-zA-Z0-9]*\n(.*?)```", section, re.DOTALL)
            for line in block.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertTrue(
            commands,
            "the `Offline demonstration` section must carry at least one runnable "
            f"command; the section reads:\n{section}",
        )
        self.assertTrue(
            SAMPLE_NAMESPACE.is_dir(),
            f"the demonstration must ship a sample namespace at {SAMPLE_NAMESPACE}",
        )

        for command in commands:
            self.assertIn(
                "--namespace",
                command,
                f"a demonstration command must address the namespace directly: {command}",
            )
            self.assertIn(
                "skills/wiki/examples/sample-namespace",
                command,
                f"a demonstration command must run against the shipped sample: {command}",
            )
            self.assertNotRegex(
                command,
                r"(?i)(\bgh\b|\bcurl\b|\bwget\b|https?://|\bTask\b|subagent)",
                f"a demonstration command must touch no GitHub endpoint and no "
                f"subagent: {command}",
            )

        before_repo = digest_tree(SKILL_DIR)
        for command in commands:
            result = self.run_command(["bash", "-c", command], cwd=REPO)
            self.assertEqual(
                result.returncode,
                0,
                f"the shipped demonstration command must exit 0: {command}\n"
                f"{self.output(result)}",
            )
        self.assertEqual(
            digest_tree(SKILL_DIR),
            before_repo,
            "the demonstration must change no tracked file in the repository",
        )
        self.assertEqual(
            digest_tree(self.home),
            {},
            "the demonstration must write nothing under the home directory",
        )
        self.assertEqual(
            _real_home_state(),
            REAL_HOME_STATE,
            "the demonstration must write nothing under the real ~/.workcell",
        )


class RepositoryGateTests(WikiTestCase):
    def test_the_repositorys_own_gates_stay_green_with_an_eighteenth_skill(self):
        case_path = REPO / "evals" / "cases" / "skills" / "wiki.json"
        self.assertTrue(
            case_path.is_file(),
            f"the routing case for the skill must land with it: {case_path}",
        )
        case = json.loads(case_path.read_text(encoding="utf-8"))
        self.assertEqual(case.get("name"), "wiki", str(case))
        self.assertEqual(case.get("kind"), "skill", str(case))
        positives = case.get("trigger", {}).get("positive", [])
        negatives = case.get("trigger", {}).get("negative", [])
        self.assertGreaterEqual(
            len(positives), 3, f"the case needs three or more positive prompts: {case}"
        )
        self.assertGreaterEqual(
            len(negatives), 2, f"the case needs two negative prompts: {case}"
        )
        for negative in negatives:
            self.assertTrue(
                isinstance(negative.get("owner"), str) and negative["owner"].strip(),
                f"every negative names its owner: {negative}",
            )
        self.assertTrue(
            any(item.get("kind") == "dialogue" for item in case.get("evals", [])),
            f"the case needs one dialogue eval: {case}",
        )

        gates = (
            [sys.executable, str(REPO / "evals" / "run_evals.py"), "--structural"],
            [sys.executable, str(REPO / "evals" / "run_evals.py"), "--min-rank1", "77"],
            ["bash", str(REPO / "scripts" / "tests" / "test_install.sh")],
        )
        for argv in gates:
            with self.subTest(gate=argv[-1]):
                result = self.run_command(argv, cwd=REPO)
                self.assertEqual(
                    result.returncode,
                    0,
                    f"{' '.join(argv)} must exit 0:\n{self.output(result)[-4000:]}",
                )

        run_evals = self.load_run_evals()
        errors, documents, _cases = run_evals.structural_errors(REPO)
        self.assertEqual(errors, [], "the structural checks must be clean")
        self.assertIn(
            "skill:wiki",
            documents,
            "skills/wiki/SKILL.md must describe a routable skill",
        )
        index = run_evals.TfidfIndex(documents)
        for entry in positives:
            ranking = [doc_id for doc_id, _score in index.scores(entry["prompt"])]
            rank = ranking.index("skill:wiki") + 1
            self.assertLessEqual(
                rank,
                entry["top_k"],
                f"the prompt {entry['prompt']!r} must retrieve skill:wiki within "
                f"top_k={entry['top_k']}; it ranked {rank} behind {ranking[:3]}",
            )

        agent_owned = {
            path.name for path in (REPO / "agents" / "agy").glob("*/skills/*")
        }
        expected = sorted(
            path.name
            for path in (REPO / "skills").iterdir()
            if path.is_dir() and path.name not in agent_owned
        )
        links_dir = REPO / "plugins" / "agy" / "skills"
        actual = sorted(path.name for path in links_dir.iterdir())
        self.assertEqual(
            actual,
            expected,
            "plugins/agy/skills must hold exactly the non-agent-owned skills/*/ "
            "directories",
        )
        for link in links_dir.iterdir():
            self.assertTrue(
                link.exists(), f"plugins/agy/skills/{link.name} is a broken symlink"
            )

    @staticmethod
    def load_run_evals():
        evals_dir = str(REPO / "evals")
        if evals_dir not in sys.path:
            sys.path.insert(0, evals_dir)
        import run_evals

        return run_evals


if __name__ == "__main__":
    unittest.main()
