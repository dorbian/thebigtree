from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROXY_PATH = ROOT / "bigtree" / "inc" / "proxy.py"


def _load_proxy_module():
    spec = importlib.util.spec_from_file_location("bigtree_proxy_contract", PROXY_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ProxyHeaderTests(unittest.TestCase):
    def setUp(self):
        self.proxy = _load_proxy_module()
        self.private = self.proxy.parse_trusted_proxy_networks("192.168.0.0/16,127.0.0.0/8")
        self.proxy.trusted_proxy_networks = lambda: self.private

    @staticmethod
    def request(remote, *, scheme="http", **headers):
        return SimpleNamespace(remote=remote, scheme=scheme, headers=headers)

    def test_forwarded_https_is_only_trusted_from_proxy_network(self):
        trusted = self.request("192.168.0.20", **{"X-Forwarded-Proto": "https"})
        stranger = self.request("203.0.113.20", **{"X-Forwarded-Proto": "https"})
        self.assertTrue(self.proxy.request_is_secure(trusted))
        self.assertFalse(self.proxy.request_is_secure(stranger))
        self.assertTrue(self.proxy.request_is_secure(self.request("203.0.113.20", scheme="https")))

    def test_client_ip_uses_nearest_untrusted_hop_not_spoofed_left_edge(self):
        req = self.request(
            "192.168.0.20",
            **{"X-Forwarded-For": "203.0.113.99, 198.51.100.44"},
        )
        # A client can supply the left-most value. A well-behaved Traefik
        # appends the actual source, so walking from the proxy backwards picks
        # the nearest untrusted address instead of trusting the spoofed edge.
        self.assertEqual("198.51.100.44", self.proxy.client_ip(req))

    def test_public_peer_cannot_override_audit_ip(self):
        req = self.request("198.51.100.44", **{"X-Forwarded-For": "127.0.0.1"})
        self.assertEqual("198.51.100.44", self.proxy.client_ip(req))

    def test_explicit_malformed_proxy_setting_fails_closed(self):
        networks = self.proxy.parse_trusted_proxy_networks("not-a-network")
        self.assertEqual((), networks)
        self.assertFalse(self.proxy.address_is_trusted("192.168.0.20", networks))


if __name__ == "__main__":
    unittest.main()
