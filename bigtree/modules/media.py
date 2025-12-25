from __future__ import annotations
import os
import time
from typing import Dict, List, Optional
from tinydb import TinyDB, Query

try:
    import bigtree
except Exception:
    bigtree = None

try:
    from bigtree.inc.logging import logger
except Exception:
    import logging
    logger = logging.getLogger("bigtree")

_MEDIA_DB_PATH: Optional[str] = None

def _now() -> float:
    return time.time()

def _get_base_dir() -> str:
    base = None
    try:
        if getattr(bigtree, "settings", None):
            base = bigtree.settings.get("BOT.DATA_DIR", None)
    except Exception:
        base = None
    if not base:
        base = os.getenv("BIGTREE__BOT__DATA_DIR") or os.getenv("BIGTREE_DATA_DIR")
    if not base:
        base = os.getenv("BIGTREE_WORKDIR") or os.path.join(os.getcwd(), ".bigtree")
    return base

def get_media_dir() -> str:
    base = _get_base_dir()
    path = os.path.join(base, "media")
    os.makedirs(path, exist_ok=True)
    return path

def _get_db_path() -> str:
    global _MEDIA_DB_PATH
    if _MEDIA_DB_PATH:
        return _MEDIA_DB_PATH
    _MEDIA_DB_PATH = os.path.join(get_media_dir(), "media.json")
    return _MEDIA_DB_PATH

def _db() -> TinyDB:
    return TinyDB(_get_db_path())

def list_media() -> List[Dict]:
    db = _db(); q = Query()
    rows = db.search(q._type == "media")
    rows.sort(key=lambda r: float(r.get("created_at") or 0), reverse=True)
    return rows

def get_media(filename: str) -> Optional[Dict]:
    if not filename:
        return None
    db = _db(); q = Query()
    return db.get((q._type == "media") & (q.filename == filename))

def add_media(filename: str, original_name: Optional[str] = None, artist_id: Optional[str] = None) -> Dict:
    db = _db(); q = Query()
    payload = {
        "_type": "media",
        "filename": filename,
        "original_name": original_name or "",
        "artist_id": artist_id or None,
        "created_at": _now(),
    }
    existing = get_media(filename)
    if existing:
        existing.update({
            "original_name": payload["original_name"] or existing.get("original_name", ""),
            "artist_id": payload["artist_id"],
        })
        db.update(existing, (q._type == "media") & (q.filename == filename))
        return existing
    db.insert(payload)
    return payload

def delete_media(filename: str) -> bool:
    if not filename:
        return False
    db = _db(); q = Query()
    removed = db.remove((q._type == "media") & (q.filename == filename))
    return bool(removed)
