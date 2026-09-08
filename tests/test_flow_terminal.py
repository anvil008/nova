import importlib.machinery
import importlib.util
from pathlib import Path
import unittest

loader=importlib.machinery.SourceFileLoader('flow_v2',str(Path(__file__).resolve().parents[1]/'tools/nova-flow'))
spec=importlib.util.spec_from_loader(loader.name,loader)
v2=importlib.util.module_from_spec(spec);loader.exec_module(v2)

class LaneTests(unittest.TestCase):
    def test_demo_uses_recorded_parentage(self):
        data=v2.demo();lanes,rows=v2.layout(data)
        self.assertEqual(len(lanes),3)
        self.assertEqual([r['lane'] for r in rows],[0,1,2,2,2,0,0,0,0,0])
        self.assertTrue(rows[1]['delegated'])
        self.assertIsNone(rows[-1]['owner'])
        self.assertIn('Executor not assigned',' '.join(v2.inspector(data,rows[-1],80)))
    def test_layout_does_not_mutate_state_or_invent_delegation(self):
        import copy
        data=v2.demo()
        for a in data['agents']:a['parent']=None
        before=copy.deepcopy(data)
        lanes,rows=v2.layout(data)
        self.assertEqual(len(lanes),1)
        self.assertFalse(any(r['delegated'] for r in rows))
        self.assertEqual(data,before)

    def test_objectives_stay_separate(self):
        data=v2.demo()
        for ident in ('first','second'):
            v2.change(data,v2.parser().parse_args(['task','add',ident,ident,'--kind','group']))
        for index,task in enumerate(data['tasks'][:8]):task['parent_id']='first' if index<2 else 'second'
        lanes,rows=v2.layout(data)
        groups=v2.sections(data,rows)
        self.assertEqual([g['title'] for g in groups],['first','second'])
        self.assertEqual([len(g['rows']) for g in groups],[2,8])

    def test_demo_exposes_failures_retries_and_other_states(self):
        data=v2.demo();_,rows=v2.layout(data)
        retry=[r['task'] for r in rows if r['task']['_task_id']=='T03']
        self.assertEqual([v2.display_reference(t) for t in retry],['T03.a1','T03.a2','T03.a3'])
        self.assertEqual([t['state'] for t in retry],['failed','failed','working'])
        self.assertTrue({'failed','blocked','canceled','pending','working','done'} <= {r['task']['state'] for r in rows})

    def test_task_tree_nests_children_and_attempts_not_dependencies(self):
        data=v2.demo();_,rows=v2.layout(data)
        tree=v2.tree_rows(data,rows)
        self.assertEqual([r['ref'] for r in tree],['T01','T02','T03','a1','a2','a3','T04','T05','T06','T07','T08'])
        self.assertEqual(tree[1]['tree'],'│ ├─')
        self.assertEqual(tree[3]['tree'],'│   ├─')
        self.assertEqual(tree[6]['tree'],'├─')
        self.assertEqual(v2.requirements(data,tree[6]),'T02, T03')
        self.assertEqual(sum(not r['attempt_row'] for r in tree),8)
        self.assertEqual(len(v2.sections(data,rows)),1)
        v2.validate(data)

    def test_hidden_parent_leaves_visible_child_selectable(self):
        data=v2.demo();_,rows=v2.layout(data)
        rows=[r for r in rows if r['task']['state'] not in ('done','canceled')]
        tree=v2.tree_rows(data,rows)
        self.assertEqual(tree[0]['ref'],'T03')
        self.assertEqual(tree[0]['tree'],'├─')
        self.assertEqual(len({r['task']['id'] for r in tree}),len(tree))

    def test_usage_deduplicates_and_prices_cache_without_double_counting(self):
        data=v2.demo()
        record=dict(id='sample',harness='codex',model='test-model',input_tokens=1000,output_tokens=100,cache_read_tokens=800,cache_write_tokens=0)
        data['agents'][0]['usage']=[record]
        data['tasks'][0]['attempts'][0]['usage']=[dict(record)]
        prices={'codex/test-model':dict(input_tokens=10,output_tokens=20,cache_read_tokens=1,cache_write_tokens=10,input_includes_cache=True)}
        lines=v2.usage_header(data,prices)
        self.assertIn('1.1k',lines[0])
        self.assertIn('200',lines[2])
        self.assertIn('$0.0008',lines[3])
        self.assertIn('$0.0048',lines[6])
        self.assertNotIn('Tokens',' '.join(v2.inspector(data,v2.layout(data)[1][0],100)))

    def test_usage_missing_prices_and_fields_are_not_zero(self):
        data=v2.demo();data['agents'][0]['usage']=[dict(id='x',model='m',input_tokens=10)]
        lines=v2.usage_header(data)
        self.assertIn('—',lines[2])
        self.assertIn('—',lines[6])

    def test_current_native_snapshot_replaces_historical_records(self):
        data=v2.demo();agent=data['agents'][0]
        old=dict(id='old',harness='codex',model='m',agent=agent['id'],input_tokens=1000,output_tokens=100)
        agent['usage']=[old];data['tasks'][0]['attempts'][0]['usage']=[old]
        agent['telemetry']={'counter_usage':[dict(old,id='snapshot',input_tokens=20,output_tokens=2)],'counter_at':'2026-09-08T06:00:00Z'}
        groups=v2.aggregate_usage(data)
        self.assertEqual(sum(u['input_tokens'] for rs in groups.values() for u in rs),20)
        self.assertIn('latest counters',v2.usage_header(data)[-1])
