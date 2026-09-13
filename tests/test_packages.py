import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('package', ROOT / 'scripts/package.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nova package ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.output = package.build(self.base / 'built')

    def test_shared_content_and_relocation(self):
        moved = self.base / 'relocated'
        shutil.move(self.output, moved)
        for harness in package.HARNESSES:
            plugin = moved / harness / 'plugins/nova'
            self.assertFalse(any(p.is_symlink() for p in plugin.rglob('*')))
            skills = list((plugin / 'skills').glob('*/SKILL.md'))
            self.assertEqual(len(skills), 14)
            for skill in skills:
                self.assertEqual(skill.read_bytes(), (ROOT / skill.relative_to(plugin)).read_bytes())
                for link in re.findall(r'\]\(([^)]+)\)', skill.read_text()):
                    if '://' not in link and not link.startswith('#'):
                        self.assertTrue((skill.parent / link.split('#')[0]).exists(), (skill, link))
            self.assertEqual(len(list((plugin / 'skills').glob('*/assets/report.html'))), 11)
            helpers = plugin / ('setup/agents' if harness == 'codex' else 'agents')
            for role in ('scout', 'implementer', 'reviewer'):
                if harness == 'codex':
                    data = tomllib.loads((helpers / f'{role}.toml').read_text())
                    self.assertTrue(data['developer_instructions'].strip())
                else:
                    path = helpers / (f'{role}/agent.md' if harness == 'agy' else f'{role}.md')
                    _, front, body = path.read_text().split('---', 2)
                    self.assertTrue(yaml.safe_load(front)['name'])
                    self.assertTrue(body.strip())

    def test_agy_integration_commands_after_relocation_and_from_project(self):
        installed_home = self.base / 'home'
        plugin = installed_home / '.gemini/config/plugins/nova'
        plugin.parent.mkdir(parents=True)
        shutil.move(self.output / 'agy/plugins/nova', plugin)
        events = json.loads((plugin / 'hooks.json').read_text())['nova-integration']
        arm = events['PostToolUse'][0]['hooks'][0]['command']
        stop = events['Stop'][0]['command']
        env = dict(os.environ, HOME=str(installed_home), XDG_CACHE_HOME=str(self.base / 'cache'))
        for cwd in (plugin, self.base):
            def run(command, payload):
                result = subprocess.run(['sh', '-c', command], input=json.dumps(payload),
                                        text=True, capture_output=True, cwd=cwd, env=env, check=True)
                return json.loads(result.stdout)
            self.assertEqual(run(arm, {'conversationId': 'parent',
                                     'toolCall': {'name': 'invoke_subagent'}}), {})
            payload = {'conversationId': 'parent', 'fullyIdle': True, 'terminationReason': 'model_stop'}
            self.assertEqual(run(stop, payload)['decision'], 'continue')
            self.assertEqual(run(stop, payload), {})
            self.assertFalse((cwd / '.nova').exists())

    def test_rebuild_removes_stale_files_and_preserves_foreign_directory(self):
        (self.output / 'obsolete').write_text('stale')
        package.build(self.output)
        self.assertFalse((self.output / 'obsolete').exists())
        foreign = self.base / 'foreign'
        foreign.mkdir()
        (foreign / 'keep').write_text('mine')
        with self.assertRaises(ValueError):
            package.build(foreign)
        self.assertEqual((foreign / 'keep').read_text(), 'mine')

    def test_native_hook_command_works_after_relocation(self):
        moved = self.base / 'different directory'
        shutil.move(self.output, moved)
        repo = self.base / 'target'; repo.mkdir()
        target = repo / 'sample.py'; target.write_text('before')
        config = self.base / 'checks.json'
        config.write_text(json.dumps({'enabled': True, 'root': str(repo), 'commands': [
            {'match': ['*.py'], 'argv': [sys.executable, '-c',
                'import pathlib,sys;pathlib.Path(sys.argv[1]).write_text("after")', '{file}']}]}))
        payload = json.dumps({'tool_name': 'Write', 'cwd': str(repo),
                              'tool_input': {'file_path': str(target)}})
        for harness in ('codex', 'claude'):
            plugin = moved / harness / 'plugins/nova'
            command = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks']['PostToolUse'][0]['hooks'][0]['command']
            env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin), NOVA_HOOK_CONFIG=str(config))
            target.write_text('before')
            result = subprocess.run(['sh', '-c', command], input=payload, text=True,
                                    capture_output=True, env=env, cwd=repo, check=True)
            self.assertEqual(target.read_text(), 'after', result.stderr)
            del env['NOVA_HOOK_CONFIG']
            target.write_text('before')
            subprocess.run(['sh', '-c', command], input=payload, text=True,
                           capture_output=True, env=env, cwd=repo, check=True)
            self.assertEqual(target.read_text(), 'before')

    def test_marketplaces_resolve_self_contained_plugin(self):
        for harness in package.HARNESSES:
            market = self.output / harness
            index_path = '.agents/plugins/marketplace.json' if harness == 'codex' else '.claude-plugin/marketplace.json'
            entry = json.loads((market / index_path).read_text())['plugins'][0]
            source = entry['source']['path'] if harness == 'codex' else entry['source']
            self.assertTrue((market / source / 'skills/refactor/SKILL.md').is_file())

    def test_packaged_hooks_do_not_start_flow_tracking(self):
        repo = self.base / 'untracked-project'
        repo.mkdir()
        for harness in package.HARNESSES:
            plugin = self.output / harness / 'plugins/nova'
            path = plugin / ('hooks.json' if harness == 'agy' else 'hooks/hooks.json')
            hooks = json.loads(path.read_text())
            if harness == 'agy':
                self.assertEqual(set(hooks), {'nova-read-routing', 'nova-write-routing', 'nova-integration'})
                self.assertEqual(set(hooks['nova-integration']) - {'enabled', 'description'}, {'PostToolUse', 'Stop'})
                self.assertNotIn('tracking.py', json.dumps(hooks))
                self.assertEqual(set(hooks['nova-read-routing']) - {'enabled', 'description'}, {'PreToolUse'})
                self.assertEqual(set(hooks['nova-write-routing']) - {'enabled', 'description'}, {'PreToolUse'})
                continue
            expected = {'PreToolUse', 'PostToolUse', 'SubagentStop', 'Stop', 'SessionEnd'}
            if harness == 'claude':
                expected |= {'WorktreeCreate', 'WorktreeRemove'}
            self.assertEqual(set(hooks['hooks']), expected)
            env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin))
            env.pop('NOVA_HOOK_CONFIG', None)
            for group in hooks['hooks']['PostToolUse']:
                for hook in group['hooks']:
                    payload = {'hook_event_name': 'PostToolUse', 'session_id': 'no-flow',
                               'cwd': str(repo), 'tool_name': 'Write',
                               'tool_input': {'file_path': str(repo / 'sample.py')}}
                    result = subprocess.run(['sh', '-c', hook['command']],
                                            input=json.dumps(payload), text=True,
                                            capture_output=True, env=env, cwd=repo, check=True)
                    self.assertEqual(result.stdout.strip(), '')
                    self.assertFalse((repo / '.nova').exists())

    def test_routing_handoff_and_reader_work_after_relocation(self):
        moved = self.base / 'relocated bundle'
        shutil.move(self.output, moved)
        repo = self.base / 'target'
        repo.mkdir()
        source = repo / 'large.py'
        source.write_text(''.join(f'value_{i} = {i}\n' for i in range(400)))
        for harness in package.HARNESSES:
            plugin = moved / harness / 'plugins/nova'
            if harness == 'agy':
                config = json.loads((plugin / 'hooks.json').read_text())['nova-read-routing']
                payload = {'workspacePaths': [str(repo)], 'toolCall': {
                    'name': 'view_file', 'args': {'AbsolutePath': str(source)}}}
                cwd = plugin  # Agy runs commands relative to the root hooks.json.
            else:
                config = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks']
                payload = {'cwd': str(repo), 'tool_name': 'Read',
                           'tool_input': {'file_path': str(source)}}
                cwd = repo
            command = config['PreToolUse'][0]['hooks'][0]['command']
            env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin))
            for name in ('NOVA_READ_ROUTING', 'NOVA_READ_MIN_LINES', 'NOVA_READ_MAX_BYTES'):
                env.pop(name, None)
            result = subprocess.run(['sh', '-c', command], input=json.dumps(payload),
                                    text=True, capture_output=True, env=env, cwd=cwd, check=True)
            decision = json.loads(result.stdout)
            if harness == 'agy':
                self.assertEqual(decision['decision'], 'deny')
                reason = decision['reason']
            else:
                self.assertEqual(decision['hookSpecificOutput']['permissionDecision'], 'deny')
                reason = decision['hookSpecificOutput']['permissionDecisionReason']
            self.assertIn(str(plugin / 'tools/nova-read'), reason)
            self.assertNotIn('value_399', reason)
            reader = subprocess.run([sys.executable, str(plugin / 'tools/nova-read'),
                                     '--paths', str(source)], text=True, capture_output=True, check=True)
            data = json.loads(reader.stdout)['files'][0]
            self.assertEqual(data['lines'][399], 'value_399 = 399')
            self.assertIsNone(data['next_line'])
            self.assertFalse((repo / '.nova').exists())

    def test_write_routing_and_runner_work_after_relocation(self):
        moved = self.base / 'relocated write bundle'
        shutil.move(self.output, moved)
        repo = self.base / 'target write'
        repo.mkdir()
        for harness in package.HARNESSES:
            plugin = moved / harness / 'plugins/nova'
            payload = {'cwd': str(repo), 'tool_name': 'Write',
                       'tool_input': {'file_path': str(repo / 'main.py'), 'content': 'x'}}
            if harness == 'agy':
                installed = self.base / 'home/.gemini/config/plugins/nova'
                installed.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(plugin, installed)
                plugin = installed
                config = json.loads((plugin / 'hooks.json').read_text())['nova-write-routing']
                payload = {'workspacePaths': [str(repo)], 'toolCall': {
                    'name': 'write_file', 'args': {'path': str(repo / 'main.py'), 'content': 'x'}}}
                cwd = self.base  # Prove the Agy installed-plugin fallback works from a project cwd.
            else:
                config = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks']
                cwd = repo
            entry = config['PreToolUse'][1] if harness != 'agy' else config['PreToolUse'][0]
            command = entry['hooks'][0]['command']
            env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin), HOME=str(self.base / 'home'))
            result = subprocess.run(['sh', '-c', command], input=json.dumps(payload), text=True,
                                    capture_output=True, env=env, cwd=cwd, check=True)
            decision = json.loads(result.stdout)
            if harness == 'agy':
                self.assertEqual(decision['decision'], 'deny')
            else:
                self.assertEqual(decision['hookSpecificOutput']['permissionDecision'], 'deny')
            target = repo / f'{harness} quoted.txt'
            runner = plugin / 'tools/nova-write'
            write = subprocess.run([sys.executable, str(runner), '--', sys.executable, '-c',
                                    'import pathlib,sys; pathlib.Path(sys.argv[1]).write_text(sys.argv[2])',
                                    str(target), 'written via argv'], text=True, capture_output=True, timeout=3)
            self.assertEqual(write.returncode, 0, write.stderr)
            self.assertEqual(target.read_text(), 'written via argv')
            exempt = dict(payload)
            if harness == 'agy':
                exempt['toolCall'] = {'name': 'run_command', 'args': {'CommandLine': f'python3 {shlex.quote(str(runner))} -- touch x'}}
            else:
                exempt.update({'tool_name': 'Bash', 'tool_input': {'command': f'python3 {shlex.quote(str(runner))} -- touch x'}})
            result = subprocess.run(['sh', '-c', command], input=json.dumps(exempt), text=True,
                                    capture_output=True, env=env, cwd=cwd, check=True)
            if harness == 'agy':
                self.assertEqual(json.loads(result.stdout), {'decision': 'allow'})
            else:
                self.assertEqual(json.loads(result.stdout), {})


if __name__ == '__main__':
    unittest.main()
