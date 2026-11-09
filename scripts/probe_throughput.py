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
import statistics
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
    parser.add_argument('--transport', choices=('reality', 'hysteria2'), default='reality')
    parser.add_argument('--hy2-down-mbps', type=float)
    parser.add_argument('--expect-cc')
    parser.add_argument('--expect-queue')
    parser.add_argument('--seconds', type=int, default=12)
    parser.add_argument('--connections', type=int, default=1)
    parser.add_argument('--min-mbps', type=float, default=5)
    parser.add_argument('--latency-samples', type=int, default=0)
    parser.add_argument('--latency-only', action='store_true')
    parser.add_argument('--url', default='https://speed.cloudflare.com/__down?bytes=20000000')
    args = parser.parse_args()
    if args.latency_only and args.latency_samples == 0:
        args.latency_samples = 5
    if not 0 <= args.latency_samples <= 20:
        parser.error('Use 0 to 20 HTTPS response-time samples')
    if args.transport == 'hysteria2' and args.via_ssh:
        parser.error('The SSH TCP tunnel comparison only applies to REALITY')
    if args.hy2_down_mbps is not None and (args.transport != 'hysteria2' or args.hy2_down_mbps <= 0):
        parser.error('Positive bandwidth hints require Hysteria 2')
    source = '''import json,pathlib,urllib.request,yaml,subprocess
c=json.loads(pathlib.Path('/home/panel/secrets/access.json').read_text())
with urllib.request.urlopen(urllib.request.Request(c['devices']['macbook']['subscription_url'],headers={'User-Agent':'mihomo'}),timeout=15) as r:proxies=yaml.safe_load(r.read())['proxies']
p=next(p for p in proxies if p['type']==('hysteria2' if __TRANSPORT__ == 'hysteria2' else 'vless'))
p['name']='diagnostic'
cc=subprocess.check_output(['sysctl','-n','net.ipv4.tcp_congestion_control'],text=True).strip()
dev=json.loads(subprocess.check_output(['ip','-j','route','show','default'],text=True))[0]['dev']
qs=json.loads(subprocess.check_output(['tc','-j','qdisc','show','dev',dev],text=True))
queues=sorted(set(q['kind'] for q in qs if q.get('parent') or (q.get('root') and q['kind']!='mq')))
print(json.dumps({'proxy':p,'cc':cc,'queues':queues}))
'''
    source = source.replace('__TRANSPORT__', repr(args.transport))
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                             args.ssh_host, 'python3 -'], input=source, text=True,
                            capture_output=True, timeout=25, check=True)
    payload = json.loads(result.stdout)
    proxy = payload['proxy']
    if args.expect_cc and payload['cc'] != args.expect_cc:
        raise RuntimeError('Server congestion control does not match expected trial')
    if args.expect_queue and payload['queues'] != [args.expect_queue]:
        raise RuntimeError('Active server queues do not match expected trial')
    assert proxy['type'] == ('vless' if args.transport == 'reality' else 'hysteria2')
    if args.hy2_down_mbps is not None:
        proxy.update({'down': f'{args.hy2_down_mbps:g} Mbps', 'up': '10 Mbps'})
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
            label = ('hysteria2-brutal' if proxy.get('down') else 'hysteria2-bbr') if args.transport == 'hysteria2' else ('ssh-carried-reality' if args.via_ssh else 'direct-reality')

            if args.transport == 'hysteria2':
                check = subprocess.run(['curl', '--noproxy', '', '-x', f'http://127.0.0.1:{port}',
                    '-sS', '--connect-timeout', '5', '--max-time', '8', '-o', '/dev/null',
                    '-w', '%{http_code}', 'https://www.youtube.com/generate_204'],
                    capture_output=True, text=True, timeout=12)
                if check.returncode or check.stdout.strip() != '204':
                    print(json.dumps({'path': 'hysteria2', 'reachable': False,
                        'curl_exit': check.returncode, 'http': check.stdout.strip()}), flush=True)
                    return 1

            if args.latency_samples:
                timings = []
                for _ in range(args.latency_samples):
                    response = subprocess.run(['curl', '--noproxy', '', '-x', f'http://127.0.0.1:{port}',
                        '-sS', '--connect-timeout', '3', '--max-time', '5', '-o', '/dev/null',
                        '-w', '%{http_code} %{time_starttransfer}',
                        'https://www.youtube.com/generate_204'], capture_output=True, text=True, timeout=8)
                    fields = response.stdout.split()
                    if response.returncode == 0 and len(fields) == 2 and fields[0] == '204':
                        timings.append(float(fields[1]) * 1000)
                print(json.dumps({'path': label, 'measurement': 'HTTPS time to first byte, not ICMP RTT',
                    'successful': len(timings), 'attempted': args.latency_samples,
                    'median_ms': round(statistics.median(timings), 1) if timings else None,
                    'max_ms': round(max(timings), 1) if timings else None,
                    'stddev_ms': round(statistics.pstdev(timings), 1) if timings else None}), flush=True)
                if args.latency_only:
                    return 0 if len(timings) == args.latency_samples else 1

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
            valid_http = all(s['http'] == '200' for s in samples)
            passed = valid_http and mbps >= args.min_mbps
            print(json.dumps({'path': label,
                'server_cc': payload['cc'], 'server_queues': payload['queues'],
                'Mbps': round(mbps, 3) if valid_http else None,
                'valid_http': valid_http, 'rate_limited': any(s['http'] == '429' for s in samples),
                'minimum_Mbps': args.min_mbps,
                'pass': passed, 'samples': samples}, ensure_ascii=False), flush=True)
            stop(core)
            core = None
    finally:
        stop(core)
        stop(tunnel)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
