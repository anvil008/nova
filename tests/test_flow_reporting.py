import unittest
from test_dagr_views import dagr

class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.data=dagr.create('Flow','flow')
        self.change('agent','a','--harness','codex')
        self.agent=self.data['agents'][0];self.agent['session_id']='session'
    def change(self,*args):dagr.change(self.data,dagr.parser().parse_args(args));dagr.validate(self.data)
    def test_fallback_reuses_task_and_parent_without_dependencies(self):
        dagr.report_activity(self.data,self.agent,'PostToolUse',{'tool_name':'read'})
        first=self.agent['task'];task=dagr.find(self.data['tasks'],first)
        self.assertEqual(task['parent_id'],'scope');self.assertEqual(task['deps'],[])
        revision=self.data['revision']
        dagr.report_activity(self.data,self.agent,'PostToolUse',{'tool_name':'read'})
        self.assertEqual(self.agent['task'],first);self.assertEqual(self.data['revision'],revision)
        self.change('task','rename',first,'Inspect implementation')
        self.assertNotIn('provisional',task)
        self.assertTrue(dagr.task_rows(self.data)[1][0])
    def test_parent_cycles_rejected_and_parent_not_prerequisite(self):
        self.change('task','add','parent','Parent','--kind','group')
        self.change('task','add','child','Child','--parent','parent')
        self.change('task','set','child','working')
        with self.assertRaises(ValueError):self.change('task','parent','parent','child')
    def test_flow_commands_do_not_create_new_work(self):
        dagr.report_activity(self.data,self.agent,'PostToolUse',{'tool_input':{'command':'workcell-flow task set task done'}})
        self.assertEqual(self.data['tasks'],[])
    def test_child_inherits_assigned_context(self):
        self.change('task','add','scope','Scope')
        self.agent['parent_task']='scope'
        self.change('agent','helper','--parent','a')
        helper=self.data['agents'][1];helper['session_id']='child'
        dagr.report_activity(self.data,helper,'PostToolUse',{})
        self.assertEqual(dagr.find(self.data['tasks'],helper['task'])['parent_id'],'scope')
