#!/usr/bin/env python3
"""Renew the IP certificate and record a sanitized result for the status page."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess

root = Path(os.environ.get('PANEL_ROOT', '/home/panel'))
runtime = json.loads((root / 'local/runtime.json').read_text())
try:
    result = subprocess.run([
        '/opt/panel-certbot/bin/certbot', 'renew', '--cert-name', 'panel-ip',
        '--quiet', '--no-random-sleep-on-renew',
        '--deploy-hook', str(root / 'local/deploy-hooks/reload-nginx.sh')],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=240)
    success = result.returncode == 0
except (OSError, subprocess.TimeoutExpired):
    success = False
state = root / 'state/renewal.json'
temp = state.with_suffix('.tmp')
temp.write_text(json.dumps({'ok': success,
                           'checked_at': dt.datetime.now(dt.timezone.utc).isoformat()}))
temp.chmod(0o600)
temp.replace(state)
raise SystemExit(0 if success else 1)
