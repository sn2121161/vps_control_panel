#!/usr/bin/env python3
"""Live throughput probe. Credentials stay in memory or a temporary private dir.

This diagnostic never edits the active Clash profile or production service.
Exit 1 means the chosen minimum throughput was not reached (not a unit test).
"""
import argparse
import concurrent.futures
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def ready(port, process):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError('Temporary process exited')
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError('Temporary listener not ready')


def stop(process):
    if process is None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ssh-host', default='joysol')
    parser.add_argument('--core', default='/Applications/Clash Verge.app/Contents/MacOS/verge-mihomo')
    parser.add_argument('--via-ssh', action='store_true')
    parser.add_argument('--seconds', type=int, default=12)
    parser.add_argument('--connections', type=int, default=1)
    parser.add_argument('--min-mbps', type=float, default=5)
    parser.add_argument('--url', default='https://speed.cloudflare.com/__down?bytes=20000000')
    args = parser.parse_args()
    source = '''import json,pathlib,urllib.request,yaml
c=json.loads(pathlib.Path('/home/panel/secrets/access.json').read_text())
with urllib.request.urlopen(urllib.request.Request(c['devices']['macbook']['subscription_url'],headers={'User-Agent':'mihomo'}),timeout=15) as r:p=yaml.safe_load(r.read())['proxies'][0]
p['name']='diagnostic';print(json.dumps(p))
'''
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                             args.ssh_host, 'python3 -'], input=source, text=True,
                            capture_output=True, timeout=25, check=True)
    proxy = json.loads(result.stdout)
    assert proxy['type'] == 'vless'
    tunnel = None
    core = None
    try:
        if args.via_ssh:
            forwarded = free_port()
            tunnel = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
                                       '-o', 'ConnectTimeout=10', '-N', '-L',
                                       f'127.0.0.1:{forwarded}:127.0.0.1:{proxy["port"]}', args.ssh_host],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ready(forwarded, tunnel)
            proxy['server'], proxy['port'] = '127.0.0.1', forwarded
        with tempfile.TemporaryDirectory(prefix='panel-diagnostic-', dir='/private/tmp') as td:
            cfg = Path(td) / 'config.json'
            port = free_port()
            cfg.write_text(json.dumps({'mixed-port': port, 'allow-lan': False,
                'bind-address': '127.0.0.1', 'mode': 'rule', 'log-level': 'silent',
                'ipv6': False, 'proxies': [proxy], 'proxy-groups': [{
                    'name': 'PROXY', 'type': 'select', 'proxies': ['diagnostic']}],
                'rules': ['MATCH,PROXY']}))
            cfg.chmod(0o600)
            core = subprocess.Popen([args.core,
                                     '-d', td, '-f', str(cfg)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ready(port, core)

            def download(_):
                cmd = ['curl', '--noproxy', '', '-x', f'http://127.0.0.1:{port}',
                       '-sS', '--connect-timeout', '8', '--max-time', str(args.seconds),
                       '-o', '/dev/null', '-w', '%{http_code} %{size_download} %{speed_download} %{time_total}', args.url]
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=args.seconds + 5)
                f = p.stdout.split()
                return {'exit': p.returncode, 'http': f[0] if f else None,
                        'bytes': int(float(f[1])) if len(f) == 4 else 0,
                        'Mbps': float(f[2]) * 8 / 1e6 if len(f) == 4 else 0,
                        'seconds': float(f[3]) if len(f) == 4 else 0}

            start = time.monotonic()
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.connections) as pool:
                samples = list(pool.map(download, range(args.connections)))
            duration = time.monotonic() - start
            mbps = sum(s['bytes'] for s in samples) * 8 / duration / 1e6
            passed = all(s['http'] == '200' for s in samples) and mbps >= args.min_mbps
            print(json.dumps({'path': 'ssh-carried-reality' if args.via_ssh else 'direct-reality',
                'Mbps': round(mbps, 3), 'minimum_Mbps': args.min_mbps,
                'pass': passed, 'samples': samples}, ensure_ascii=False), flush=True)
            stop(core)
            core = None
    finally:
        stop(core)
        stop(tunnel)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
