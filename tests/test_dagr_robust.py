"""Behavioral coverage for retry causality, explicit kinds and bounded storage."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_dagr_views import dagr

class RobustTests(unittest.TestCase):
    def setUp(self):
        self.data=dagr.create('Robust fixture','robust')
    def change(self,*args):
        candidate=copy.deepcopy(self.data)
        dagr.change(candidate,dagr.parser().parse_args(args));dagr.validate(candidate)
        self.data=candidate
    def done(self,id):
        self.change('task','set',id,'working')
        self.change('task','set',id,'done','--evidence','fixture check')
    def test_review_causes_retry_without_rewriting_history(self):
        self.change('task','add','build','Implement')
        self.done('build')
        self.change('task','add','review','Check implementation','--kind','review','--after','build')
        self.done('review')
        historical=copy.deepcopy(self.data['tasks'][0]['attempts'][0])
        self.change('task','retry','build','--cause','review.a1','--note','Address finding')
        rows=[t for _,t in dagr.view_rows(self.data)]
        self.assertEqual([t['id'] for t in rows],['build.a1','review.a1','build.a2'])
        self.assertEqual(rows[1]['_inputs'],['build.a1'])
        self.assertEqual(rows[2]['_cause'],'review.a1')
        self.assertEqual(self.data['tasks'][0]['attempts'][0],historical)
        bad=copy.deepcopy(self.data);bad['tasks'][0]['attempts'][1]['cause']['ref']='build.a2'
        with self.assertRaises(ValueError):dagr.validate(bad)
        bad['tasks'][0]['attempts'][1]['cause']['ref']='absent.a1'
        with self.assertRaises(ValueError):dagr.validate(bad)
    def test_only_explicit_gate_is_join(self):
        for id in ('a','b'):self.change('task','add',id,id)
        for id,kind in [('ordinary','task'),('join','gate'),('ask','question')]:
            self.change('task','add',id,id,'--kind',kind,'--after','a','--after','b')
        rows={t['_task_id']:t for _,t in dagr.view_rows(self.data)}
        self.assertFalse(rows['ordinary']['_join']);self.assertTrue(rows['join']['_join'])
        self.assertEqual(rows['ask']['_blockers'],['a','b'])
        with self.assertRaises(ValueError):self.change('task','add','invalid','No inputs','--kind','gate')
    def test_progress_is_per_attempt_and_invalid_write_preserves_file(self):
        self.change('task','add','work','Work');self.change('task','set','work','working')
        self.change('task','progress','work','--done','2','--total','5','--note','Checking')
        self.assertEqual(dagr.view_rows(self.data)[0][1]['_progress']['done'],2)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'run.json';dagr.atomic(path,self.data);before=path.read_bytes()
            bad=copy.deepcopy(self.data);bad['tasks'][0]['attempts'][0]['progress']['done']=6
            with self.assertRaises(ValueError):dagr.atomic(path,bad)
            self.assertEqual(path.read_bytes(),before)
        self.change('task','set','work','failed','--note','Retry')
        self.change('task','retry','work','--note','Continue')
        self.assertNotIn('progress',self.data['tasks'][0]['attempts'][1])
    def test_byte_limit_checks_actual_serialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'run.json';dagr.atomic(path,self.data);before=path.read_bytes()
            with patch.object(dagr,'MAX_BYTES',len(before)-1):
                with self.assertRaises(ValueError):dagr.atomic(path,self.data)
                with self.assertRaises(ValueError):dagr.read(path)
            self.assertEqual(path.read_bytes(),before)
    def test_deep_cycle_detection_is_iterative(self):
        items=[{'id':str(i),'deps':[str(i-1)] if i else []} for i in range(3000)]
        dagr.acyclic(items,lambda x:x['deps'])
        items[0]['deps']=['2999']
        with self.assertRaises(ValueError):dagr.acyclic(items,lambda x:x['deps'])
    def test_graph_and_event_limits(self):
        with patch.object(dagr,'MAX_EVENTS',0):
            with self.assertRaises(ValueError):dagr.validate(self.data)
        self.change('task','add','a','A')
        with patch.object(dagr,'MAX_ITEMS',0):
            with self.assertRaises(ValueError):dagr.validate(self.data)
