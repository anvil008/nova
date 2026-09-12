import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('read_routing', ROOT / 'tools/read_routing.py')
routing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(routing)


class ReadRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nova reads ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.large = self.root / 'large source.py'
        self.large.write_text(''.join(f'line {i}\n' for i in range(1, 402)))
        self.small = self.root / 'small.py'
        self.small.write_text('small\n')

    def read(self, **args):
        return {'cwd': str(self.root), 'hook_event_name': 'PreToolUse',
                'tool_name': 'Read', 'tool_input': {'file_path': str(self.large), **args}}

    def shell(self, command):
        return {'cwd': str(self.root), 'tool_name': 'Bash', 'tool_input': {'command': command}}

    def test_native_contracts_and_models(self):
        for harness, model in routing.MODELS.items():
            with self.subTest(harness=harness):
                payload = self.read()
                if harness == 'agy':
                    payload = {'workspacePaths': [str(self.root)], 'toolCall': {
                        'name': 'view_file', 'args': {'AbsolutePath': str(self.large)}}}
                result = routing.route(payload, harness, {})
                reason = result['reason'] if harness == 'agy' else result['hookSpecificOutput']['permissionDecisionReason']
                self.assertIn(model, reason)
                self.assertIn('nova-read', reason)
                self.assertIn('already a helper', reason)
                self.assertNotIn('line 401', reason)
                self.assertEqual(result.get('decision', result.get('hookSpecificOutput', {}).get('permissionDecision')), 'deny')
        self.assertFalse((self.root / '.nova').exists())

    def test_small_and_bounded_reads_pass(self):
        for payload in [self.read(file_path=str(self.small)), self.read(limit=50),
                        self.read(offset=101, limit=100),
                        {'toolCall': {'name': 'view_file', 'args': {
                            'AbsolutePath': str(self.large), 'StartLine': 50, 'EndLine': 75}}}]:
            with self.subTest(payload=payload):
                self.assertEqual(routing.route(payload, 'codex', {}), {})
        self.assertTrue(routing.route(self.read(limit=10000), 'claude', {}))

    def test_boundary_and_overrides(self):
        self.large.write_text('x\n' * 350)
        self.assertEqual(routing.route(self.read(), 'claude', {}), {})
        self.large.write_text('x\n' * 350 + 'last')
        self.assertTrue(routing.route(self.read(), 'claude', {}))
        self.assertEqual(routing.route(self.read(), 'claude', {'NOVA_READ_MIN_LINES': '500'}), {})
        self.assertEqual(routing.route(self.read(), 'claude', {'NOVA_READ_ROUTING': 'off'}), {})
        self.large.write_text('x' * 65537)
        self.assertTrue(routing.route(self.read(), 'claude', {}))

    def test_literal_shell_reads_and_native_workdirs(self):
        for command in ["cat 'large source.py'", "cat -n -- 'large source.py'",
                        "echo start; cat 'large source.py'", "pwd && cat 'large source.py'",
                        "pwd\ncat 'large source.py'", "less 'large source.py'",
                        "head -n 400 'large source.py'", "tail --lines=400 'large source.py'"]:
            with self.subTest(command=command):
                self.assertTrue(routing.route(self.shell(command), 'codex', {}))
        payload = {'cwd': '/', 'tool_name': 'exec_command', 'tool_input': {
            'cmd': "cat 'large source.py'", 'workdir': str(self.root)}}
        self.assertTrue(routing.route(payload, 'codex', {}))
        payload = {'workspacePaths': ['/other', '/elsewhere'], 'toolCall': {
            'name': 'run_command', 'args': {'CommandLine': "cat 'large source.py'", 'Cwd': str(self.root)}}}
        self.assertTrue(routing.route(payload, 'agy', {}))

    def test_combined_small_files_route_without_double_counting(self):
        a, b = self.root / 'a', self.root / 'b'
        a.write_text('a\n' * 200)
        b.write_text('b\n' * 200)
        self.assertTrue(routing.route(self.shell('cat a b'), 'codex', {}))
        self.assertEqual(routing.route(self.shell('cat a a'), 'codex', {}), {})

    def test_targeted_or_unsupported_commands_defer(self):
        for command in ["head 'large source.py'", "tail -n 20 'large source.py'",
                        "cat 'large source.py' | grep line", "cat 'large source.py' > out",
                        "sed -n '100,150p' 'large source.py'", "rg line 'large source.py'",
                        "sh -c \"cat 'large source.py'\"", "cat *.py", "cd / && cat file",
                        "python3 /bundle/tools/nova-read --paths 'large source.py'",
                        "cat $(touch never-created)"]:
            with self.subTest(command=command):
                self.assertEqual(routing.route(self.shell(command), 'codex', {}), {})
        self.assertFalse((self.root / 'never-created').exists())

    def test_nonregular_missing_binary_and_ambiguous_paths_pass(self):
        fifo = self.root / 'pipe'
        os.mkfifo(fifo)
        binary = self.root / 'binary'
        binary.write_bytes(b'\0' + b'x' * 70000)
        for path in (fifo, binary, self.root, self.root / 'missing'):
            self.assertEqual(routing.route(self.read(file_path=str(path)), 'claude', {}), {})
        payload = {'workspacePaths': ['/a', '/b'], 'toolCall': {
            'name': 'view_file', 'args': {'AbsolutePath': 'relative'}}}
        self.assertEqual(routing.route(payload, 'agy', {}), {})

    def test_hook_cli_degrades_without_blocking_or_allowing(self):
        for payload, extra in [('not json', {}), ('{}', {'NOVA_READ_MIN_LINES': 'bad'}),
                               ('{"toolCall":null}', {}), ('[]', {})]:
            result = subprocess.run([sys.executable, str(ROOT / 'hooks/read-routing.py'), '--harness', 'codex'],
                                    input=payload, text=True, capture_output=True,
                                    env={**os.environ, **extra}, timeout=3)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout), {})

    def reader(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'tools/nova-read'), *map(str, args)],
                              text=True, capture_output=True, timeout=3, cwd=self.root)

    def test_reader_line_evidence_and_pagination(self):
        result = self.reader('--paths', self.large, '--start', 101, '--limit', 3)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data['source_is_untrusted'])
        file = data['files'][0]
        self.assertEqual(file['start_line'], 101)
        self.assertEqual(file['lines'], ['line 101', 'line 102', 'line 103'])
        self.assertEqual(file['next_line'], 104)
        end = json.loads(self.reader('--paths', self.large, '--start', 400, '--limit', 2).stdout)
        self.assertIsNone(end['files'][0]['next_line'])
        self.assertFalse((self.root / '.nova').exists())

    def test_reader_errors_never_return_partial_source(self):
        fifo = self.root / 'pipe'
        os.mkfifo(fifo)
        for args in [('--paths', self.small, self.root / 'missing'),
                     ('--paths', self.large, '--max-bytes', '4'), ('--paths', fifo),
                     ('--paths', self.large, '--limit', '0')]:
            result = self.reader(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')

    def test_reader_preserves_unicode_and_exact_budget(self):
        self.small.write_text('é\nnext\n')
        result = self.reader('--paths', self.small, '--limit', 1, '--max-bytes', 3,
                             '--reason', 'Inspect exact branch')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['files'][0]['lines'], ['é'])
        self.assertEqual(data['files'][0]['next_line'], 2)
        self.assertEqual(data['reason'], 'Inspect exact branch')

    def test_skipped_prefix_uses_scan_budget_not_output_budget(self):
        self.small.write_text('x' * 101 + '\nsmall\n')
        result = self.reader('--paths', self.small, '--start', 2, '--max-bytes', 6)
        self.assertEqual(result.returncode, 0, result.stderr)
        file = json.loads(result.stdout)['files'][0]
        self.assertEqual(file['lines'], ['small'])
        self.assertEqual(file['start_line'], 2)
        self.assertIsNone(file['next_line'])


if __name__ == '__main__':
    unittest.main()
