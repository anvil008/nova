import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

RUNNER = Path(__file__).resolve().parents[1] / 'hooks/post-edit.py'
spec = importlib.util.spec_from_file_location('post_edit', RUNNER)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class PostEditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.file = self.root / 'space $(literal).py'
        self.file.write_text('original')
        self.payload = {'tool_name': 'Write', 'cwd': str(self.root),
                        'tool_input': {'file_path': str(self.file)}}
        self.config = {'enabled': True, 'root': str(self.root), 'commands': []}

    def test_configured_format_then_lint_with_literal_path(self):
        self.config['commands'] = [
            {'match': ['*.py'], 'argv': [sys.executable, '-c',
             'import pathlib,sys;pathlib.Path(sys.argv[1]).write_text("formatted")', '{file}']},
            {'match': ['*.py'], 'argv': [sys.executable, '-c',
             'import pathlib,sys;print(pathlib.Path(sys.argv[1]).read_text());sys.exit(1)', '{file}']}]
        result = hook.run(self.payload, self.config)
        self.assertEqual(self.file.read_text(), 'formatted')
        self.assertIn('exited 1\nformatted', result)

    def test_disabled_excluded_and_outside_symlink(self):
        self.config['commands'] = [{'match': ['*'], 'argv': ['MISSING_TOOL', '{file}']}]
        self.config['enabled'] = False
        self.assertEqual(hook.run(self.payload, self.config), '')
        self.config.update(enabled=True, exclude=['*.py'])
        self.assertEqual(hook.run(self.payload, self.config), '')
        self.file.unlink()
        self.file.symlink_to(RUNNER.resolve())
        self.assertEqual(hook.edited_paths(self.payload, self.root), [])

    def test_codex_patch_and_agy_paths(self):
        patch = {'tool_name': 'apply_patch', 'cwd': str(self.root), 'tool_input': {
            'command': f'*** Begin Patch\n*** Update File: {self.file.name}\n*** Add File: absent.py\n*** End Patch'}}
        self.assertEqual(hook.edited_paths(patch, self.root), [self.file])
        agy = {'toolCall': {'name': 'write_to_file', 'args': {'TargetFile': self.file.name}},
               'workspacePaths': [str(self.root)]}
        self.assertEqual(hook.edited_paths(agy, self.root), [self.file])
        agy['workspacePaths'].append('/other')
        self.assertEqual(hook.edited_paths(agy, self.root), [])

    def test_timeout_and_missing_tool_are_diagnostics(self):
        self.config['commands'] = [
            {'match': ['*'], 'argv': [sys.executable, '-c', 'import time;time.sleep(5)', '{file}'], 'timeout': 1},
            {'match': ['*'], 'argv': ['MISSING_TOOL', '{file}']}]
        result = hook.run(self.payload, self.config)
        self.assertIn('timed out', result)
        self.assertIn('MISSING_TOOL', result)

    def test_native_outputs_never_force_continuation(self):
        self.config['commands'] = [{'match': ['*'], 'argv': ['MISSING_TOOL', '{file}']}]
        config_path = self.root / 'config.json'
        config_path.write_text(json.dumps(self.config))
        for harness in ['codex', 'claude', 'agy']:
            result = subprocess.run([sys.executable, str(RUNNER), '--harness', harness,
                                     '--config', str(config_path)],
                                    input=json.dumps(self.payload), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            output = json.loads(result.stdout)
            self.assertNotIn('decision', output)
            if harness == 'agy':
                self.assertEqual(output, {})
                self.assertIn('MISSING_TOOL', result.stderr)
            else:
                self.assertIn('MISSING_TOOL', output['hookSpecificOutput']['additionalContext'])


if __name__ == '__main__':
    unittest.main()
