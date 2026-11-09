#!/usr/bin/env python3
"""Write a sanitized, read-only health view for the administrator page."""
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import time


def collect(root):
    runtime = json.loads((root / 'local' / 'runtime.json').read_text())
    alerts = []
    backup_file = root / 'state' / 'backup.json'
    backup = json.loads(backup_file.read_text()) if backup_file.exists() else None
    if not backup or not backup.get('ok'):
        alerts.append({'id': 'backup', 'text': '尚无成功备份，或最近一次备份失败。'})
    elif backup.get('generated_at'):
        age = time.time() - dt.datetime.fromisoformat(backup['generated_at']).timestamp()
        if age > 35 * 86400:
            alerts.append({'id': 'backup_stale', 'text': '最近成功备份已超过 35 天。'})
    expiry = None
    try:
        cert = ssl._ssl._test_decode_cert(runtime['certificate'])
        expiry = ssl.cert_time_to_seconds(cert['notAfter'])
        if expiry - time.time() < 48 * 3600:
            alerts.append({'id': 'certificate', 'text': 'HTTPS 证书剩余有效期不足 48 小时。'})
    except (OSError, ssl.SSLError, ValueError):
        alerts.append({'id': 'certificate', 'text': '无法检查 HTTPS 证书。'})
    renewal_file = root / 'state' / 'renewal.json'
    renewal = json.loads(renewal_file.read_text()) if renewal_file.exists() else None
    if renewal and not renewal.get('ok'):
        alerts.append({'id': 'renewal', 'text': '最近一次证书续期检查失败。'})
    try:
        running = subprocess.check_output(['docker', 'inspect', '--format', '{{.State.Running}}',
                                           'panel-3xui'], timeout=8, stderr=subprocess.DEVNULL).strip() == b'true'
    except (OSError, subprocess.SubprocessError):
        running = False
    ports = {}
    listeners = [('panel', int(runtime.get('panel_port', 2053))), ('subscription', 2096), ('proxy', 443)]
    if runtime.get('hysteria_port'):
        listeners.append(('clash_subscription', 9101))
    for name, port in listeners:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=2):
                ports[name] = True
        except OSError:
            ports[name] = False
    if runtime.get('hysteria_port'):
        try:
            result = subprocess.run(['ss', '-H', '-lun',
                f"sport = :{int(runtime['hysteria_port'])}"], capture_output=True, timeout=5)
            ports['hysteria_udp'] = result.returncode == 0 and bool(result.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            ports['hysteria_udp'] = False
    if not running or not all(ports.values()):
        alerts.append({'id': 'service', 'text': '面板、订阅或代理监听异常。端口健康不代表线路和平台可用。'})
    free = shutil.disk_usage(root).free
    if free < 2 * 1024**3:
        alerts.append({'id': 'disk', 'text': '服务器剩余磁盘不足 2GiB。'})
    return {'updated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'alerts': alerts,
            'backup': backup, 'certificate_expiry': expiry, 'renewal': renewal,
            'container_running': running, 'ports': ports, 'disk_free_bytes': free}


if __name__ == '__main__':
    root = Path(os.environ.get('PANEL_ROOT', '/home/panel'))
    output = Path('/var/lib/panel-monitor/status.json')
    result = collect(root)
    temp = output.with_suffix('.tmp')
    temp.write_text(json.dumps(result, ensure_ascii=False))
    temp.chmod(0o644)
    temp.replace(output)
