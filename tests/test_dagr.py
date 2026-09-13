import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import re
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/nova-flow'
loader = importlib.machinery.SourceFileLoader('nova_dagr', str(TOOL))
spec = importlib.util.spec_from_loader(loader.name, loader)
dagr = importlib.util.module_from_spec(spec); loader.exec_module(dagr)


class DagrTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nova-flow-')
        self.addCleanup(self.temp.cleanup)
        self.store = Path(self.temp.name) / 'runs'

    def cli(self, *args, success=True):
        result = subprocess.run([sys.executable, str(TOOL), '--dir', str(self.store), *args],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def data(self):
        return json.loads((self.store / 'run.json').read_text())

    def initial(self):
        self.cli('init', 'A feature', '--id', 'feature')
        self.cli('milestone', 'm1', 'Define behavior')
        self.cli('task', 'add', 'spec', 'Agree on behavior', '--milestone', 'm1')

    def test_usage_is_attributed_idempotent_and_retained_on_retry(self):
        self.initial()
        self.cli('agent', 'worker', '--harness', 'codex', '--model', 'test-model', '--effort', 'max')
        self.cli('task', 'set', 'spec', 'working', '--agent', 'worker')
        args = ('usage', 'spec', '--record', 'request1', '--source', 'fixture response', '--agent', 'worker')
        self.cli(*args, '--input-tokens', '100', '--cache-read-tokens', '60', '--output-tokens', '20')
        self.cli(*args, '--input-tokens', '120')
        attempt = self.data()['tasks'][0]['attempts'][0]
        self.assertEqual(len(attempt['usage']), 1)
        self.assertEqual(attempt['usage'][0]['input_tokens'], 120)
        self.assertEqual(attempt['usage'][0]['output_tokens'], 20)
        self.assertEqual(attempt['workers']['worker']['model'], 'test-model')
        before = (self.store / 'run.json').read_bytes()
        self.cli(*args, '--output-tokens', '-1', success=False)
        self.assertEqual((self.store / 'run.json').read_bytes(), before)
        self.cli('task', 'set', 'spec', 'failed', '--note', 'retry needed')
        self.cli('task', 'retry', 'spec', '--note', 'second attempt')
        self.cli(*args, '--output-tokens', '2', success=False)
        self.cli('usage', 'spec', '--record', 'request2', '--source', 'second fixture', '--output-tokens', '5')
        task = self.data()['tasks'][0]
        self.assertEqual(task['attempts'][0]['usage'], attempt['usage'])
        report = '\n'.join(dagr.usage_lines(task))
        self.assertIn('output tokens: 25', report)
        self.assertIn('input tokens: 120 (partial)', report)
        self.assertIn('reasoning tokens: not reported', report)

    def test_ungrouped_task_and_late_agent_assignment(self):
        self.cli('init', 'Discovery', '--id', 'discovery')
        self.cli('task', 'add', 'T1', 'Investigate request')
        self.cli('task', 'set', 'T1', 'working')
        self.cli('agent', 'scout', '--task', 'T1', '--model', 'test-model', '--effort', 'low')
        data = self.data(); task = data['tasks'][0]
        self.assertIsNone(task['milestone'])
        self.assertNotIn('Ungrouped', dagr.terminal(data))
        self.assertEqual(dagr.task_tags(task), '')
        self.assertEqual(dagr.task_runtime(data, task), 'test-model·low')
        self.assertEqual(dagr.task_tokens(task), '—/—')
        self.cli('usage', 'T1', '--record', 'count1', '--source', 'fixture', '--input-tokens', '12000', '--output-tokens', '0')
        self.assertEqual(dagr.task_tokens(self.data()['tasks'][0]), '12.0k/0')
        self.cli('task', 'add', 'T2', 'Bad milestone', '--milestone', 'missing', success=False)

    def test_optional_issue_and_milestone_labels(self):
        self.initial()
        self.cli('task','add','fix','Fix cache expiry','--issue','https://github.com/example/project/issues/42')
        task=self.data()['tasks'][-1]
        self.assertEqual(dagr.task_tags(task),'[#42] ')
        self.cli('task','edit','fix','--milestone','m1')
        self.assertEqual(dagr.task_tags(self.data()['tasks'][-1]),'[m1 · #42] ')
        self.cli('task','add','bad','Bad link','--issue','https://example.com/issues/42',success=False)

    def test_full_lifecycle_subagents_and_archive(self):
        self.initial()
        self.cli('agent', 'main', '--harness', 'codex', '--phase', 'spec', '--activity', 'Interviewing user')
        self.cli('agent', 'scout', '--parent', 'main', '--role', 'scout', '--model', 'example-model')
        self.cli('task', 'set', 'spec', 'working', '--agent', 'scout')
        self.cli('task', 'set', 'spec', 'done', '--evidence', 'docs/specs/spec01.md')
        self.cli('phase', 'plan')
        self.cli('finish', '--note', 'Specification complete')
        before = (self.store / 'run.json').read_bytes()
        self.cli('archive')
        self.assertFalse((self.store / 'run.json').exists())
        self.assertEqual((self.store / 'archive/feature/run.json').read_bytes(), before)
        self.cli('view', '--archive', 'feature')
        self.assertTrue(json.loads(self.cli('list').stdout)[0]['archived'])
        self.cli('init', 'Next task', '--id', 'next')
        self.assertEqual((self.store / 'archive/feature/run.json').read_bytes(), before)

    def test_dependencies_and_invalid_updates_preserve_live_bytes(self):
        self.initial()
        self.cli('task', 'add', 'build', 'Implement', '--milestone', 'm1', '--after', 'spec')
        before = (self.store / 'run.json').read_bytes()
        self.cli('task', 'set', 'build', 'working', success=False)
        self.cli('task', 'set', 'spec', 'done', '--evidence', 'claim', success=False)
        self.assertEqual((self.store / 'run.json').read_bytes(), before)
        self.cli('task', 'set', 'spec', 'working')
        self.cli('task', 'set', 'spec', 'done', success=False)
        self.cli('task', 'set', 'spec', 'done', '--evidence', 'accepted spec')
        self.cli('task', 'set', 'build', 'working')
        self.cli('task', 'retry', 'spec', '--note', 'new question', success=False)

    def test_retry_keeps_previous_attempt_and_events(self):
        self.initial()
        self.cli('task', 'set', 'spec', 'working')
        self.cli('task', 'set', 'spec', 'failed', '--note', 'Missing answer')
        previous = self.data()
        self.cli('task', 'retry', 'spec', '--note', 'Answer arrived')
        current = self.data()
        self.assertEqual(current['tasks'][0]['attempts'][0], previous['tasks'][0]['attempts'][0])
        self.assertEqual(current['events'][:-1], previous['events'])
        self.assertEqual(len(current['tasks'][0]['attempts']), 2)
        self.cli('task', 'set', 'spec', 'done', '--evidence', 'check passed', '--verified', '--source-revision', 'abc123')
        self.assertEqual(self.data()['tasks'][0]['attempts'][-1]['evidence_level'], 'verified')

    def test_terminal_run_and_archives_cannot_be_overwritten(self):
        self.initial()
        self.cli('archive', success=False)
        self.cli('task', 'set', 'spec', 'canceled', '--note', 'No longer requested')
        self.cli('agent', 'worker', '--state', 'working')
        self.cli('finish', '--note', 'Done', success=False)
        self.cli('agent', 'worker', '--state', 'done')
        self.cli('finish', '--note', 'Canceled scope', '--state', 'canceled')
        self.cli('phase', 'build', success=False)
        destination = self.store / 'archive/feature'
        destination.mkdir(parents=True); (destination / 'run.json').write_text('existing history')
        self.cli('archive', success=False)
        self.assertEqual((destination / 'run.json').read_text(), 'existing history')
        self.assertTrue((self.store / 'run.json').is_file())

    def test_concurrent_updates_are_serialized(self):
        self.initial()
        commands = [[sys.executable, str(TOOL), '--dir', str(self.store), 'agent', f'worker-{n}', '--role', 'scout'] for n in range(8)]
        processes = [subprocess.Popen(c, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for c in commands]
        for p in processes:
            out, err = p.communicate(timeout=10)
            self.assertEqual(p.returncode, 0, err)
        data = self.data()
        self.assertEqual(len(data['agents']), 8)
        self.assertEqual(data['revision'], 11)
        dagr.validate(data)

    def test_validation_rejects_cycles_unknown_refs_and_malformed_states(self):
        self.initial()
        data = self.data(); data['tasks'][0]['deps'] = ['spec']
        with self.assertRaises(ValueError): dagr.validate(data)
        data['tasks'][0]['deps'] = ['unknown']
        with self.assertRaises(ValueError): dagr.validate(data)
        data = self.data(); data['nova_dagr'] = 400
        with self.assertRaises(ValueError): dagr.validate(data)
        self.cli('agent', 'main')
        self.cli('agent', 'child', '--parent', 'main')
        self.cli('agent', 'main', '--parent', 'child', success=False)
        self.cli('view', '--archive', '../escape', success=False)

    def test_archive_recovers_after_link_before_unlink(self):
        self.initial()
        self.cli('task', 'set', 'spec', 'canceled', '--note', 'Canceled')
        self.cli('finish', '--state', 'canceled', '--note', 'Stopped')
        destination = self.store / 'archive/feature'; destination.mkdir(parents=True)
        (destination / 'run.json').hardlink_to(self.store / 'run.json')
        self.cli('archive')
        self.assertFalse((self.store / 'run.json').exists())
        self.cli('check', '--archive', 'feature')

    def test_view_sanitizes_terminal_escape_sequences(self):
        self.cli('init', 'Title\x1b[31m red')
        output = self.cli('view').stdout
        self.assertNotIn('\x1b', output)

    def test_browser_api_is_read_only_and_rejects_archive_traversal(self):
        self.initial()
        process = subprocess.Popen([sys.executable, str(TOOL), '--dir', str(self.store),
                                    'serve', '--port', '0'], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        def stop():
            process.terminate(); process.wait(timeout=5)
            process.stdout.close(); process.stderr.close()
        self.addCleanup(stop)
        line = process.stdout.readline()
        address = re.search(r'http://127.0.0.1:[0-9]+', line).group(0)
        with urllib.request.urlopen(address + '/api/run', timeout=3) as response:
            self.assertEqual(json.load(response)['run']['id'], 'feature')
        with urllib.request.urlopen(address + '/', timeout=3) as response:
            self.assertIn('Work in motion', response.read().decode())
        for request in [address + '/api/run?id=../escape', address + '/arbitrary-file',
                        urllib.request.Request(address + '/api/run', data=b'{}', method='POST')]:
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(request, timeout=3)
        self.assertEqual(self.data()['revision'], 3)

    def test_archived_id_reuse_and_run_symlinks_are_rejected(self):
        self.initial()
        self.cli('task', 'set', 'spec', 'canceled', '--note', 'Canceled')
        self.cli('finish', '--state', 'canceled', '--note', 'Canceled')
        self.cli('archive')
        self.cli('init', 'Another run', '--id', 'feature', success=False)
        (self.store / 'run.json').symlink_to(self.store / 'archive/feature/run.json')
        self.cli('phase', 'build', success=False)
        self.cli('archive', success=False)

    def test_replanning_and_progress_notes_are_semantic_updates(self):
        self.initial()
        self.cli('task', 'edit', 'spec', '--title', 'Refined requirement', '--phase', 'plan')
        self.cli('task', 'edit', 'spec', '--after', 'spec', success=False)
        self.cli('task', 'set', 'spec', 'working')
        self.cli('task', 'edit', 'spec', '--title', 'Change scope mid-attempt', success=False)
        self.cli('task', 'note', 'spec', 'Two examples clarified')
        task = self.data()['tasks'][0]
        self.assertEqual(task['title'], 'Refined requirement')
        self.assertEqual(task['note'], 'Two examples clarified')
        self.assertEqual(len(task['attempts']), 1)


if __name__ == '__main__':
    unittest.main()
