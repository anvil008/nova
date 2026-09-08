import tempfile
import unittest
import subprocess
from pathlib import Path
from test_dagr_views import dagr

class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store=self.root/'.nova'
    def test_independent_sessions_and_joined_participants(self):
        a=dagr.lifecycle(self.store,'codex','a','start',workspace=self.root)
        b=dagr.lifecycle(self.store,'agy','b','start',workspace=self.root)
        self.assertNotEqual(a,b)
        run=dagr.read(a/'run.json')['run']['id']
        helper=dagr.lifecycle(self.store,'agy','helper','start',join=run,workspace=self.root/'ui')
        self.assertEqual(helper,a)
        dagr.lifecycle(self.store,'codex','a','end',workspace=self.root)
        self.assertTrue((a/'run.json').exists())
        archived=dagr.lifecycle(self.store,'agy','helper','end',workspace=self.root/'ui')
        self.assertTrue(archived.exists());self.assertFalse((a/'run.json').exists())
        self.assertTrue((b/'run.json').exists())
    def test_unfinished_session_is_resumable(self):
        a=dagr.lifecycle(self.store,'agy','a','start',workspace=self.root)
        data=dagr.read(a/'run.json');dagr.change(data,dagr.parser().parse_args(['task','add','work','Unfinished']))
        dagr.atomic(a/'run.json',data)
        dagr.lifecycle(self.store,'agy','a','end',workspace=self.root)
        self.assertEqual(dagr.read(a/'run.json')['run']['lifecycle'],'interrupted')
        self.assertEqual(dagr.lifecycle(self.store,'agy','a','start',workspace=self.root),a)
        self.assertEqual(dagr.read(a/'run.json')['run']['lifecycle'],'active')
    def test_aggregate_namespaces_identical_task_ids(self):
        for harness in ('codex','agy'):
            a=dagr.lifecycle(self.store,harness,'same','start',workspace=self.root)
            data=dagr.read(a/'run.json');dagr.change(data,dagr.parser().parse_args(['task','add','work',harness]));dagr.atomic(a/'run.json',data)
        data=dagr.selected_run(self.store)
        self.assertEqual(len(dagr.view_rows(data)),4)
        self.assertEqual(len(dagr.work_tasks(data)),2)
        self.assertEqual(len({t['id'] for t in data['tasks']}),4)
        self.assertEqual(len(dagr.summaries(self.store)),2)
    def test_git_worktree_shared_store_and_unrelated_clone(self):
        repo=self.root/'repo';subprocess.run(['git','init','-q',str(repo)],check=True)
        subprocess.run(['git','-C',str(repo),'-c','user.name=Test','-c','user.email=test@example.com','commit','--allow-empty','-qm','init'],check=True)
        tree=self.root/'tree';subprocess.run(['git','-C',str(repo),'worktree','add','-qb','other',str(tree)],check=True)
        self.assertEqual(dagr.project_store(repo),dagr.project_store(tree))
        other=self.root/'other';subprocess.run(['git','init','-q',str(other)],check=True)
        self.assertNotEqual(dagr.project_store(repo),dagr.project_store(other))
    def test_jj_workspace_pointer(self):
        repo=self.root/'repo';(repo/'.jj/repo').mkdir(parents=True)
        tree=self.root/'tree';(tree/'.jj').mkdir(parents=True)
        (tree/'.jj/repo').write_text(str(repo/'.jj/repo'))
        self.assertEqual(dagr.project_store(repo),dagr.project_store(tree))
    def test_launcher_exit_archives_empty_run(self):
        tool=Path(__file__).resolve().parents[1]/'tools/nova-flow'
        result=subprocess.run([str(tool),'--dir',str(self.store),'track','--harness','agy','--session','launch','--','python3','-c','import os; assert os.environ["NOVA_RUN_ID"]'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(dagr.summaries(self.store)[0]['archived'])
