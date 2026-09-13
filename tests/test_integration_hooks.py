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

class AgyIntegrationHooks(unittest.TestCase):
    def test_delegation_reminder_waits_for_idle_and_is_consumed_once(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            def event(name, session='parent', **kw):
                return hook.handle_agy(dict(conversationId=session, **kw), cache, name)
            self.assertEqual(event('Stop', fullyIdle=True, terminationReason='model_stop'), {})
            self.assertEqual(event('PostToolUse', toolCall={'name': 'invoke_subagent', 'args': {}}), {})
            self.assertEqual(event('Stop', fullyIdle=True, terminationReason='model_stop', session='other'), {})
            for kw in ({'fullyIdle': False}, {'fullyIdle': True, 'terminationReason': 'error'},
                       {'fullyIdle': True, 'terminationReason': 'model_stop', 'error': 'failed'}):
                self.assertEqual(event('Stop', **kw), {})
            result = event('Stop', fullyIdle=True, terminationReason='model_stop')
            self.assertEqual(result['decision'], 'continue')
            self.assertIn('local main', result['reason'])
            self.assertEqual(event('Stop', fullyIdle=True, terminationReason='model_stop'), {})

    def test_failed_or_unrelated_tools_do_not_arm_reminder(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            for payload in ({'toolCall': {'name': 'run_command'}},
                            {'toolCall': {'name': 'invoke_subagent'}, 'error': 'failed'},
                            {'toolCall': None}):
                hook.handle_agy(dict(conversationId='parent', **payload), cache, 'PostToolUse')
            self.assertEqual(hook.handle_agy({'conversationId': 'parent', 'fullyIdle': True,
                             'terminationReason': 'model_stop'}, cache, 'Stop'), {})
            self.assertEqual(hook.handle_agy({}, cache, 'Stop'), {})

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
