"""Helpers for safely consuming reverse-proxy headers.

BigTree is commonly reached through a Traefik instance on another host.  The
forwarded headers are useful for HTTPS cookies and audit logs, but they must
not be trusted from arbitrary Internet peers that can reach the aiohttp port.

By default only loopback, RFC1918 and IPv6 ULA/link-local peers are treated as
trusted reverse proxies.  Override the set with ``WEB.trusted_proxy_cidrs``
(or ``BIGTREE__WEB__trusted_proxy_cidrs``) when Traefik uses another network.
The setting accepts a comma-separated string or a JSON/list value.
"""
from __future__ import annotations

import ipaddress
from functools import lru_cache
from typing import Iterable, Sequence

_DEFAULT_TRUSTED = (
    "127.0.0.0/8",
    "::1/128",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "fc00::/7",
    "fe80::/10",
)


def _split_cidrs(raw) -> list[str]:
    if raw is None:
        return list(_DEFAULT_TRUSTED)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return list(_DEFAULT_TRUSTED)
        return [item.strip() for item in text.replace(";", ",").split(",") if item.strip()]
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return list(_DEFAULT_TRUSTED)


@lru_cache(maxsize=32)
def _parse_networks_cached(values: tuple[str, ...]):
    networks = []
    for value in values:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def parse_trusted_proxy_networks(raw=None):
    values = tuple(_split_cidrs(raw))
    networks = _parse_networks_cached(values)
    # A malformed explicit setting must fail closed rather than silently
    # reverting to broad private-network trust.
    return networks


def _settings_proxy_cidrs():
    try:
        import bigtree
        settings = getattr(bigtree, "settings", None)
        if settings:
            raw = settings.get("WEB.trusted_proxy_cidrs", None)
            if raw is None:
                raw = settings.get("WEB.trusted_proxies", None)
            return raw
    except Exception:
        pass
    return None


def trusted_proxy_networks():
    return parse_trusted_proxy_networks(_settings_proxy_cidrs())


def _address(value: str | None):
    text = str(value or "").strip()
    if not text:
        return None
    # aiohttp's remote normally contains only the address, but be tolerant of
    # bracketed IPv6 and the occasional host:port representation.
    if text.startswith("[") and "]" in text:
        text = text[1:text.index("]")]
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        if text.count(":") == 1:
            host, _sep, _port = text.partition(":")
            try:
                return ipaddress.ip_address(host)
            except ValueError:
                return None
        return None


def address_is_trusted(value: str | None, networks: Sequence | None = None) -> bool:
    address = _address(value)
    if address is None:
        return False
    networks = trusted_proxy_networks() if networks is None else networks
    for network in networks:
        try:
            if address.version == network.version and address in network:
                return True
        except Exception:
            continue
    return False


def request_from_trusted_proxy(req) -> bool:
    return address_is_trusted(getattr(req, "remote", None))


def request_is_secure(req) -> bool:
    """Return the externally visible HTTPS state without trusting strangers."""
    if str(getattr(req, "scheme", "")).lower() == "https":
        return True
    if not request_from_trusted_proxy(req):
        return False
    forwarded = (req.headers.get("X-Forwarded-Proto") or "").split(",", 1)[0].strip().lower()
    return forwarded == "https"


def client_ip(req) -> str:
    """Resolve the audit client IP through a trusted proxy chain.

    Walk X-Forwarded-For from the nearest hop backwards and return the first
    address that is not itself a trusted proxy.  This avoids accepting a fake
    left-most XFF value supplied by a client when Traefik appends the real
    source address.
    """
    peer = str(getattr(req, "remote", None) or "")
    networks = trusted_proxy_networks()
    if not address_is_trusted(peer, networks):
        return peer

    forwarded = req.headers.get("X-Forwarded-For") or ""
    addresses = []
    for raw in forwarded.split(","):
        addr = _address(raw.strip())
        if addr is not None:
            addresses.append(addr)
    for addr in reversed(addresses):
        if not address_is_trusted(str(addr), networks):
            return str(addr)
    if addresses:
        return str(addresses[0])
    return peer
