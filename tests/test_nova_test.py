"""Unit tests for the nova-test quiet test runner."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
NOVA_TEST = ROOT / "tools/nova-test"

from importlib.machinery import SourceFileLoader
nova_test = SourceFileLoader("nova_test", str(NOVA_TEST)).load_module()


class NovaTestCLITests(unittest.TestCase):
    def test_success_compact_output_and_exit_code_0(self):
        # Command emitting routine test noise (test_... ok) followed by unittest summary
        script = (
            "import sys\n"
            "for i in range(20):\n"
            "    sys.stderr.write(f'test_{i} (mod.Test) ... ok\\n')\n"
            "sys.stderr.write('----------------------------------------------------------------------\\n')\n"
            "sys.stderr.write('Ran 20 tests in 0.052s\\n\\nOK\\n')\n"
        )
        cmd = [str(NOVA_TEST), sys.executable, "-c", script]
        proc = subprocess.run(cmd, capture_output=True, text=True)

        self.assertEqual(proc.returncode, 0)
        # Compact summary emitted to stdout
        self.assertIn("✓ [nova-test] Succeeded in", proc.stdout)
        self.assertIn("(exit 0)", proc.stdout)
        self.assertIn("Ran 20 tests in 0.052s", proc.stdout)
        self.assertIn("OK", proc.stdout)
        # Verbose line-by-line output suppressed
        self.assertNotIn("test_0 (mod.Test) ... ok", proc.stdout)
        self.assertNotIn("test_19 (mod.Test) ... ok", proc.stdout)
        self.assertNotIn("test_0", proc.stderr)

    def test_failure_outputs_full_raw_stdout_and_stderr_and_original_exit_code(self):
        script = (
            "import sys\n"
            "sys.stdout.write('diagnostic stdout detail\\n')\n"
            "sys.stderr.write('Traceback (most recent call last):\\n')\n"
            "sys.stderr.write('AssertionError: expected True but got False\\n')\n"
            "sys.exit(42)\n"
        )
        cmd = [str(NOVA_TEST), sys.executable, "-c", script]
        proc = subprocess.run(cmd, capture_output=True, text=True)

        self.assertEqual(proc.returncode, 42)
        # Failure header on stderr
        self.assertIn("✗ [nova-test] Failed with exit code 42 in", proc.stderr)
        # Raw untouched stdout and stderr preserved
        self.assertIn("diagnostic stdout detail", proc.stdout)
        self.assertIn("Traceback (most recent call last):", proc.stderr)
        self.assertIn("AssertionError: expected True but got False", proc.stderr)

    def test_verbose_bypass_flag(self):
        # Using -v bypasses quiet filtering
        script = "import sys; print('verbose line 1'); print('verbose line 2')"
        for flag in ("-v", "--verbose"):
            cmd = [str(NOVA_TEST), flag, sys.executable, "-c", script]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("verbose line 1", proc.stdout)
            self.assertIn("verbose line 2", proc.stdout)
            self.assertNotIn("✓ [nova-test]", proc.stdout)

    def test_arbitrary_argv_with_spaces_quotes_and_pipes(self):
        # Argument with spaces, single quotes, double quotes, and pipe character
        complex_arg = 'foo "bar" \'baz\' | qux & 123'
        cmd = [
            str(NOVA_TEST),
            sys.executable,
            "-c",
            "import sys; print(f'received: {sys.argv[1]}')",
            complex_arg,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("✓ [nova-test] Succeeded in", proc.stdout)
        self.assertIn(f"received: {complex_arg}", proc.stdout)

        # Pipeline execution via shell command
        pipe_cmd = [
            str(NOVA_TEST),
            "sh",
            "-c",
            "printf 'hello pipe\n' | tr 'a-z' 'A-Z'",
        ]
        proc_pipe = subprocess.run(pipe_cmd, capture_output=True, text=True)
        self.assertEqual(proc_pipe.returncode, 0)
        self.assertIn("✓ [nova-test] Succeeded in", proc_pipe.stdout)
        self.assertIn("HELLO PIPE", proc_pipe.stdout)

    def test_missing_command_shows_usage(self):
        proc = subprocess.run([str(NOVA_TEST)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Usage: nova-test", proc.stderr)

    def test_help_flag_shows_usage(self):
        for flag in ("-h", "--help"):
            proc = subprocess.run([str(NOVA_TEST), flag], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("Usage: nova-test", proc.stdout)

    def test_command_not_found(self):
        proc = subprocess.run(
            [str(NOVA_TEST), "nonexistent-command-12345678"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 127)
        self.assertIn("nova-test: command not found:", proc.stderr)


class NovaTestMultiLanguageExtractSummaryTests(unittest.TestCase):
    """Test extract_summary for all common languages and test frameworks."""

    def test_rust_cargo_test_single_suite(self):
        stdout = (
            "   Compiling my_crate v0.1.0 (/path)\n"
            "    Finished test [unoptimized + debuginfo] target(s) in 0.45s\n"
            "     Running unittests src/lib.rs\n"
            "running 5 tests\n"
            "test test_a ... ok\n"
            "test test_b ... ok\n"
            "\n"
            "test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.02s\n"
        )
        summary = nova_test.extract_summary(stdout, "")
        self.assertEqual(
            summary,
            ["test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.02s"],
        )

    def test_rust_cargo_test_multiple_suites(self):
        stdout = (
            "test result: ok. 4 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s\n"
            "   Doc-tests my_crate\n"
            "test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s\n"
        )
        summary = nova_test.extract_summary(stdout, "")
        self.assertEqual(len(summary), 2)
        self.assertTrue(all("test result: ok." in line for line in summary))

    def test_go_test_single_package(self):
        stdout = (
            "=== RUN   TestAdd\n"
            "--- PASS: TestAdd (0.00s)\n"
            "PASS\n"
            "ok  	github.com/example/pkg	0.042s\n"
        )
        summary = nova_test.extract_summary(stdout, "")
        self.assertEqual(summary, ["PASS", "ok  	github.com/example/pkg	0.042s"])

    def test_go_test_multiple_packages(self):
        stdout = (
            "?   	github.com/example/empty	[no test files]\n"
            "ok  	github.com/example/pkg1	0.012s\n"
            "ok  	github.com/example/pkg2	0.035s\n"
        )
        summary = nova_test.extract_summary(stdout, "")
        self.assertEqual(
            summary,
            ["ok  	github.com/example/pkg1	0.012s", "ok  	github.com/example/pkg2	0.035s"],
        )

    def test_python_unittest(self):
        stderr = (
            "......................................................................\n"
            "----------------------------------------------------------------------\n"
            "Ran 70 tests in 1.234s\n"
            "\n"
            "OK\n"
        )
        summary = nova_test.extract_summary("", stderr)
        self.assertEqual(summary, ["Ran 70 tests in 1.234s", "OK"])

    def test_python_unittest_with_skipped(self):
        stderr = (
            "----------------------------------------------------------------------\n"
            "Ran 12 tests in 0.100s\n"
            "\n"
            "OK (skipped=2)\n"
        )
        summary = nova_test.extract_summary("", stderr)
        self.assertEqual(summary, ["Ran 12 tests in 0.100s", "OK (skipped=2)"])

    def test_python_pytest(self):
        stdout = (
            "============================= test session starts ==============================\n"
            "rootdir: /tmp\n"
            "collected 10 items\n\n"
            "test_sample.py ..........                                                [100%]\n\n"
            "============================== 10 passed in 0.25s ==============================\n"
        )
        summary = nova_test.extract_summary(stdout, "")
        self.assertEqual(summary, ["10 passed in 0.25s"])

    def test_python_pytest_with_skipped_and_warnings(self):
        stdout = "================== 10 passed, 2 skipped, 1 warning in 0.45s ==================\n"
        summary = nova_test.extract_summary(stdout, "")
        self.assertEqual(summary, ["10 passed, 2 skipped, 1 warning in 0.45s"])

    def test_js_jest(self):
        stdout = (
            "PASS src/app.test.ts\n"
            "PASS src/util.test.ts\n\n"
            "Test Suites: 2 passed, 2 total\n"
            "Tests:       15 passed, 15 total\n"
            "Snapshots:   0 total\n"
            "Time:        1.456 s\n"
            "Ran all test suites.\n"
        )
        summary = nova_test.extract_summary(stdout, "")
        self.assertEqual(
            summary,
            [
                "Test Suites: 2 passed, 2 total",
                "Tests:       15 passed, 15 total",
                "Snapshots:   0 total",
                "Time:        1.456 s",
            ],
        )

    def test_js_mocha(self):
        stdout = (
            "  Array\n"
            "    #indexOf()\n"
            "      ✔ should return -1 when not present\n\n"
            "  1 passing (25ms)\n"
        )
        summary = nova_test.extract_summary(stdout, "")
        self.assertEqual(summary, ["1 passing (25ms)"])

    def test_js_vitest(self):
        stdout = (
            " Test Files  3 passed (3)\n"
            "      Tests  12 passed (12)\n"
            "   Start at  10:00:00\n"
            "   Duration  350ms\n"
        )
        summary = nova_test.extract_summary(stdout, "")
        self.assertEqual(
            summary,
            ["Test Files  3 passed (3)", "Tests  12 passed (12)", "Duration  350ms"],
        )

    def test_js_bun_test(self):
        stdout = (
            " 15 pass\n"
            " 0 fail\n"
            "Ran 15 tests across 2 files. [32.00ms]\n"
        )
        summary = nova_test.extract_summary(stdout, "")
        self.assertEqual(
            summary,
            ["15 pass", "Ran 15 tests across 2 files. [32.00ms]"],
        )

    def test_c_cpp_ctest(self):
        stdout = (
            "Test project /build\n"
            "    Start 1: test1\n"
            "1/2 Test #1: test1 ........................   Passed    0.02 sec\n"
            "    Start 2: test2\n"
            "2/2 Test #2: test2 ........................   Passed    0.03 sec\n\n"
            "100% tests passed, 0 tests failed out of 2\n\n"
            "Total Test time (real) =   0.06 sec\n"
        )
        summary = nova_test.extract_summary(stdout, "")
        self.assertEqual(
            summary,
            ["100% tests passed, 0 tests failed out of 2", "Total Test time (real) =   0.06 sec"],
        )

    def test_java_maven(self):
        stdout = (
            "[INFO] Running com.example.AppTest\n"
            "[INFO] Tests run: 8, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 0.12 s\n"
            "[INFO] \n"
            "[INFO] Results:\n"
            "[INFO] \n"
            "[INFO] Tests run: 8, Failures: 0, Errors: 0, Skipped: 0\n"
            "[INFO] \n"
            "[INFO] BUILD SUCCESS\n"
            "[INFO] Total time: 1.500 s\n"
        )
        summary = nova_test.extract_summary(stdout, "")
        self.assertIn("[INFO] Tests run: 8, Failures: 0, Errors: 0, Skipped: 0", summary)
        self.assertIn("[INFO] BUILD SUCCESS", summary)

    def test_java_gradle(self):
        stdout = (
            "> Task :test\n"
            "BUILD SUCCESSFUL in 2s\n"
            "3 actionable tasks: 3 executed\n"
        )
        summary = nova_test.extract_summary(stdout, "")
        self.assertEqual(summary, ["BUILD SUCCESSFUL in 2s"])

    def test_ansi_color_stripping_preserves_matches(self):
        # Pytest output wrapped in green ANSI color codes
        colored_pytest = "\x1b[32m============================== 5 passed in 0.12s ==============================\x1b[0m\n"
        summary = nova_test.extract_summary(colored_pytest, "")
        self.assertEqual(summary, ["5 passed in 0.12s"])

        # Rust output with bold/color ANSI
        colored_cargo = "\x1b[1m\x1b[32mtest result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s\x1b[0m\n"
        summary_cargo = nova_test.extract_summary(colored_cargo, "")
        self.assertEqual(
            summary_cargo,
            ["test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s"],
        )

    def test_generic_fallback_last_lines(self):
        # 5 lines of arbitrary command output
        stdout = "line 1\nline 2\nline 3\nline 4\nline 5\n"
        summary = nova_test.extract_summary(stdout, "")
        self.assertEqual(summary, ["line 3", "line 4", "line 5"])

    def test_generic_fallback_empty_output(self):
        summary = nova_test.extract_summary("", "")
        self.assertEqual(summary, [])


if __name__ == "__main__":
    unittest.main()
