import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('write_routing', ROOT / 'tools/write_routing.py')
routing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(routing)


class WriteRoutingTests(unittest.TestCase):
    def edit(self, name='Write', args=None, **extra):
        return {'hook_event_name': 'PreToolUse', 'tool_name': name,
                'tool_input': args or {'file_path': '/project/a file.py', 'content': 'x'}, **extra}

    def reason(self, result):
        return result['reason'] if 'reason' in result else result['hookSpecificOutput']['permissionDecisionReason']

    def test_direct_native_writes_are_denied_for_each_harness(self):
        for harness in routing.HARNESSES:
            with self.subTest(harness=harness):
                result = routing.route(self.edit(), harness, {})
                self.assertEqual(result.get('decision', result.get('hookSpecificOutput', {}).get('permissionDecision')), 'deny')
                self.assertIn('delegate this whole implementation task', self.reason(result))
                self.assertIn('nova-write', self.reason(result))

    def test_claude_identified_implementer_is_allowed_but_ambiguous_is_not(self):
        self.assertEqual(routing.route(self.edit(agent_id='child-1', agent_type='implementer'), 'claude', {}), {})
        for agent_type in ('builder', 'writer'):
            self.assertTrue(routing.route(self.edit(agent_id='child-1', agent_type=agent_type), 'claude', {}))
        self.assertTrue(routing.route(self.edit(agent_type='implementer'), 'claude', {}))
        self.assertTrue(routing.route(self.edit(agent_id='child-1', agent_type='reviewer'), 'claude', {}))
        self.assertTrue(routing.route(self.edit(agent_id='child-1', agent_type='implementer'), 'codex', {}))
        self.assertTrue(routing.route(self.edit(agent_id='child-1', agent_type='implementer'), 'agy', {}))

    def test_namespaced_tools_and_agy_write_replace_are_normalized(self):
        for name in ('mcp__editor__Write', 'native/edit', 'write_file', 'replace_file_content'):
            with self.subTest(name=name):
                self.assertTrue(routing.route(self.edit(name), 'agy', {}))

    def test_runner_exemption_is_exact_and_not_affected_by_children(self):
        runner = ROOT / 'tools/nova-write'
        payload = self.edit('Bash', {'command': f"python3 '{runner}' -- touch 'a file'"}, active_children=['x'])
        for harness in routing.HARNESSES:
            self.assertEqual(routing.route(payload, harness, {}), {})
        literal = self.edit('Bash', {'command': f"python3 {shlex.quote(str(runner))} -- python3 -c 'print(\"; >\")'"})
        self.assertEqual(routing.route(literal, 'codex', {}), {})
        for command in (f"{runner} -- touch a; echo after > out", f"{runner} -- touch a | tee out"):
            self.assertTrue(routing.route(self.edit('Bash', {'command': command}), 'codex', {}))

    def test_obvious_shell_authoring_is_denied_and_routine_commands_pass(self):
        denied = ('echo x > out', 'echo x >> out', 'echo x > source.py 2>/dev/null', 'printf x | tee out', "sed -i 's/a/b/' file", 'perl -pi -e s/a/b/ file', 'dd if=in of=out', 'truncate -s 0 file')
        for command in denied:
            with self.subTest(command=command):
                self.assertTrue(routing.route(self.edit('Bash', {'command': command}), 'codex', {}))
        passed = ('pytest -q', 'npm test', 'git status', 'jj log', 'cat file', "echo '>'", 'echo x > /dev/null', 'python -m unittest > checks.log', 'cat file && pytest > tests.log')
        for command in passed:
            with self.subTest(command=command):
                self.assertEqual(routing.route(self.edit('Bash', {'command': command}), 'codex', {}), {})

    def test_override_and_malformed_payloads_pass(self):
        self.assertEqual(routing.route(self.edit(), 'codex', {'NOVA_WRITE_ROUTING': 'off'}), {})
        for payload in (None, [], {'toolCall': None}, {'tool_name': 'Write', 'tool_input': []}, {'hook_event_name': 'PostToolUse', 'tool_name': 'Write'}):
            self.assertEqual(routing.route(payload, 'codex', {}), {})

    def test_runner_preserves_argv_spaces_output_and_exit_status(self):
        temp = tempfile.TemporaryDirectory(prefix='nova write ')
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        target = root / 'a quoted name.txt'
        command = [sys.executable, str(ROOT / 'tools/nova-write'), '--', sys.executable, '-c',
                   'import pathlib,sys; pathlib.Path(sys.argv[1]).write_text(sys.argv[2]); print(sys.argv[1])',
                   str(target), 'hello world']
        result = subprocess.run(command, text=True, capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_text(), 'hello world')
        self.assertEqual(result.stdout.strip(), str(target))
        missing = subprocess.run([sys.executable, str(ROOT / 'tools/nova-write'), '--', 'definitely-not-a-nova-command'],
                                 text=True, capture_output=True, timeout=3)
        self.assertEqual(missing.returncode, 127)

    def test_hook_cli_fails_open_on_bad_input(self):
        for payload in ('not json', '[]', '{"toolCall":null}'):
            result = subprocess.run([sys.executable, str(ROOT / 'hooks/write-routing.py'), '--harness', 'codex'],
                                    input=payload, text=True, capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout), {})

    def test_hook_cli_allows_explicitly_for_agy(self):
        allowed = json.dumps({'toolCall': {'name': 'run_command', 'args': {'CommandLine': 'ls'}}})
        for payload in (allowed, 'not json', '[]'):
            result = subprocess.run([sys.executable, str(ROOT / 'hooks/write-routing.py'), '--harness', 'agy'],
                                    input=payload, text=True, capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout), {'decision': 'allow'})
        result = subprocess.run([sys.executable, str(ROOT / 'hooks/write-routing.py'), '--harness', 'codex'],
                                input=allowed, text=True, capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {})


if __name__ == '__main__':
    unittest.main()
