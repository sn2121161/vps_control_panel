"""Recovery and privacy checks using synthetic data, not a live panel."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('backup', Path(__file__).parents[1] / 'scripts/backup.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class SnapshotTest(unittest.TestCase):
    def test_restorable_allowlisted_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder in ('data', 'state', 'local', 'secrets', 'backups'):
                (root / folder).mkdir()
            with sqlite3.connect(root / 'data/x-ui.db') as con:
                con.execute('CREATE TABLE example(value TEXT)')
                con.execute('INSERT INTO example VALUES (?)', ('synthetic',))
            (root / 'local/compose.yml').write_text('synthetic deployment')
            (root / 'local/tcp-performance.conf').write_text('synthetic TCP tuning')
            (root / 'local/modules-load.conf').write_text('synthetic module name')
            (root / 'secrets/access.json').write_text(json.dumps({'synthetic': True}))
            (root / 'secrets/github-key').write_text('must never enter backup')
            (root / 'data/unrelated.log').write_text('must never enter backup')
            with patch.object(backup.subprocess, 'check_output', return_value='test-image'), \
                    patch.object(backup.time, 'sleep'):
                archive = backup.create_backup(root, 'initial')
                stamp = archive.stat().st_mtime_ns
                same = backup.create_backup(root, 'initial')
            self.assertEqual(archive, same)
            self.assertEqual(archive.stat().st_mtime_ns, stamp)
            self.assertEqual(stat.S_IMODE(archive.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(archive.parent.stat().st_mode), 0o700)
            checksum = archive.with_name(archive.name + '.sha256').read_text().split()[0]
            with archive.open('rb') as source:
                self.assertEqual(hashlib.file_digest(source, 'sha256').hexdigest(), checksum)
            with tarfile.open(archive, 'r:gz') as tar:
                self.assertEqual(set(tar.getnames()), {
                    'data/x-ui.db', 'manifest.json', 'local/compose.yml', 'secrets/access.json',
                    'local/tcp-performance.conf', 'local/modules-load.conf'})
                restored = root / 'state/restored.db'
                restored.write_bytes(tar.extractfile('data/x-ui.db').read())
            with sqlite3.connect(restored) as con:
                self.assertEqual(con.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(con.execute('SELECT value FROM example').fetchone()[0], 'synthetic')
            self.assertFalse((root / 'state/backup-in-progress').exists())

    def test_symlink_is_rejected_and_maintenance_marker_is_cleaned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder in ('data', 'state', 'local', 'secrets', 'backups'):
                (root / folder).mkdir()
            with sqlite3.connect(root / 'data/x-ui.db') as con:
                con.execute('CREATE TABLE example(value TEXT)')
            (root / 'local/compose.yml').symlink_to('/etc/passwd')
            with patch.object(backup.subprocess, 'check_output', return_value='test-image'), \
                    patch.object(backup.time, 'sleep'):
                with self.assertRaises(RuntimeError):
                    backup.create_backup(root, 'initial')
            self.assertFalse(list((root / 'backups').glob('*/panel-backup.tar.gz')))
            self.assertFalse((root / 'state/backup-in-progress').exists())


if __name__ == '__main__':
    unittest.main()
