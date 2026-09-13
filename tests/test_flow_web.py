import concurrent.futures
import json
import os
from pathlib import Path
import signal
import tempfile
import unittest
import urllib.request
from test_dagr_views import dagr

class ViewerTests(unittest.TestCase):
    def test_concurrent_start_reuses_server_and_reads_live_data(self):
        cache=Path.home()/'.cache/agent-work/nova/viewer-tests';cache.mkdir(parents=True,exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(dir=cache) as tmp:
                root=Path(tmp)/'.nova';pid=None;other_pid=None
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                        urls=list(pool.map(lambda _:dagr.ensure_viewer(root),range(3)))
                    self.assertEqual(len(set(urls)),1)
                    info=json.loads((root/'viewer.json').read_text());pid=info['pid']
                    base='http://127.0.0.1:'+str(info['port'])
                    with urllib.request.urlopen(base+'/') as response:self.assertIn(b'Work in motion',response.read())
                    with urllib.request.urlopen(base+'/api/demo') as response:
                        demo=json.load(response)
                    self.assertEqual(len(demo['tasks']),8)
                    self.assertEqual([t['state'] for _,t in demo['_view']['rows'] if t['_task_id']=='T03'],['failed','failed','working'])
                    self.assertFalse((root/'run.json').exists())
                    dagr.atomic(root/'run.json',dagr.create('Live test','test'))
                    with urllib.request.urlopen(base+'/api/run') as response:self.assertEqual(json.load(response)['run']['title'],'Live test')
                    self.assertEqual(dagr.ensure_viewer(root),urls[0])
                    other=Path(tmp)/'second-project/.nova'
                    other_url=dagr.ensure_viewer(other)
                    other_info=json.loads((other/'viewer.json').read_text());other_pid=other_info['pid']
                    self.assertNotEqual(other_info['port'],info['port'])
                    self.assertNotEqual(other_url,urls[0])
                    with urllib.request.urlopen('http://127.0.0.1:'+str(other_info['port'])+'/api/health') as response:self.assertEqual(json.load(response)['store'],str(other.resolve()))
                    self.assertEqual(dagr.ensure_viewer(root),urls[0])
                finally:
                    if pid:os.kill(pid,signal.SIGTERM)
                    if other_pid:os.kill(other_pid,signal.SIGTERM)
        finally:cache.rmdir()
