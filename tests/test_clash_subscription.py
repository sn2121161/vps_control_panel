import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'clash_subscription', Path(__file__).resolve().parents[1] / 'scripts/clash_subscription.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SubscriptionTests(unittest.TestCase):
    def test_device_identity_routing_and_backup_node_survive(self):
        reality = {'name': 'backup', 'type': 'vless', 'uuid': 'test-device'}
        profile = {'proxies': [reality.copy(), {'name': 'primary', 'type': 'hysteria2',
                    'password': 'device-auth', 'skip-cert-verify': True}],
                   'rules': ['GEOIP,CN,DIRECT', 'MATCH,PROXY'],
                   'proxy-groups': [{'name': 'PROXY', 'type': 'select',
                                     'proxies': ['primary', 'backup']}]}
        result = module.configure_profile(profile)
        self.assertEqual(result['proxies'][0], reality)
        self.assertEqual(result['proxies'][1]['password'], 'device-auth')
        self.assertEqual(result['proxies'][1]['down'], '25 Mbps')
        self.assertFalse(result['proxies'][1]['skip-cert-verify'])
        self.assertEqual(result['rules'], ['GEOIP,CN,DIRECT', 'MATCH,PROXY'])
        self.assertEqual(result['proxy-groups'][0]['proxies'], ['primary', 'backup'])

    def test_rejects_raw_or_error_subscription(self):
        for value in ('base64-node-list', None, {'error': 'denied'}):
            with self.assertRaises(ValueError):
                module.configure_profile(value)
