import tempfile
import unittest
from pathlib import Path
from test_dagr_views import dagr


class MigrationTests(unittest.TestCase):
    def test_preserves_bytes_identity_and_session_routing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            data=dagr.create('Old run','old')
            data['run']['owner']='codex:session'
            dagr.atomic(root/'run.json',data)
            original=(root/'run.json').read_bytes()
            dagr.migrate_legacy(root)
            self.assertFalse((root/'run.json').exists())
            self.assertEqual((root/'runs/old/run.json').read_bytes(),original)
            self.assertEqual(dagr.session_store(root,'codex','session'),root/'runs/old')
            self.assertEqual(dagr.selected_run(root)['run']['id'],'old')
            self.assertEqual(dagr.migrate_legacy(root),[])

    def test_collision_preserves_both_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'runs/old').mkdir(parents=True)
            dagr.atomic(root/'run.json',dagr.create('Original','old'))
            dagr.atomic(root/'runs/old/run.json',dagr.create('Different','old'))
            with self.assertRaises(ValueError):dagr.migrate_legacy(root)
            self.assertEqual(dagr.read(root/'run.json')['run']['title'],'Original')
            self.assertEqual(dagr.read(root/'runs/old/run.json')['run']['title'],'Different')

    def test_archive_is_still_selectable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'archive/old').mkdir(parents=True)
            dagr.atomic(root/'archive/old/run.json',dagr.create('Archived','old'))
            dagr.migrate_legacy(root)
            self.assertTrue((root/'runs/old/archive/old/run.json').exists())
            self.assertEqual(dagr.selected_run(root,'old')['run']['title'],'Archived')
