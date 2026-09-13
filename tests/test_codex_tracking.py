import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tracking', ROOT / 'hooks/codex-tracking.py')
tracking = importlib.util.module_from_spec(spec); spec.loader.exec_module(tracking)


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); (self.root / '.git').mkdir()
        (self.root / 'nested').mkdir()
        self.log = self.root / 'session.jsonl'
        self.log.write_text(json.dumps({'type': 'session_meta', 'payload': {'id': 'session1'}})+'\n')
        self.payload = dict(session_id='session1', cwd=str(self.root / 'nested'), model='fixture-model', transcript_path=str(self.log))

    def hook(self, kind, **kwargs):
        return tracking.handle({**self.payload, 'hook_event_name': kind, **kwargs})

    def data(self):
        return tracking.dagr.read(self.root / '.nova/run.json')

    def settle(self,data):
        for task in data['tasks']:
            if task['state'] not in tracking.dagr.TERMINAL:
                tracking.dagr.change(data,tracking.dagr.parser().parse_args(['task','set',task['id'],'canceled','--note','Fixture cleanup']))

    def append(self, typ, payload, timestamp='2026-09-07T21:00:00Z'):
        with self.log.open('a') as f: f.write(json.dumps(dict(type=typ, payload=payload, timestamp=timestamp))+'\n')

    def tokens(self, n):
        self.append('event_msg', {'type': 'token_count', 'info': {'total_token_usage': {'input_tokens': n, 'cached_input_tokens': n//2, 'output_tokens': n//10}}})

    def test_register_resumption_dedup_stop_and_nested_root(self):
        self.hook('SessionStart'); first=self.data()
        self.hook('SessionStart'); self.assertEqual(self.data(), first)
        self.assertFalse((self.root/'nested/.nova').exists())
        self.assertEqual(first['agents'][0]['model'], 'fixture-model')
        self.hook('Stop'); self.assertEqual(self.data()['run']['state'], 'active')
        self.assertEqual(self.data()['agents'][0]['state'], 'idle')
        self.hook('TranscriptPoll'); self.assertEqual(self.data()['agents'][0]['state'], 'idle')
        self.hook('UserPromptSubmit'); self.assertEqual(len(self.data()['agents']), 1)

    def test_usage_baseline_binding_replay_and_stop_preserves_work(self):
        self.append('turn_context', {'model':'actual-model', 'effort':'max', 'turn_id':'turn1'})
        self.tokens(100); self.hook('SessionStart')
        data=self.data(); agent=data['agents'][0]
        self.assertEqual(agent['usage'][0]['input_tokens'],100)
        self.assertEqual(agent['effort'],'max')
        args=tracking.dagr.parser().parse_args(['task','add','T1','Work'])
        tracking.dagr.change(data,args)
        tracking.dagr.change(data,tracking.dagr.parser().parse_args(['task','set','T1','working']))
        tracking.dagr.change(data,tracking.dagr.parser().parse_args(['session','bind','session1','--task','T1']))
        # Deterministic binding time relative to fixture turn context.
        data['agents'][0]['binding']['at']='2026-09-07T21:01:00Z'
        tracking.dagr.atomic(self.root/'.nova/run.json',data)
        self.tokens(120); self.hook('PostToolUse') # old turn: session-only
        self.append('turn_context', {'model':'actual-model','effort':'low','turn_id':'turn2'},'2026-09-07T21:02:00Z')
        self.tokens(160); self.hook('PostToolUse')
        data=self.data(); self.assertEqual(data['tasks'][0]['attempts'][0]['usage'][0]['input_tokens'],40)
        self.assertEqual(sum(u['input_tokens'] for u in data['agents'][0]['usage']),120)
        self.tokens(160); self.hook('PostToolUse')
        self.assertEqual(len(self.data()['tasks'][0]['attempts'][0]['usage']),1)
        self.hook('Stop'); self.assertEqual(self.data()['tasks'][0]['state'],'working')
        self.assertEqual(self.data()['agents'][0]['state'],'idle')

    def test_subagent_never_reads_parent_transcript_or_model(self):
        self.tokens(100)
        self.hook('SubagentStart', agent_id='child', agent_type='scout')
        data=self.data(); parent,child=data['agents']
        self.assertEqual(child['parent'],parent['id'])
        self.assertEqual(child['model'],'')
        self.hook('SubagentStop',agent_id='child',agent_transcript_path=str(self.log))
        child=self.data()['agents'][1]
        self.assertNotIn('usage',child)
        self.assertIn('mismatch',child['telemetry']['warning'])

    def test_partial_line_and_terminal_run_immutable(self):
        self.hook('SessionStart')
        with self.log.open('ab') as f:f.write(b'{"type":')
        self.hook('PostToolUse'); self.assertNotIn('usage',self.data()['agents'][0])
        self.hook('Stop');data=self.data()
        self.settle(data)
        tracking.dagr.change(data,tracking.dagr.parser().parse_args(['finish','--note','done']))
        tracking.dagr.atomic(self.root/'.nova/run.json',data)
        self.hook('SessionStart'); self.assertEqual(self.data(),data)

    def test_archive_late_hooks_do_not_reopen_and_sparse_counters(self):
        self.hook('Stop'); self.assertFalse((self.root/'.nova/run.json').exists())
        self.tokens(100); self.hook('SessionStart')
        self.append('event_msg', {'type':'token_count','info':{'total_token_usage':{'output_tokens':12}}})
        self.hook('PostToolUse'); self.tokens(150); self.hook('PostToolUse')
        self.assertEqual(sum(u.get('input_tokens',0) for u in self.data()['agents'][0]['usage']),150)
        self.hook('Stop'); data=self.data()
        self.settle(data)
        tracking.dagr.change(data, tracking.dagr.parser().parse_args(['finish','--note','finished']))
        tracking.dagr.atomic(self.root/'.nova/run.json',data)
        tracking.dagr.archive(self.root/'.nova')
        for kind in ('Stop','PostToolUse','SessionStart','UserPromptSubmit'):
            self.hook(kind)
            self.assertFalse((self.root/'.nova/run.json').exists())

    def test_explicit_attach_carries_baseline_not_historical_usage(self):
        import subprocess, sys
        self.tokens(100); self.hook('SessionStart'); self.hook('Stop')
        data=self.data(); run_id=data['run']['id']
        self.settle(data)
        tracking.dagr.change(data,tracking.dagr.parser().parse_args(['finish','--note','finished']))
        tracking.dagr.atomic(self.root/'.nova/run.json',data)
        tracking.dagr.archive(self.root/'.nova')
        tracking.dagr.atomic(self.root/'.nova/run.json',tracking.dagr.create('Next task'))
        result=subprocess.run([sys.executable,str(ROOT/'tools/nova-flow'),'--dir',str(self.root/'.nova'),'session','attach','session1','--archive',run_id],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('usage',self.data()['agents'][0])
        self.tokens(150); self.hook('UserPromptSubmit')
        self.assertEqual(self.data()['agents'][0]['usage'][0]['input_tokens'],50)
        result=subprocess.run([sys.executable,str(ROOT/'hooks/codex-tracking.py')],input=json.dumps({**self.payload,'hook_event_name':'Stop'}),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),{})
        self.assertEqual(self.data()['agents'][0]['state'],'idle')

    def test_reset_restarts_current_counter_and_continues_collection(self):
        self.append('turn_context',{'model':'m'})
        self.tokens(1000);self.hook('SessionStart')
        self.tokens(20);self.hook('PostToolUse')
        self.tokens(50);self.hook('PostToolUse')
        state=self.data()['agents'][0]['telemetry']
        self.assertEqual(state['totals']['input_tokens'],50)
        self.assertEqual(sum(u['input_tokens'] for u in state['counter_usage']),50)
        self.assertEqual(state['counter_resets'],1)
        before=self.data();self.hook('TranscriptPoll');self.assertEqual(self.data(),before)

    def test_legacy_stuck_cursor_rebuilds_without_rewriting_history(self):
        self.tokens(1000);self.tokens(20);self.hook('SessionStart')
        data=self.data();agent=data['agents'][0]
        history=json.loads(json.dumps(agent.get('usage',[])))
        agent['telemetry'].pop('counter_usage',None)
        agent['telemetry']['totals']['input_tokens']=1000
        agent['telemetry']['warning']='Cumulative counters decreased; usage after reset is unattributed.'
        tracking.dagr.atomic(self.root/'.nova/run.json',data)
        self.hook('TranscriptPoll');agent=self.data()['agents'][0]
        self.assertEqual(agent['telemetry']['totals']['input_tokens'],20)
        self.assertEqual(agent['usage'],history)
        self.assertNotIn('warning',agent['telemetry'])
