import tempfile
import unittest
from pathlib import Path
from test_dagr_views import dagr


class GroupTests(unittest.TestCase):
    def setUp(self):
        self.data=dagr.create('Test','test')
        self.change('task','add','group','Group','--kind','group')
        self.change('task','add','nested','Nested','--kind','group','--parent','group')
        self.change('task','add','task','Task','--parent','nested')
    def change(self,*args):
        dagr.change(self.data,dagr.parser().parse_args(args))
    def test_nested_progress_is_derived_without_mutating_records(self):
        self.change('task','set','task','working')
        rows={t['_task_id']:t for _,t in dagr.view_rows(self.data)}
        self.assertEqual(rows['group']['_group_label'],'1 working')
        self.assertEqual(rows['nested']['state'],'working')
        self.assertEqual(self.data['tasks'][0]['state'],'pending')
        self.assertEqual(dagr.task_runtime(self.data,rows['group'],True),'')
        self.assertEqual(len(dagr.work_tasks(self.data)),1)
        with self.assertRaises(ValueError):self.change('finish','--note','Still working')
    def test_finished_children_allow_finish_and_fold(self):
        self.change('task','set','task','working')
        self.change('task','set','task','done','--evidence','Fixture check passed')
        self.assertEqual(dagr.group_summary(self.data,self.data['tasks'][0]),('done','1/1 done'))
        self.assertEqual(dagr.view_rows(self.data,folded=True),[])
        self.change('finish','--note','Complete')
        dagr.validate(self.data)
    def test_empty_group_and_confirmed_session_exit(self):
        self.data['tasks']=self.data['tasks'][:1]
        self.assertEqual(dagr.group_summary(self.data,self.data['tasks'][0]),('pending','No tasks'))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.data['run']['owner']='codex:s'
            dagr.atomic(root/'run.json',self.data)
            dagr.lifecycle(root,'codex','s','start')
            destination=dagr.lifecycle(root,'codex','s','end')
            self.assertTrue(destination.exists())
            self.assertFalse((root/'run.json').exists())
