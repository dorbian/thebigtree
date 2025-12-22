from __future__ import annotations
import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

HONSE_BASE_URL = os.getenv("HONSE_BASE_URL", "https://public-beta.honse.farm").rstrip("/")
HONSE_REFRESH_SECONDS = int(os.getenv("HONSE_REFRESH_SECONDS", "300"))
HONSE_TIMEOUT_SECONDS = int(os.getenv("HONSE_TIMEOUT_SECONDS", "10"))
HONSE_DEBUG = os.getenv("HONSE_PRESENCE_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
HONSE_FEDERATION_ENTRY = os.getenv("HONSE_FEDERATION_ENTRY", "forest").strip().lower()

logger = logging.getLogger("bigtree")


def _entry_candidates(entry: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    for field in ("name", "id", "slug", "key", "server", "serverId", "hostname", "host", "domain"):
        val = entry.get(field)
        if isinstance(val, str) and val.strip():
            candidates.append(val.strip().lower())
    nested = entry.get("server")
    if isinstance(nested, dict):
        for field in ("name", "id", "slug", "key", "serverId", "hostname", "host", "domain"):
            val = nested.get(field)
            if isinstance(val, str) and val.strip():
                candidates.append(val.strip().lower())
    return candidates


def _matches_entry(entry: Dict[str, Any], entry_key: str, hosts: List[str]) -> bool:
    entry_key = (entry_key or "").strip().lower()
    if entry_key:
        for cand in _entry_candidates(entry):
            if cand == entry_key or entry_key in cand:
                return True
    hostname = str(entry.get("hostname") or "").lower().strip()
    if hostname and entry_key and entry_key in hostname:
        return True
    if "://" in hostname:
        parsed = urlparse(hostname)
        hostname = (parsed.hostname or "").lower().strip()
    if ":" in hostname:
        hostname = hostname.split(":", 1)[0].strip()
    if hostname and any(hostname == h or hostname.endswith(h) for h in hosts):
        return True
    return False


def _extract_count(entries: List[Dict[str, Any]], entry_key: str, hosts: List[str]) -> Optional[int]:
    hosts = [h.lower().strip() for h in hosts if h]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if not _matches_entry(entry, entry_key, hosts):
            continue
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
            if HONSE_DEBUG:
                logger.warning("[honse_presence] %s -> %s", url, resp.status_code)
            return None
        return resp.json()
    except Exception:
        if HONSE_DEBUG:
            logger.warning("[honse_presence] %s -> request failed", url)
        return None


def _extract_entries(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("servers", "data", "items", "result"):
            val = data.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
    return []


def get_online_count() -> Optional[int]:
    """
    Return online user count for the configured federation server.
    Falls back to None if data cannot be retrieved.
    """
    logger.warning("[honse_presence] fetching %s for entry '%s'", HONSE_BASE_URL, HONSE_FEDERATION_ENTRY)
    base_url = HONSE_BASE_URL
    if "://" not in base_url:
        base_url = f"https://{base_url}"
    parsed = urlparse(base_url)
    base_host = (parsed.hostname or HONSE_BASE_URL).lower().strip()
    hosts = [base_host]
    if base_host.startswith("server."):
        hosts.append(base_host.replace("server.", "", 1))
    details_url = f"{HONSE_BASE_URL}/api/federation/servers"
    data = _get_json(details_url)
    entries = _extract_entries(data)
    if entries:
        count = _extract_count(entries, HONSE_FEDERATION_ENTRY, hosts)
        if count is not None:
            logger.warning("[honse_presence] %s -> %s online", HONSE_FEDERATION_ENTRY, count)
            return count
        sample = []
        for entry in entries[:3]:
            sample.append(_entry_candidates(entry))
        logger.warning("[honse_presence] no match for entry '%s' (hosts=%s, sample=%s)", HONSE_FEDERATION_ENTRY, hosts, sample)
        return None
    if HONSE_DEBUG:
        logger.warning("[honse_presence] no entries for %s", base_host)
    return None
