import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import select
import struct
import subprocess
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
loader=importlib.machinery.SourceFileLoader('dagr_views',str(ROOT/'tools/nova-flow'))
spec=importlib.util.spec_from_loader(loader.name,loader)
dagr=importlib.util.module_from_spec(spec);loader.exec_module(dagr)


def fixture():
    data=dagr.create('View fixture','view-fixture')
    def change(*args):dagr.change(data,dagr.parser().parse_args(args))
    change('milestone','M1','Build')
    change('agent','worker','--model','fixture-model','--effort','max')
    change('task','add','T1','First task','--milestone','M1')
    change('task','set','T1','working')
    change('task','set','T1','done','--evidence','fixture only')
    change('task','add','T2','Retry task','--after','T1')
    change('task','set','T2','working','--agent','worker')
    change('task','set','T2','failed','--note','first attempt failed')
    change('task','retry','T2','--note','fix the failure','--agent','worker')
    change('task','add','JOIN','Combined checks','--kind','gate','--after','T1','--after','T2')
    return data


class ViewTests(unittest.TestCase):
    def test_attempt_identity_and_blocking_join(self):
        rows=dagr.view_rows(fixture());ids=[t['id'] for _,t in rows]
        self.assertEqual(ids,['T1.a1','T2.a1','T2.a2','JOIN'])
        self.assertTrue(rows[1][1]['_historical'])
        self.assertEqual(rows[1][1]['state'],'failed')
        self.assertEqual(rows[1][1]['_row_note'],'first attempt failed')
        self.assertEqual(rows[2][1]['state'],'working')
        self.assertEqual(rows[3][0],'⋈ ')
        self.assertEqual(rows[3][1]['_blockers'],['T2'])
        self.assertIn('fixture-model',dagr.task_runtime(fixture(),rows[1][1]))

    def test_search_fold_and_unknown_diagnostics(self):
        data=fixture()
        self.assertEqual(len(dagr.view_rows(data,'retry')),2)
        self.assertEqual(len(dagr.view_rows(data,'worker')),2)
        self.assertEqual(len(dagr.view_rows(data,'fixture-model')),2)
        self.assertEqual(len(dagr.view_rows(data,folded=True)),3)
        self.assertEqual(dagr.view_rows(data,'absent'),[])
        self.assertIn('No session telemetry observed','\n'.join(dagr.diagnostics(Path('/project/.nova'),data)))
        self.assertIn('no run.json','\n'.join(dagr.diagnostics(Path('/project/.nova'))))

    def test_elapsed_uses_settled_end(self):
        self.assertEqual(dagr.age_text('2026-09-07T10:00:00Z','2026-09-07T11:02:00Z'),'1h 2m')
        self.assertEqual(dagr.age_text(None),'unknown')

    @unittest.skipUnless(os.name=='posix','POSIX terminal required')
    def test_terminal_arrows_panels_resize_and_restore(self):
        import pty,fcntl,termios
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,'run.json').write_text(json.dumps(fixture()))
            master,slave=pty.openpty()
            self.addCleanup(os.close,master);self.addCleanup(os.close,slave)
            fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',32,140,0,0))
            before=termios.tcgetattr(slave)
            process=subprocess.Popen([str(ROOT/'tools/nova-flow'),'--dir',tmp,'view'],stdin=slave,stdout=slave,stderr=slave,env={**os.environ,'TERM':'xterm-256color','NOVA_FLOW_NO_WEB':'1'})
            self.addCleanup(lambda: process.poll() is None and process.kill())
            output=b''
            def drain():
                nonlocal output
                until=time.monotonic()+.3
                while time.monotonic()<until:
                    if select.select([master],[],[],.03)[0]: output+=os.read(master,65536)
            drain();os.write(master,b'\x1bOBd');drain()
            fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',24,70,0,0))
            import signal
            process.send_signal(signal.SIGWINCH);drain()
            os.write(master,b'q');process.wait(timeout=3);drain()
            self.assertEqual(process.returncode,0,output[-1500:])
            self.assertEqual(termios.tcgetattr(slave),before)
            for label in (b'T2',b'a2',b'TASK FLOW',b'Requires:',b'Retry'):
                self.assertIn(label,output)
