import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('bootstrap', ROOT / 'scripts/bootstrap.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bootstrap test ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_dry_run_makes_no_files(self):
        binary = self.root / 'codex'
        binary.write_text('#!/bin/sh\nexit 99\n')
        binary.chmod(0o755)
        prefix = self.root / 'not created'
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/bootstrap.py'),
                                 '--harness', 'codex', '--dry-run', '--prefix', str(prefix)],
                                env=dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ['PATH']),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(prefix.exists())

    def test_marketplace_conflict_requires_explicit_switch(self):
        data = {'marketplaces': [{'name': 'nova', 'root': '/different/source'}]}
        with patch.object(bootstrap, 'run', return_value=data) as run:
            with self.assertRaises(ValueError):
                bootstrap.marketplace('codex', self.root, False)
            self.assertEqual(bootstrap.marketplace('codex', self.root, True), 'replace')
            self.assertEqual(run.call_count, 2)  # Both calls only inspect the registry.
        with patch.object(bootstrap, 'run', return_value=[]):
            self.assertEqual(bootstrap.marketplace('claude', self.root, False), 'add')
        with patch.object(bootstrap, 'run', return_value=[{'name': 'nova', 'path': str(self.root)}]):
            self.assertEqual(bootstrap.marketplace('claude', self.root, False), 'keep')

    def test_helper_updates_preserve_user_edits(self):
        source = self.root / 'source'; source.mkdir()
        (source / 'scout.toml').write_text('new definition')
        target = self.root / 'config/agents/scout.toml'; target.parent.mkdir(parents=True)
        target.write_text('user definition')
        with patch.dict(os.environ, {'CODEX_HOME': str(self.root / 'config')}):
            with self.assertRaises(ValueError):
                bootstrap.helper_updates(source, {})
            owned = {str(target): hashlib.sha256(target.read_bytes()).hexdigest()}
            updates = bootstrap.helper_updates(source, owned)
            self.assertEqual(updates, [(target, b'new definition')])
            target.write_text('edited since bootstrap')
            with self.assertRaises(ValueError):
                bootstrap.helper_updates(source, owned)
        self.assertEqual(target.read_text(), 'edited since bootstrap')

    def test_helper_symlink_is_never_overwritten(self):
        source = self.root / 'source'; source.mkdir()
        (source / 'scout.toml').write_text('definition')
        target = self.root / 'config/agents/scout.toml'; target.parent.mkdir(parents=True)
        target.symlink_to(source / 'scout.toml')
        with patch.dict(os.environ, {'CODEX_HOME': str(self.root / 'config')}):
            with self.assertRaises(ValueError):
                bootstrap.helper_updates(source, {})
        self.assertTrue(target.is_symlink())

    def test_native_failure_is_not_reported_as_success(self):
        binary = self.root / 'claude'; binary.write_text('#!/bin/sh\nexit 9\n'); binary.chmod(0o755)
        with self.assertRaises(subprocess.CalledProcessError):
            bootstrap.run([str(binary), 'plugin', 'install', 'nova@nova'])

    def test_hook_paths_survive_failed_update_with_custom_homes_and_archive(self):
        roots = {'CODEX_HOME': str(self.root / 'custom-codex'),
                 'CLAUDE_CONFIG_DIR': str(self.root / 'custom-claude')}
        hooks = []
        for root in roots.values():
            hook = Path(root) / 'plugins/cache/nova/nova/old/hooks/runner.py'
            hook.parent.mkdir(parents=True)
            hook.write_text('old running-session hook')
            hooks.append(hook)
        archive = self.root / 'prefix/hook-compat'
        with patch.dict(os.environ, roots):
            with self.assertRaises(RuntimeError):
                with bootstrap.preserve_hook_paths(self.root / 'home', archive=archive):
                    for hook in hooks:
                        hook.unlink()
                    raise RuntimeError('native update failed')
        for hook in hooks:
            self.assertEqual(hook.read_text(), 'old running-session hook')
        self.assertTrue((archive / 'codex/old/hooks/runner.py').exists())
        self.assertFalse((self.root / 'home/.local').exists())

    def test_global_instruction_updates_preserve_user_edits(self):
        target = self.root / 'gemini/GEMINI.md'
        target.parent.mkdir(parents=True)
        target.write_text('local custom instructions')
        with patch.dict(os.environ, {'GEMINI_HOME': str(self.root / 'gemini')}):
            with self.assertRaises(ValueError):
                bootstrap.global_instruction_updates(['agy'], {})
            # When force=True, unmanaged edits are overwritten
            updates = bootstrap.global_instruction_updates(['agy'], {}, force=True)
            self.assertEqual(len(updates), 1)
            self.assertEqual(updates[0][0], target)
            # When receipt matches old hash, update is permitted
            owned = {str(target): hashlib.sha256(b'local custom instructions').hexdigest()}
            updates = bootstrap.global_instruction_updates(['agy'], owned)
            self.assertEqual(len(updates), 1)
            self.assertEqual(updates[0][0], target)

    def test_global_instruction_symlink_refused(self):
        target = self.root / 'claude/CLAUDE.md'
        target.parent.mkdir(parents=True)
        dummy = self.root / 'dummy.md'
        dummy.write_text('dummy')
        target.symlink_to(dummy)
        with patch.dict(os.environ, {'CLAUDE_HOME': str(self.root / 'claude')}):
            with self.assertRaises(ValueError):
                bootstrap.global_instruction_updates(['claude'], {})

    def test_bootstrap_tool_copies_include_nova_test(self):
        tool_sources = [
            ROOT / 'tools/nova-flow',
            ROOT / 'tools/nova-flow.html',
            ROOT / 'tools/nova-flow-demo.json',
            ROOT / 'tools/nova-test',
        ]
        updates = bootstrap.owned_updates(tool_sources, self.root / 'bin', {})
        installed_names = [target.name for target, _ in updates]
        self.assertIn('nova-test', installed_names)
        self.assertIn('nova-flow', installed_names)


if __name__ == '__main__':
    unittest.main()

