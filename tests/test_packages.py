import importlib.util
import json
import os
from pathlib import Path
import re
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
        self.temp = tempfile.TemporaryDirectory(prefix='workcell package ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.output = package.build(self.base / 'built')

    def test_shared_content_and_relocation(self):
        moved = self.base / 'relocated'
        shutil.move(self.output, moved)
        for harness in package.HARNESSES:
            plugin = moved / harness / 'plugins/workcell'
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
            plugin = moved / harness / 'plugins/workcell'
            command = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks']['PostToolUse'][0]['hooks'][0]['command']
            env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin), WORKCELL_HOOK_CONFIG=str(config))
            target.write_text('before')
            result = subprocess.run(['sh', '-c', command], input=payload, text=True,
                                    capture_output=True, env=env, cwd=repo, check=True)
            self.assertEqual(target.read_text(), 'after', result.stderr)
            del env['WORKCELL_HOOK_CONFIG']
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


if __name__ == '__main__':
    unittest.main()
