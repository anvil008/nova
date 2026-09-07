import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('native_tracking',Path(__file__).resolve().parents[1]/'hooks/native-tracking.py')
native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)

class NativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.env=patch.dict('os.environ',{},clear=True);self.env.start();self.addCleanup(self.env.stop)
    def test_agy_documented_payload_registers_and_stop_stays_open(self):
        payload=dict(conversationId='agy1',workspacePaths=[str(self.root)],modelName='observed-model',invocationNum=0)
        self.assertIn('injectSteps',native.handle('agy','PreInvocation',payload))
        store=native.dagr.run_paths(self.root/'.workcell')[0]
        native.handle('agy','Stop',{**payload,'fullyIdle':True})
        data=native.dagr.read(store)
        self.assertEqual(data['agents'][0]['state'],'idle');self.assertEqual(data['run']['state'],'active')
        self.assertEqual(data['agents'][0]['model'],'observed-model');self.assertNotIn('usage',data['agents'][0])
    def test_claude_child_and_end_archive_after_last_participant(self):
        payload=dict(session_id='main',cwd=str(self.root),model='parent-model')
        native.handle('claude','SessionStart',payload)
        native.handle('claude','SubagentStart',{**payload,'agent_id':'child'})
        path=native.dagr.run_paths(self.root/'.workcell')[0];data=native.dagr.read(path)
        self.assertEqual(len(data['agents']),2);self.assertEqual(data['agents'][1]['model'],'')
        native.handle('claude','SessionEnd',payload);self.assertTrue(path.exists())
        native.handle('claude','SubagentStop',{**payload,'agent_id':'child'})
        self.assertFalse(path.exists())
        native.handle('claude','SessionEnd',payload)
        self.assertFalse(native.dagr.run_paths(self.root/'.workcell'))
    def test_ambiguous_agy_projects_not_combined(self):
        other=self.root/'other';other.mkdir()
        with self.assertRaises(ValueError):native.handle('agy','PreInvocation',dict(conversationId='x',workspacePaths=[str(self.root),str(other)]))
