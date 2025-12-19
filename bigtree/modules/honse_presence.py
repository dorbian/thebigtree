from __future__ import annotations
import os
from typing import Any, Dict, List, Optional

import requests

HONSE_BASE_URL = os.getenv("HONSE_BASE_URL", "https://server.thebigtree.life").rstrip("/")
HONSE_REFRESH_SECONDS = int(os.getenv("HONSE_REFRESH_SECONDS", "300"))
HONSE_TIMEOUT_SECONDS = int(os.getenv("HONSE_TIMEOUT_SECONDS", "10"))


def _extract_count(entries: List[Dict[str, Any]], host: str) -> Optional[int]:
    host = host.lower().strip()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        hostname = str(entry.get("hostname") or "").lower()
        if not hostname:
            continue
        if hostname == host or hostname.endswith(host):
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
    Return online user count for thebigtree.life federation server.
    Falls back to None if data cannot be retrieved.
    """
    summary_url = f"{HONSE_BASE_URL}/api/federation/servers/summary"
    data = _get_json(summary_url)
    if isinstance(data, list):
        count = _extract_count(data, "thebigtree.life")
        if count is not None:
            return count
    details_url = f"{HONSE_BASE_URL}/api/federation/servers"
    data = _get_json(details_url)
    if isinstance(data, list):
        return _extract_count(data, "thebigtree.life")
    return None
