from __future__ import annotations
import calendar as _calendar
import os
import time
from typing import Dict, List, Optional
from tinydb import TinyDB, Query

try:
    import bigtree
except Exception:
    bigtree = None

_CALENDAR_DB_PATH: Optional[str] = None

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
    os.makedirs(base, exist_ok=True)
    return base

def _db_path() -> str:
    global _CALENDAR_DB_PATH
    if _CALENDAR_DB_PATH:
        return _CALENDAR_DB_PATH
    _CALENDAR_DB_PATH = os.path.join(_get_base_dir(), "gallery_calendar.json")
    return _CALENDAR_DB_PATH

def _db() -> TinyDB:
    return TinyDB(_db_path())

def list_calendar() -> List[Dict]:
    db = _db(); q = Query()
    rows = db.search(q._type == "month")
    by_month = {int(r.get("month") or 0): r for r in rows}
    out: List[Dict] = []
    for month in range(1, 13):
        entry = by_month.get(month) or {}
        out.append({
            "month": month,
            "month_name": _calendar.month_name[month],
            "image": entry.get("image"),
            "title": entry.get("title") or "",
            "artist_id": entry.get("artist_id"),
            "updated_at": entry.get("updated_at") or 0,
        })
    return out

def set_month(month: int, image: str, title: str = "", artist_id: Optional[str] = None) -> Dict:
    month = int(month)
    if month < 1 or month > 12:
        raise ValueError("month must be 1-12")
    db = _db(); q = Query()
    payload = {
        "_type": "month",
        "month": month,
        "image": image,
        "title": title or "",
        "artist_id": artist_id or None,
        "updated_at": _now(),
    }
    existing = db.get((q._type == "month") & (q.month == month))
    if existing:
        db.update(payload, (q._type == "month") & (q.month == month))
    else:
        db.insert(payload)
    return payload

def clear_month(month: int) -> bool:
    month = int(month)
    if month < 1 or month > 12:
        return False
    db = _db(); q = Query()
    removed = db.remove((q._type == "month") & (q.month == month))
    return bool(removed)
