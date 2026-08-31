import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "loop_state.py"
SKILL_MD = ROOT / "SKILL.md"
SKILLS_DIR = ROOT.parents[0]
REVIEW_EXAMPLES = SKILLS_DIR / "code-review" / "examples"

# The exit step the loop gains: reached on every stop status, opt-in, and the only
# place the wiki is named.
EXIT_SECTION = "When the loop stops"
TICK_SECTION = "Every tick"

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[*_`\"')\]]*\s+")


def run(state, *args):
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--state", str(state), *map(str, args)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def section_body(text, title):
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
    end = len(lines)
    for number in range(start, len(lines)):
        match = re.match(r"^(#{1,6})\s+", lines[number])
        if match and len(match.group(1)) <= level:
            end = number
            break
    return "\n".join(lines[start:end])


def numbered_steps(section):
    """The numbered items of `section`'s ordered list, as {number: text}. Indented
    continuation lines belong to the item above them; an unindented paragraph closes
    the list, so trailing prose is never mistaken for a step."""
    steps = {}
    current = None
    for line in section.splitlines():
        match = re.match(r"^ {0,3}(\d+)\.\s+(.*)$", line)
        if match:
            current = int(match.group(1))
            steps[current] = match.group(2)
            continue
        if not line.strip():
            continue
        if current is not None and line[:1].isspace():
            steps[current] += " " + line.strip()
            continue
        current = None
    return steps


def fenced_commands(section):
    """Every runnable command line inside `section`'s fenced code blocks, with
    continuations joined, comments and blank lines dropped."""
    commands = []
    for block in re.findall(r"```[a-zA-Z0-9]*\n(.*?)```", section, re.DOTALL):
        joined = re.sub(r"\\\n\s*", " ", block)
        for line in joined.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                commands.append(stripped)
    return commands


def review(findings, verdict="block"):
    return {"verdict": verdict, "findings": findings}


def finding(claim, file="src/a.py", severity="high"):
    return {"file": file, "claim": claim, "severity": severity}


class ReviewFixLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "loop.json"

    def write_review(self, name, payload):
        path = Path(self.tmp.name) / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_init_defaults_to_loop_branch_and_ten_passes(self):
        result = run(self.state, "init")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["branch"], "loop-branch")
        self.assertEqual(output["maxIterations"], 10)
        self.assertEqual(output["iteration"], 0)
        self.assertTrue(output["continue"])

    def test_init_refuses_to_clobber_a_running_loop_without_force(self):
        self.assertEqual(run(self.state, "init").returncode, 0)
        clobber = run(self.state, "init")
        self.assertNotEqual(clobber.returncode, 0)
        self.assertIn("already exists", clobber.stderr.lower())
        self.assertEqual(run(self.state, "init", "--force").returncode, 0)

    def test_record_without_init_is_an_error(self):
        source = self.write_review("r.json", review([finding("x")]))
        result = run(self.state, "record", source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("run `init` first", result.stderr)

    def test_empty_findings_converge(self):
        run(self.state, "init")
        source = self.write_review("clean.json", review([], verdict="approve"))
        output = json.loads(run(self.state, "record", source).stdout)
        self.assertEqual(output["status"], "converged")
        self.assertFalse(output["continue"])

    def test_progress_keeps_the_loop_running(self):
        run(self.state, "init")
        first = self.write_review("a.json", review([finding("one"), finding("two")]))
        second = self.write_review("b.json", review([finding("two")]))
        self.assertTrue(json.loads(run(self.state, "record", first).stdout)["continue"])
        output = json.loads(run(self.state, "record", second).stdout)
        self.assertTrue(output["continue"])
        self.assertEqual(output["iteration"], 2)

    def test_an_identical_second_pass_stalls_the_loop(self):
        """The fixer changed nothing that mattered; another pass would waste a review."""
        run(self.state, "init")
        same = self.write_review("same.json", review([finding("one"), finding("two")]))
        self.assertTrue(json.loads(run(self.state, "record", same).stdout)["continue"])
        output = json.loads(run(self.state, "record", same).stdout)
        self.assertEqual(output["status"], "stalled")
        self.assertFalse(output["continue"])
        self.assertIn("identical finding set", output["reason"])

    def test_fingerprint_ignores_order_and_line_but_not_content(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import loop_state

        a, b = finding("one"), finding("two", file="src/b.py")
        self.assertEqual(loop_state.fingerprint([a, b]), loop_state.fingerprint([b, a]))
        moved = dict(a, line=999)
        self.assertEqual(loop_state.fingerprint([a]), loop_state.fingerprint([moved]))
        self.assertNotEqual(loop_state.fingerprint([a]), loop_state.fingerprint([a, b]))

    def test_loop_is_bounded_even_when_findings_keep_changing(self):
        """The bound is the safety property: a fixer that trades one finding for
        another must not loop forever."""
        run(self.state, "init", "--max-iterations", "3")
        statuses = []
        for n in range(3):
            source = self.write_review(f"r{n}.json", review([finding(f"claim-{n}")]))
            statuses.append(
                json.loads(run(self.state, "record", source).stdout)["status"]
            )
        self.assertEqual(statuses, ["running", "running", "exhausted"])

        extra = self.write_review("extra.json", review([finding("another")]))
        refused = run(self.state, "record", extra)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("already finished", refused.stderr.lower())

    def test_status_reports_without_advancing(self):
        run(self.state, "init")
        source = self.write_review("r.json", review([finding("one")]))
        run(self.state, "record", source)
        first = json.loads(run(self.state, "status").stdout)
        second = json.loads(run(self.state, "status").stdout)
        self.assertEqual(first, second)
        self.assertEqual(first["iteration"], 1)

    def test_malformed_input_is_rejected(self):
        run(self.state, "init")
        cases = (
            ({"findings": []}, "verdict must be one of"),
            ({"verdict": "block", "findings": "nope"}, "must be an array"),
            (
                {"verdict": "block", "findings": [{"file": "a.py", "claim": ""}]},
                "non-empty string",
            ),
        )
        for payload, message in cases:
            with self.subTest(message=message):
                source = self.write_review("bad.json", payload)
                result = run(self.state, "record", source)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr.lower())

        bad_branch = run(
            Path(self.tmp.name) / "b.json", "init", "--branch", "bad branch"
        )
        self.assertNotEqual(bad_branch.returncode, 0)
        self.assertIn("plain branch name", bad_branch.stderr)

    def test_accepts_a_real_merged_review_from_the_code_review_skill(self):
        run(self.state, "init")
        result = run(self.state, "record", REVIEW_EXAMPLES / "expected-review.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output["continue"])
        self.assertEqual(output["latest"]["findings"], 2)
        self.assertEqual(output["latest"]["blocking"], 1)

    def test_skill_publishes_its_branch_bound_and_stop_conditions(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "loop-branch",
            "--max-iterations 10",
            "code-review",
            "builder",
            "converged",
            "stalled",
            "exhausted",
            "Never run this loop on `main`",
            "never merge `loop-branch`",
            "loop_state.py record",
        ):
            self.assertIn(phrase, skill)

    def test_nit_only_review_converges_at_medium_threshold(self):
        """Findings below --min-severity are reported but never block convergence."""
        run(self.state, "init", "--min-severity", "medium")
        source = self.write_review(
            "nits.json",
            review(
                [
                    finding("trailing space", severity="nit"),
                    finding("rename", severity="nit"),
                ],
                verdict="approve-with-nits",
            ),
        )
        result = run(self.state, "record", source)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "converged")
        self.assertFalse(output["continue"])
        self.assertEqual(output["latest"]["findings"], 2)
        self.assertEqual(output["latest"]["blocking"], 0)
        self.assertEqual(output["minSeverity"], "medium")

    def test_findings_at_threshold_still_block(self):
        run(self.state, "init", "--min-severity", "medium")
        source = self.write_review(
            "m.json",
            review(
                [finding("real", severity="medium"), finding("tidy", severity="low")],
            ),
        )
        output = json.loads(run(self.state, "record", source).stdout)
        self.assertEqual(output["status"], "running")
        self.assertEqual(output["latest"]["blocking"], 1)

    def test_invalid_min_severity_is_rejected(self):
        result = run(self.state, "init", "--min-severity", "bogus")
        self.assertNotEqual(result.returncode, 0)
        for value in ("critical", "high", "medium", "low", "nit"):
            self.assertIn(value, result.stderr)
        self.assertFalse(self.state.exists())

    def test_skill_states_driver_requirement_and_uses_jj_branching(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("/loop", skill)
        self.assertIn("Claude Code", skill)
        self.assertRegex(skill, r"(?i)manual")
        self.assertNotIn("git switch -c", skill)
        self.assertNotIn("/tmp", skill)
        self.assertIn("--min-severity", skill)


class SkillProseTestCase(unittest.TestCase):
    """Statement-level reading of `skills/review-fix-loop/SKILL.md`. A contract that
    holds only across two paragraphs is not a contract an agent obeys under load, so
    each oracle asks for one statement carrying the whole rule."""

    def skill(self):
        self.assertTrue(SKILL_MD.is_file(), f"{SKILL_MD} must exist")
        text = SKILL_MD.read_text(encoding="utf-8")
        self.assertTrue(text.strip(), f"{SKILL_MD} must not be empty")
        return text

    def section(self, title):
        body = section_body(self.skill(), title)
        self.assertIsNotNone(
            body,
            f"skills/review-fix-loop/SKILL.md must carry a `{title}` section",
        )
        return body

    @staticmethod
    def sentences(text):
        flat = re.sub(r"\s+", " ", text).strip()
        return [part for part in SENTENCE_SPLIT.split(flat) if part]

    def sentence(self, text, patterns, why):
        matches = [
            candidate
            for candidate in self.sentences(text)
            if all(re.search(pattern, candidate, re.IGNORECASE) for pattern in patterns)
        ]
        self.assertTrue(
            matches,
            f"{why}\nNo single statement in skills/review-fix-loop/SKILL.md matched "
            f"all of {patterns!r}.\nSearched:\n{text}",
        )
        return matches[0]

    def exit_step(self, pattern):
        """The numbered steps of the exit procedure whose text matches `pattern`."""
        steps = numbered_steps(self.section(EXIT_SECTION))
        self.assertTrue(
            steps,
            f"the `{EXIT_SECTION}` section must lay out a numbered procedure, so the "
            "order of its steps is a contract rather than a suggestion",
        )
        return [
            (number, body)
            for number, body in sorted(steps.items())
            if re.search(pattern, body, re.IGNORECASE)
        ]


class LoopExitConsolidationTests(SkillProseTestCase):
    def test_consolidation_runs_on_every_stop_status(self):
        """`stalled` and `exhausted` are the most informative endings the loop
        produces, so the exit step must claim them by name rather than only the
        happy one."""
        section = self.section(EXIT_SECTION)
        self.sentence(
            section,
            [
                r"\bconverged\b",
                r"\bstalled\b",
                r"\bexhausted\b",
                r"consolidat|record|wiki",
            ],
            f"the `{EXIT_SECTION}` section must name `converged`, `stalled` and "
            "`exhausted` together in one statement as the endings that consolidate, "
            "so an unhappy ending records its evidence rather than discarding it",
        )

    def test_the_opt_in_check_is_a_command_not_a_directory_test(self):
        """The store lives outside every repository, so opting in is a question only
        `wiki.py status` can answer — a directory test inside the working copy would
        answer it wrongly and silently."""
        text = self.skill()
        section = self.section(EXIT_SECTION)
        self.assertIn(
            "wiki.py status --repo .",
            section,
            f"the `{EXIT_SECTION}` section must run "
            "`python3 skills/wiki/scripts/wiki.py status --repo .` as its first step",
        )
        asked = self.exit_step(r"wiki\.py status")
        self.assertTrue(
            asked,
            f"a numbered step of `{EXIT_SECTION}` must run `wiki.py status --repo .`",
        )
        for later, what in (
            (self.exit_step(r"wiki\.py record"), "the record"),
            (self.exit_step(r"documenter"), "the documenter dispatch"),
        ):
            if later:
                self.assertLess(
                    asked[0][0],
                    later[0][0],
                    "the opt-in check must condition the whole exit step: "
                    f"`wiki.py status` is step {asked[0][0]} and {what} is step "
                    f"{later[0][0]}",
                )
        self.sentence(
            section,
            [
                (
                    r"present`?:?\s*(is\s+)?`?false"
                    r"|no namespace|without a namespace|absent namespace"
                    r"|namespace is absent|not present"
                ),
                r"(no|never|nothing|neither)\b.{0,140}?record",
                r"(no|never|nothing|neither|nor)\b.{0,140}?dispatch",
            ],
            "one statement must say that an absent namespace ends the loop exactly as "
            "it ends today — naming the absent namespace, the absence of any record, "
            "and the absence of any dispatch together",
        )
        # `~/.workcell/wiki/<project-key>` is the store outside the repository; a
        # `.workcell/wiki/` written relative to the working copy is the directory test
        # this contract exists to forbid.
        stray = re.search(r"(?<!~/)(?<!HOME/)\.workcell/wiki", text)
        self.assertIsNone(
            stray,
            "the opt-in check is a command, never a directory test: "
            "skills/review-fix-loop/SKILL.md must not name a repository-relative "
            "`.workcell/wiki/` path"
            + (
                f"; found {text[max(0, stray.start() - 60) : stray.end() + 60]!r}"
                if stray
                else ""
            ),
        )

    def test_evidence_is_recorded_before_the_dispatch(self):
        """The raw bundle is what the dispatch cites, so a dispatch that runs first
        has nothing to point at."""
        recorded = self.exit_step(r"wiki\.py record")
        dispatched = self.exit_step(r"documenter")
        self.assertTrue(
            recorded,
            f"a numbered step of `{EXIT_SECTION}` must run `wiki.py record`",
        )
        self.assertTrue(
            dispatched,
            f"a numbered step of `{EXIT_SECTION}` must dispatch the `documenter`",
        )
        self.assertLess(
            recorded[0][0],
            dispatched[0][0],
            "`wiki.py record` must come before the `documenter` dispatch in the "
            f"numbered exit procedure; record is step {recorded[0][0]} and the "
            f"dispatch is step {dispatched[0][0]}",
        )
        self.sentence(
            self.section(EXIT_SECTION),
            [r"raw id", r"print|record", r"cite|carr|quote|name"],
            "the exit step must say that the dispatch cites the raw id `record` printed",
        )

    def test_the_dispatch_is_one_documenter_scoped_to_the_resolved_namespace(self):
        """One dispatch, because a fan-out would race on the same append-only pages;
        and its ownership is whatever `status` resolved, not a path written by hand."""
        dispatched = self.exit_step(r"documenter")
        self.assertTrue(
            dispatched,
            f"a numbered step of `{EXIT_SECTION}` must dispatch the `documenter`",
        )
        step = " ".join(body for _, body in dispatched)
        for needle in ("agents/handoff.md", "skills/wiki/references/wiki-layout.md"):
            self.assertIn(
                needle,
                step,
                f"the documenter dispatch must name `{needle}`; the step reads:\n{step}",
            )
        self.sentence(
            step,
            [r"\b(one|a single|exactly one)\b", r"documenter", r"dispatch"],
            "the dispatch step must describe exactly one `documenter` dispatch rather "
            "than a fan-out",
        )
        self.sentence(
            step,
            [r"ownership", r"namespace"],
            "the dispatch must carry the namespace path as its `ownership`",
        )
        self.sentence(
            step,
            [r"resolv", r"dispatch time|literal|hard-cod"],
            "the namespace path must be resolved at dispatch time rather than written "
            "as a literal",
        )
        self.assertNotRegex(
            step,
            r"\.workcell/wiki/[A-Za-z0-9]",
            "the ownership path must stay a placeholder such as "
            "`~/.workcell/wiki/<project-key>/**`, never a hard-coded project key",
        )

    def test_the_agent_writes_only_through_the_cli(self):
        """One CLI as the sole writer is what keeps write-once bundles, append-only
        pages, and `check`'s invariants true."""
        self.sentence(
            self.section(EXIT_SECTION),
            [r"prose", r"wiki\.py", r"\bnever\b", r"edit", r"namespace|directly"],
            "one statement must say the consolidating agent passes its prose to "
            "`wiki.py` and never edits a file in the namespace directly",
        )

    def test_the_gate_is_wiki_check_not_a_claim(self):
        """Reading a file's contents to judge it is not orchestration; `check` is the
        judgement the orchestrator is allowed to make."""
        section = self.section(EXIT_SECTION)
        self.sentence(
            section,
            [r"wiki\.py check|`check`", r"exit(s|ing)?\s+(zero|0)"],
            "the exit step must complete on `wiki.py check` exiting zero",
        )
        self.sentence(
            section,
            [r"never|not\b|rather than", r"read", r"pattern page"],
            "the exit step must say the orchestrator does not read the pattern pages "
            "to judge them",
        )

    def test_the_loop_fixer_is_never_handed_the_wiki(self):
        """The brief is the only way the wiki could reach the fixer, so the boundary
        is restated where it could be violated."""
        tick = self.section(TICK_SECTION)
        steps = numbered_steps(tick)
        self.assertTrue(
            steps, f"the `{TICK_SECTION}` section must keep its numbered steps"
        )
        fix = " ".join(
            body
            for _, body in sorted(steps.items())
            if re.search(r"\bbuilder\b", body, re.IGNORECASE)
        )
        self.assertTrue(
            fix,
            f"the `{TICK_SECTION}` section must keep a step that dispatches the builder",
        )
        self.sentence(
            fix,
            [r"mode:\s*`?loop", r"\bnever\b", r"\bwiki\b", r"namespace", r"finding"],
            "the builder-dispatch step must say in one statement that the `mode: loop` "
            "brief carries the findings and never the wiki or the namespace path",
        )

    def test_the_loops_existing_contracts_survive(self):
        """A regression guard, green today and required to stay green: the exit step
        is an addition, and it must not cost the loop its bound, its stop table, its
        branch refusal, or its shipped demonstration."""
        text = self.skill()
        for phrase in (
            "--min-severity",
            "mode: loop",
            "agents/handoff.md",
            "Never run this loop on `main`",
            "init --force",
            "loop_state.py record",
        ):
            self.assertTrue(
                phrase in text,
                f"skills/review-fix-loop/SKILL.md must keep `{phrase}`",
            )
        for status in ("converged", "stalled", "exhausted"):
            self.assertRegex(
                text,
                rf"\|\s*`{status}`\s*\|",
                f"the stop-status table must keep its `{status}` row",
            )

        commands = fenced_commands(self.section("Offline demonstration"))
        self.assertTrue(
            commands,
            "the `Offline demonstration` section must keep at least one runnable command",
        )
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        with tempfile.TemporaryDirectory() as sandbox:
            os.symlink(SKILLS_DIR, Path(sandbox) / "skills")
            for command in commands:
                argv = shlex.split(command)
                if argv and argv[0] == "python3":
                    argv[0] = sys.executable
                result = subprocess.run(
                    argv,
                    cwd=sandbox,
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"the shipped demonstration command must still exit 0: {command}\n"
                    f"{result.stdout}\n{result.stderr}",
                )


if __name__ == "__main__":
    unittest.main()
