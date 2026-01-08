from __future__ import annotations
import json
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import bigtree
except Exception:
    bigtree = None

LINK_TTL_SECONDS = 6 * 60 * 60


def _settings_get(section: str, key: str, default=None):
    try:
        if hasattr(bigtree, "settings") and bigtree.settings:
            sec = bigtree.settings.section(section)
            if isinstance(sec, dict):
                return sec.get(key, default)
            return bigtree.settings.get(f"{section}.{key}", default)
    except Exception:
        pass
    try:
        cfg = getattr(getattr(bigtree, "config", None), "config", None) or {}
        return cfg.get(section, {}).get(key, default)
    except Exception:
        pass
    return default


def _links_path() -> Path:
    base = _settings_get("BOT", "DATA_DIR", None) or getattr(bigtree, "datadir", ".")
    return Path(base) / "temp_links.json"


def _load_json(p: Path, default):
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return default


def _save_json(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")


def _purge_expired(links: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    now = int(time.time())
    kept = []
    for link in links:
        expires = int(link.get("expires_at") or 0)
        used = int(link.get("used_count") or 0)
        max_uses = int(link.get("max_uses") or 1)
        if expires > now and used < max_uses:
            kept.append(link)
    return kept


def load_links() -> List[Dict[str, Any]]:
    data = _load_json(_links_path(), {"links": []})
    links = data.get("links") if isinstance(data, dict) else []
    links = _purge_expired(links if isinstance(links, list) else [])
    return links


def save_links(links: List[Dict[str, Any]]) -> None:
    links = _purge_expired(links)
    _save_json(_links_path(), {"links": links})


def issue_link(
    scopes: List[str],
    ttl_seconds: int = LINK_TTL_SECONDS,
    role_ids: Optional[List[str]] = None,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    token = secrets.token_urlsafe(24)
    now = int(time.time())
    doc = {
        "token": token,
        "scopes": scopes or [],
        "role_ids": role_ids or [],
        "created_at": now,
        "expires_at": now + int(ttl_seconds),
        "max_uses": 1,
        "used_count": 0,
    }
    if created_by:
        doc["created_by"] = str(created_by)
    links = load_links()
    links.append(doc)
    save_links(links)
    return doc


def consume_link(token: str, user_name: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    links = load_links()
    updated: Optional[Dict[str, Any]] = None
    for link in links:
        if link.get("token") != token:
            continue
        updated = link
        break
    if not updated:
        return None
    updated["used_count"] = int(updated.get("used_count") or 0) + 1
    updated["used_at"] = int(time.time())
    updated["used_by"] = user_name
    save_links(links)
    return updated
