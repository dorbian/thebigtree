from __future__ import annotations
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

HONSE_BASE_URL = os.getenv("HONSE_BASE_URL", "https://server.thebigtree.life").rstrip("/")
HONSE_REFRESH_SECONDS = int(os.getenv("HONSE_REFRESH_SECONDS", "300"))
HONSE_TIMEOUT_SECONDS = int(os.getenv("HONSE_TIMEOUT_SECONDS", "10"))


def _extract_count(entries: List[Dict[str, Any]], hosts: List[str]) -> Optional[int]:
    hosts = [h.lower().strip() for h in hosts if h]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        hostname = str(entry.get("hostname") or "").lower().strip()
        if not hostname:
            continue
        if "://" in hostname:
            parsed = urlparse(hostname)
            hostname = (parsed.hostname or "").lower().strip()
        if ":" in hostname:
            hostname = hostname.split(":", 1)[0].strip()
        if not hostname:
            continue
        if any(hostname == h or hostname.endswith(h) for h in hosts):
            raw = entry.get("usersOnlineCount")
            try:
                return int(raw)
            except Exception:
                return None
    return None


def _get_json(url: str) -> Optional[Any]:
    try:
        resp = requests.get(url, timeout=HONSE_TIMEOUT_SECONDS)
        if not resp.ok:
            return None
        return resp.json()
    except Exception:
        return None


def get_online_count() -> Optional[int]:
    """
    Return online user count for the configured federation server.
    Falls back to None if data cannot be retrieved.
    """
    base_url = HONSE_BASE_URL
    if "://" not in base_url:
        base_url = f"https://{base_url}"
    parsed = urlparse(base_url)
    base_host = (parsed.hostname or HONSE_BASE_URL).lower().strip()
    hosts = [base_host]
    if base_host.startswith("server."):
        hosts.append(base_host.replace("server.", "", 1))
    summary_url = f"{HONSE_BASE_URL}/api/federation/servers/summary"
    data = _get_json(summary_url)
    if isinstance(data, list):
        count = _extract_count(data, hosts)
        if count is not None:
            return count
    details_url = f"{HONSE_BASE_URL}/api/federation/servers"
    data = _get_json(details_url)
    if isinstance(data, list):
        return _extract_count(data, hosts)
    return None
