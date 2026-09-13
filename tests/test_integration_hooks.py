import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('integration', Path(__file__).resolve().parents[1] / 'hooks/integration.py')
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class IntegrationHooks(unittest.TestCase):
    def test_parent_reminder_is_once_and_session_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            def event(name, session='parent', **kw):
                return hook.handle(dict(hook_event_name=name, session_id=session, **kw), cache)
            self.assertEqual(event('Stop'), {})
            self.assertEqual(event('SubagentStop'), {})
            self.assertEqual(event('Stop', 'another'), {})
            self.assertEqual(event('Stop')['decision'], 'block')
            self.assertEqual(event('Stop'), {})
            event('SubagentStop')
            self.assertEqual(event('Stop', stop_hook_active=True), {})
            self.assertEqual(event('Stop'), {})
            event('SubagentStop')
            event('SessionEnd')
            self.assertEqual(event('Stop'), {})

    def test_missing_session_is_noop(self):
        self.assertEqual(hook.handle({'hook_event_name': 'Stop'}, Path('/unused')), {})

class CompatibilityHooks(unittest.TestCase):
    def test_evicted_paths_restored_even_when_update_fails(self):
        import sys
        import shutil
        scripts = Path(__file__).resolve().parents[1] / 'scripts'
        sys.path.insert(0, str(scripts))
        import bootstrap
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            version = home / '.codex/plugins/cache/nova/nova/old'
            (version / 'hooks').mkdir(parents=True)
            (version / 'tools').mkdir()
            (version / 'hooks/read-routing.py').write_text('adapter')
            (version / 'tools/read_routing.py').write_text('dependency')
            with self.assertRaises(RuntimeError):
                with bootstrap.preserve_hook_paths(home):
                    shutil.rmtree(version)
                    raise RuntimeError('native update failed')
            self.assertEqual((version / 'hooks/read-routing.py').read_text(), 'adapter')
            self.assertEqual((version / 'tools/read_routing.py').read_text(), 'dependency')
