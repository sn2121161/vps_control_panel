#!/usr/bin/env python3
"""Add negotiated HY2 bandwidth hints to native panel Clash subscriptions.

Loopback only. No subscription URLs, credentials, or response bodies are logged.
The panel remains the authority for authentication, device state and routing.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import yaml


def configure_profile(profile):
    if not isinstance(profile, dict) or not isinstance(profile.get('proxies'), list):
        raise ValueError('Not a Clash subscription')
    for proxy in profile['proxies']:
        if proxy.get('type') == 'hysteria2':
            proxy.update({'down': '25 Mbps', 'up': '10 Mbps', 'skip-cert-verify': False})
    return profile


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = urlsplit(self.path).path
        # Fixed upstream and a bounded subscription path: no arbitrary forwarding.
        if not re.fullmatch(r'/[a-f0-9]{24}/[A-Za-z0-9_-]{8,128}', path):
            self.send_error(404)
            return
        try:
            request = Request('http://127.0.0.1:2096' + path,
                              headers={'User-Agent': 'mihomo',
                                       'Host': os.environ['PANEL_PUBLIC_HOST'],
                                       'X-Forwarded-Proto': 'https'})
            with urlopen(request, timeout=15) as upstream:
                raw = upstream.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise ValueError('Subscription too large')
                profile = configure_profile(yaml.safe_load(raw))
                body = yaml.safe_dump(profile, allow_unicode=True, sort_keys=False).encode()
                headers = {name: upstream.headers[name] for name in (
                    'Subscription-Userinfo', 'Profile-Update-Interval') if upstream.headers[name]}
        except HTTPError as exc:
            self.send_error(404 if exc.code == 404 else 502)
            return
        except (URLError, TimeoutError, OSError, ValueError, yaml.YAMLError, TypeError, AttributeError):
            self.send_error(502)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/yaml; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 9101), Handler).serve_forever()
