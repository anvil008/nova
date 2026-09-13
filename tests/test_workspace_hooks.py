import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / 'hooks/workspace.py'


class WorkspaceHooks(unittest.TestCase):
    def setUp(self):
        cache = Path.home() / '.cache/agent-work/nova/workspace-hooks'
        cache.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=cache)
        self.addCleanup(self.temp.cleanup)
        config = Path(self.temp.name) / 'jj.toml'
        config.write_text('[user]\nname = "Test"\nemail = "test@example.com"\n[revset-aliases]\n"trunk()" = "main"\n')
        env = patch.dict('os.environ', {'JJ_CONFIG': str(config)})
        env.start()
        self.addCleanup(env.stop)
        self.root = Path(self.temp.name) / 'repo with spaces'
        self.root.mkdir()
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.com')
        self.git('config', 'commit.gpgsign', 'false')
        (self.root / 'file.txt').write_text('base\n')
        self.git('add', '.')
        self.git('commit', '-m', 'base')

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, text=True, stderr=subprocess.DEVNULL).strip()

    def hook(self, event, cwd=None, **fields):
        payload = dict(hook_event_name=event, cwd=str(cwd or self.root), **fields)
        return subprocess.run(['python3', str(HOOK)], input=json.dumps(payload), text=True, capture_output=True)

    def create(self, name, cwd=None):
        result = self.hook('WorktreeCreate', cwd, name=name)
        self.assertEqual(result.returncode, 0, result.stderr)
        path = Path(result.stdout.strip())
        self.assertEqual(path, self.root / '.workspaces' / name)
        self.assertEqual((path / 'file.txt').read_text(), 'base\n')
        return path

    def test_git_creation_from_primary_and_secondary_and_clean_removal(self):
        first = self.create('first')
        second = self.create('second', first)
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertIn(str(second), self.git('worktree', 'list', '--porcelain'))
        result = self.hook('WorktreeRemove', worktree_path=str(second))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(second.exists())
        self.assertTrue(first.exists())

    def test_clean_unintegrated_commit_is_retained_until_main_contains_it(self):
        path = self.create('unmerged')
        (path / 'file.txt').write_text('finished task\n')
        self.git('-C', str(path), 'add', '.')
        self.git('-C', str(path), 'commit', '-m', 'task')
        self.assertNotEqual(self.hook('WorktreeRemove', worktree_path=str(path)).returncode, 0)
        self.assertTrue(path.exists())
        self.git('merge', '--ff-only', 'worktree-unmerged')
        self.assertEqual(self.hook('WorktreeRemove', worktree_path=str(path)).returncode, 0)
        self.assertFalse(path.exists())

    def test_dirty_and_ignored_worktree_retained(self):
        path = self.create('dirty')
        (path / 'file.txt').write_text('user changes\n')
        result = self.hook('WorktreeRemove', worktree_path=str(path))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((path / 'file.txt').read_text(), 'user changes\n')
        self.git('-C', str(path), 'restore', 'file.txt')
        (self.root / '.git/info/exclude').write_text('/.workspaces/\nsecret\n')
        (path / 'secret').write_text('keep\n')
        result = self.hook('WorktreeRemove', worktree_path=str(path))
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((path / 'secret').exists())

    def test_bad_names_collisions_symlinks_and_foreign_cleanup(self):
        for name in ('../escape', '/absolute', 'a/b', 'x;touch nope'):
            self.assertNotEqual(self.hook('WorktreeCreate', name=name).returncode, 0)
        path = self.create('existing')
        self.assertNotEqual(self.hook('WorktreeCreate', name='existing').returncode, 0)
        self.assertTrue(path.exists())
        self.assertNotEqual(self.hook('WorktreeRemove', worktree_path=str(self.root)).returncode, 0)
        self.assertTrue((self.root / 'file.txt').exists())

    def test_primary_task_head_is_not_used_as_base(self):
        self.git('switch', '-c', 'unrelated-task')
        (self.root / 'file.txt').write_text('unrelated task\n')
        self.git('commit', '-am', 'unrelated task')
        self.create('independent')

    def test_unknown_trunk_fails_without_creating_worktree(self):
        self.git('branch', '-m', 'custom-trunk')
        result = self.hook('WorktreeCreate', name='unknown')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Cannot identify trunk', result.stderr)
        self.assertFalse((self.root / '.workspaces/unknown').exists())

    def test_symlink_container_refused(self):
        elsewhere = Path(self.temp.name) / 'elsewhere'
        elsewhere.mkdir()
        (self.root / '.workspaces').symlink_to(elsewhere, target_is_directory=True)
        result = self.hook('WorktreeCreate', name='escape')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(elsewhere.iterdir()), [])

    def local_main_ahead_of_remote(self):
        old = self.git('rev-parse', 'HEAD')
        self.git('update-ref', 'refs/remotes/origin/main', old)
        self.git('symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/main')
        (self.root / 'file.txt').write_text('integrated locally\n')
        self.git('add', '.')
        self.git('commit', '-m', 'local integration')
        return old

    def test_git_workspace_inherits_local_integration_before_publication(self):
        self.local_main_ahead_of_remote()
        result = self.hook('WorktreeCreate', name='local-main')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((Path(result.stdout.strip()) / 'file.txt').read_text(), 'integrated locally\n')

    @unittest.skipUnless(shutil.which('jj'), 'jj required')
    def test_jj_workspace_prefers_local_main_over_stale_trunk_alias(self):
        old = self.local_main_ahead_of_remote()
        subprocess.run(['jj', 'git', 'init', '--colocate'], cwd=self.root, check=True, capture_output=True)
        subprocess.run(['jj', 'config', 'set', '--repo', 'revset-aliases."trunk()"', old],
                       cwd=self.root, check=True, capture_output=True)
        result = self.hook('WorktreeCreate', name='local-main')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((Path(result.stdout.strip()) / 'file.txt').read_text(), 'integrated locally\n')

    def test_packaged_native_command(self):
        output = Path(self.temp.name) / 'bundle'
        subprocess.run(['python3', str(ROOT / 'scripts/package.py'), '--output', str(output)], check=True, capture_output=True)
        plugin = output / 'claude/plugins/nova'
        hooks = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks']
        for event in ('WorktreeCreate', 'WorktreeRemove'):
            command = hooks[event][0]['hooks'][0]['command']
            payload = dict(hook_event_name=event, cwd=str(self.root), name='native',
                           worktree_path=str(self.root / '.workspaces/native'))
            result = subprocess.run(['sh', '-c', command], input=json.dumps(payload), text=True,
                                    capture_output=True, cwd=self.root,
                                    env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin)))
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / '.workspaces/native').exists())

    @unittest.skipUnless(shutil.which('jj'), 'jj required')
    def test_jj_creation_from_secondary_and_retention(self):
        subprocess.run(['jj', 'git', 'init', '--colocate'], cwd=self.root, check=True, capture_output=True)
        first = self.create('jj-first')
        second = self.create('jj-second', first)
        self.assertTrue((second / '.jj/repo').is_file())
        result = self.hook('WorktreeRemove', worktree_path=str(second))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('JJ workspace retained', result.stderr)
        self.assertTrue((second / 'file.txt').exists())
