#!/usr/bin/env python3
"""Create a local application snapshot. Never commit, upload, or send it."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
from zoneinfo import ZoneInfo


def atomic_json(path, obj):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False))
    tmp.chmod(0o600)
    tmp.replace(path)


def sha256(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def create_backup(root, kind='monthly'):
    now = dt.datetime.now(ZoneInfo('Asia/Shanghai'))
    period = now.strftime('%Y-%m-01' if kind == 'monthly' else '%Y-%m-%d')
    folder = root / 'backups' / period
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder.chmod(0o700)
    archive = folder / 'panel-backup.tar.gz'
    checksum = folder / 'panel-backup.tar.gz.sha256'
    if archive.exists():
        expected = checksum.read_text().split()[0]
        if sha256(archive) != expected:
            raise RuntimeError('existing_backup_checksum_failed')
        atomic_json(root / 'state' / 'backup.json', {
            'ok': True, 'checked_at': now.isoformat(), 'period': period,
            'generated_at': dt.datetime.fromtimestamp(archive.stat().st_mtime, ZoneInfo('Asia/Shanghai')).isoformat(),
            'size_bytes': archive.stat().st_size})
        return archive
    if shutil.disk_usage(root).free < 1024**3:
        raise RuntimeError('less_than_1GiB_free')
    marker = root / 'state' / 'backup-in-progress'
    marker.touch(mode=0o600)
    try:
        # Nginx blocks administrative requests while this marker exists.
        time.sleep(2)
        with tempfile.TemporaryDirectory(prefix='snapshot-', dir=root / 'state') as temp:
            staging = Path(temp)
            uri = (root / 'data' / 'x-ui.db').as_uri() + '?mode=ro'
            with sqlite3.connect(uri, uri=True, timeout=30) as source:
                with sqlite3.connect(staging / 'x-ui.db') as dest:
                    source.backup(dest)
                    if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise RuntimeError('sqlite_integrity_failed')
            versions = subprocess.check_output([
                'docker', 'inspect', '--format', '{{.Config.Image}}', 'panel-3xui'], text=True).strip()
            (staging / 'manifest.json').write_text(json.dumps({
                'generated_at': now.isoformat(), 'period': period, 'kind': kind,
                'image': versions, 'format': 1,
                'restore': 'Restore offline with the recorded image; review revoked credentials before reopening ports.'}, indent=2))
            tmp_archive = folder / '.panel-backup.tar.gz.tmp'
            try:
                with tarfile.open(tmp_archive, 'w:gz') as tar:
                    tar.add(staging / 'x-ui.db', arcname='data/x-ui.db')
                    tar.add(staging / 'manifest.json', arcname='manifest.json')
                    # Explicit allowlist: never recurse through the project root.
                    for relative in ('local/compose.yml', 'local/nginx-http.conf',
                                     'local/nginx-https.conf', 'local/runtime.json',
                                     'local/versions.json', 'local/deploy-hooks',
                                     'secrets/access.json', 'secrets/status.htpasswd'):
                        item = root / relative
                        if item.is_symlink():
                            raise RuntimeError('symlink_in_backup_allowlist')
                        if item.exists():
                            tar.add(item, arcname=relative)
                tmp_archive.chmod(0o600)
                digest = sha256(tmp_archive)
                tmp_archive.replace(archive)
                checksum.write_text(f'{digest}  {archive.name}\n')
                checksum.chmod(0o600)
            finally:
                tmp_archive.unlink(missing_ok=True)
        atomic_json(root / 'state' / 'backup.json', {
            'ok': True, 'generated_at': now.isoformat(), 'period': period,
            'size_bytes': archive.stat().st_size})
        return archive
    finally:
        marker.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kind', choices=('monthly', 'initial'), default='monthly')
    parser.add_argument('--retry', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    root = Path(os.environ.get('PANEL_ROOT', '/home/panel')).resolve()
    with (root / 'state' / 'backup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        status = root / 'state' / 'backup.json'
        if args.retry and (not status.exists() or json.loads(status.read_text()).get('ok')):
            return
        try:
            result = create_backup(root, args.kind)
            print(f'Local snapshot complete: {result.parent.name}')
        except Exception as exc:
            # Never persist exception text that might include credentials.
            atomic_json(status, {'ok': False, 'failed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                                 'error': type(exc).__name__})
            raise SystemExit('Local snapshot failed; check permissions, disk and database.')


if __name__ == '__main__':
    main()
