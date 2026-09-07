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
        data = {'marketplaces': [{'name': 'workcell', 'root': '/different/source'}]}
        with patch.object(bootstrap, 'run', return_value=data) as run:
            with self.assertRaises(ValueError):
                bootstrap.marketplace('codex', self.root, False)
            self.assertEqual(bootstrap.marketplace('codex', self.root, True), 'replace')
            self.assertEqual(run.call_count, 2)  # Both calls only inspect the registry.
        with patch.object(bootstrap, 'run', return_value=[]):
            self.assertEqual(bootstrap.marketplace('claude', self.root, False), 'add')
        with patch.object(bootstrap, 'run', return_value=[{'name': 'workcell', 'path': str(self.root)}]):
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
            bootstrap.run([str(binary), 'plugin', 'install', 'workcell@workcell'])


if __name__ == '__main__':
    unittest.main()
