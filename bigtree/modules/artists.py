from __future__ import annotations
import os
import re
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

_ARTIST_DB_PATH: Optional[str] = None

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
    path = os.path.join(base, "tarot")
    os.makedirs(path, exist_ok=True)
    return path

def _get_db_path() -> str:
    global _ARTIST_DB_PATH
    if _ARTIST_DB_PATH:
        return _ARTIST_DB_PATH
    base = _get_base_dir()
    _ARTIST_DB_PATH = os.path.join(base, "tarot_artists.json")
    return _ARTIST_DB_PATH

def _db() -> TinyDB:
    return TinyDB(_get_db_path())

def _slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "artist"

def list_artists() -> List[Dict]:
    db = _db(); q = Query()
    artists = db.search(q._type == "artist")
    artists.sort(key=lambda a: (a.get("name") or "", a.get("artist_id") or ""))
    return artists

def get_artist(artist_id: str) -> Optional[Dict]:
    if not artist_id:
        return None
    db = _db(); q = Query()
    return db.get((q._type == "artist") & (q.artist_id == artist_id))

def upsert_artist(artist_id: Optional[str], name: str, links: Optional[Dict[str, str]] = None) -> Dict:
    db = _db(); q = Query()
    name = (name or "").strip()
    if not name:
        raise ValueError("name required")
    if not artist_id:
        artist_id = _slugify(name)
    payload = {
        "_type": "artist",
        "artist_id": artist_id,
        "name": name,
        "links": {k: v for k, v in (links or {}).items() if v},
    }
    existing = get_artist(artist_id)
    if existing:
        db.update(payload, (q._type == "artist") & (q.artist_id == artist_id))
    else:
        db.insert(payload)
    return payload

def delete_artist(artist_id: str) -> bool:
    if not artist_id:
        return False
    db = _db(); q = Query()
    removed = db.remove((q._type == "artist") & (q.artist_id == artist_id))
    return bool(removed)
