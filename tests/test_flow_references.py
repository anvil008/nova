import concurrent.futures
import tempfile
import unittest
from pathlib import Path
from test_dagr_views import dagr


class ReferenceTests(unittest.TestCase):
    def test_concurrent_runs_and_stability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def write(number):
                path=root/'runs'/str(number);path.mkdir(parents=True)
                data=dagr.create('Run',str(number))
                dagr.change(data,dagr.parser().parse_args(['task','add','work','Do work']))
                dagr.atomic(path/'run.json',data)
                return path,data
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(write,range(8)))
            refs=[data['tasks'][0]['display_ref'] for _,data in results]
            self.assertEqual(len(set(refs)),8)
            path,data=results[0];original=data['tasks'][0]['display_ref']
            data['tasks'][0]['title']='Renamed'
            dagr.atomic(path/'run.json',data)
            self.assertEqual(data['tasks'][0]['display_ref'],original)
            projection=dagr.selected_run(root)
            self.assertTrue(all(t['title']=='Run' or t['title'] in ('Do work','Renamed') for t in projection['tasks']))
            self.assertTrue(all(dagr.display_reference(t).startswith(('G','T')) for _,t in dagr.view_rows(projection)))
            self.assertEqual(len(dagr.work_tasks(projection)),8)

    def test_cli_accepts_display_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            dagr.main(['--dir',tmp,'init','Example','--id','run'])
            dagr.main(['--dir',tmp,'task','add','work','Original'])
            data=dagr.read(root/'run.json');ref=data['tasks'][0]['display_ref']
            dagr.main(['--dir',tmp,'task','rename',ref,'Renamed'])
            data=dagr.read(root/'run.json')
            self.assertEqual(data['tasks'][0]['title'],'Renamed')
            self.assertEqual(data['tasks'][0]['id'],'work')
