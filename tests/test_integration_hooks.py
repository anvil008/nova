import hashlib
import importlib.util
import json
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

    def test_read_only_children_do_not_arm_reminder(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            def stop():
                return hook.handle(dict(hook_event_name='Stop', session_id='parent'), cache)
            def child(*agent_type):
                payload = dict(hook_event_name='SubagentStop', session_id='parent')
                if agent_type:
                    payload['agent_type'] = agent_type[0]
                return hook.handle(payload, cache)
            for agent_type in ('nova:scout', 'reviewer', 'Explore', 'Plan', 'claude-code-guide'):
                self.assertEqual(child(agent_type), {})
                self.assertEqual(stop(), {}, agent_type)
            for agent_type in (('nova:implementer',), ('general-purpose',), ('',), (None,), ()):
                child(*agent_type)
                self.assertEqual(stop().get('decision'), 'block', agent_type)
            child('nova:implementer')
            child('nova:reviewer')
            self.assertEqual(stop().get('decision'), 'block')

    def test_missing_session_is_noop(self):
        self.assertEqual(hook.handle({'hook_event_name': 'Stop'}, Path('/unused')), {})


class DeliveryGatedReminder(unittest.TestCase):
    """Claude supplies agent_id and transcripts, so the reminder waits for the child's result."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache = Path(directory.name) / 'cache'
        self.transcript = Path(directory.name) / 'parent.jsonl'
        self.transcript.write_text('{"type": "user", "timestamp": "2026-09-14T17:00:00.000Z"}\n')

    def append(self, entry):
        with self.transcript.open('a', encoding='utf-8') as lines:
            lines.write(json.dumps(entry) + '\n')

    def notification(self, agent_id, stamp, status='completed'):
        self.append({'type': 'user', 'timestamp': stamp, 'message': {'role': 'user', 'content':
                    f'<task-notification>\n<task-id>{agent_id}</task-id>\n<status>{status}</status>\n'
                    '</task-notification>'}})

    def child(self, agent_id, agent_type='nova:implementer', harness='claude'):
        return hook.handle({'hook_event_name': 'SubagentStop', 'session_id': 'parent',
                            'agent_type': agent_type, 'agent_id': agent_id,
                            'agent_transcript_path': f'/tmp/agent-{agent_id}.jsonl',
                            'transcript_path': str(self.transcript)}, self.cache, harness)

    def stop(self, transcript=None, harness='claude', **kw):
        payload = {'hook_event_name': 'Stop', 'session_id': 'parent',
                   'transcript_path': str(self.transcript) if transcript is None else transcript}
        return hook.handle(dict(payload, **kw), self.cache, harness)

    def pending(self):
        marker = self.cache / hashlib.sha256(b'parent').hexdigest()
        return json.loads(marker.read_text())['pending'] if marker.exists() else {}

    def test_reminder_waits_for_the_childs_result_and_fires_once_per_delivery(self):
        self.assertEqual(self.child('agentone'), {})
        self.assertEqual(self.stop(), {})  # Intermediate stop while the child still runs.
        self.assertEqual(list(self.pending()), ['agentone'])
        self.notification('agentone', '2026-09-14T17:10:00.000Z')
        self.assertEqual(self.stop()['decision'], 'block')
        self.assertEqual(self.pending(), {})
        self.assertEqual(self.stop(), {})
        self.child('agentone')  # Re-armed by a later stop with no new result delivered.
        self.assertEqual(self.stop(), {})
        self.notification('agentone', '2026-09-14T17:20:00.000Z')  # Resumed and finished again.
        self.assertEqual(self.stop()['decision'], 'block')
        self.assertEqual(self.stop(), {})

    def test_foreground_agent_result_delivers_but_a_launch_acknowledgement_does_not(self):
        self.child('agenttwo')
        self.append({'type': 'user', 'timestamp': '2026-09-14T17:05:00.000Z',
                     'toolUseResult': {'agentId': 'agenttwo', 'status': 'async_launched'}})
        self.assertEqual(self.stop(), {})
        self.append({'type': 'user', 'timestamp': '2026-09-14T17:06:00.000Z',
                     'toolUseResult': {'agentId': 'agenttwo', 'status': 'completed'}})
        self.assertEqual(self.stop()['decision'], 'block')

    def test_undelivered_children_stay_pending_while_a_delivered_one_reminds(self):
        self.child('agentaaa')
        self.child('agentbbb')
        self.notification('agentaaa', '2026-09-14T17:10:00.000Z')
        self.assertEqual(self.stop()['decision'], 'block')
        self.assertEqual(list(self.pending()), ['agentbbb'])
        self.assertEqual(self.stop(), {})
        self.notification('agentbbb', '2026-09-14T17:12:00.000Z', status='failed')
        self.assertEqual(self.stop()['decision'], 'block')
        self.assertEqual(self.pending(), {})

    def test_active_stop_hook_records_consumption_without_blocking(self):
        self.child('agentthree')
        self.notification('agentthree', '2026-09-14T17:10:00.000Z')
        self.assertEqual(self.stop(stop_hook_active=True), {})
        self.assertEqual(self.pending(), {})
        self.assertEqual(self.stop(), {})

    def test_unreadable_or_missing_transcript_falls_back_to_arm_on_stop(self):
        self.child('agentfour')
        self.assertEqual(self.stop(transcript=str(self.transcript) + '.missing')['decision'], 'block')
        self.assertEqual(self.stop(), {})
        self.child('agentfive')
        self.assertEqual(self.stop(transcript='')['decision'], 'block')

    def test_read_only_children_never_become_pending(self):
        self.assertEqual(self.child('agentsix', 'nova:scout'), {})
        self.assertEqual(self.stop(), {})
        self.child('agentseven')
        self.child('agentsix', 'reviewer')
        self.assertEqual(list(self.pending()), ['agentseven'])
        self.notification('agentsix', '2026-09-14T17:10:00.000Z')
        self.assertEqual(self.stop(), {})
        self.notification('agentseven', '2026-09-14T17:11:00.000Z')
        self.assertEqual(self.stop()['decision'], 'block')

    def test_malformed_transcript_lines_are_ignored(self):
        self.child('agenteight')
        with self.transcript.open('a', encoding='utf-8') as lines:
            lines.write('{"type": "user", "agenteight" truncated\n')
        self.assertEqual(self.stop(), {})
        self.notification('agenteight', '2026-09-14T17:10:00.000Z')
        self.assertEqual(self.stop()['decision'], 'block')

    def test_a_legacy_child_keeps_arming_the_reminder_alongside_identified_children(self):
        self.child('agentnine')
        hook.handle({'hook_event_name': 'SubagentStop', 'session_id': 'parent'}, self.cache, 'claude')
        self.assertEqual(self.stop()['decision'], 'block')
        self.assertEqual(self.stop(), {})

    def test_codex_arms_on_stop_even_though_its_payload_carries_the_same_fields(self):
        # Codex SubagentStop supplies agent_id and agent_transcript_path, but its rollout
        # transcript never records a child result, so only Claude gets delivery gating.
        self.assertEqual(self.child('agentten', harness='codex'), {})
        self.assertEqual(self.stop(harness='codex')['decision'], 'block')
        self.assertEqual(self.stop(harness='codex'), {})
        self.child('agentten')
        self.assertEqual(self.stop(), {})
        self.notification('agentten', '2026-09-14T17:10:00.000Z')
        self.assertEqual(self.stop()['decision'], 'block')


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
