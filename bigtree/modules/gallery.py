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

try:
    from bigtree.inc.database import get_database
except Exception:
    get_database = None  # type: ignore

_CALENDAR_DB_PATH: Optional[str] = None
_REACTIONS_DB_PATH: Optional[str] = None
_HIDDEN_DB_PATH: Optional[str] = None
_SETTINGS_DB_PATH: Optional[str] = None

_REACTION_TYPES = ("appreciation", "inspired", "gratitude", "craft")


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


# -------- legacy TinyDB paths (fallback only) --------
def _db_path() -> str:
    global _CALENDAR_DB_PATH
    if _CALENDAR_DB_PATH:
        return _CALENDAR_DB_PATH
    _CALENDAR_DB_PATH = os.path.join(_get_base_dir(), "gallery_calendar.json")
    return _CALENDAR_DB_PATH


def _db() -> TinyDB:
    return TinyDB(_db_path())


def _reactions_path() -> str:
    global _REACTIONS_DB_PATH
    if _REACTIONS_DB_PATH:
        return _REACTIONS_DB_PATH
    _REACTIONS_DB_PATH = os.path.join(_get_base_dir(), "gallery_reactions.json")
    return _REACTIONS_DB_PATH


def _reactions_db() -> TinyDB:
    return TinyDB(_reactions_path())


def _hidden_path() -> str:
    global _HIDDEN_DB_PATH
    if _HIDDEN_DB_PATH:
        return _HIDDEN_DB_PATH
    _HIDDEN_DB_PATH = os.path.join(_get_base_dir(), "gallery_hidden.json")
    return _HIDDEN_DB_PATH


def _hidden_db() -> TinyDB:
    return TinyDB(_hidden_path())


def _settings_path() -> str:
    global _SETTINGS_DB_PATH
    if _SETTINGS_DB_PATH:
        return _SETTINGS_DB_PATH
    _SETTINGS_DB_PATH = os.path.join(_get_base_dir(), "gallery_settings.json")
    return _SETTINGS_DB_PATH


def _settings_db() -> TinyDB:
    return TinyDB(_settings_path())


def reaction_types() -> List[str]:
    return list(_REACTION_TYPES)


def _normalize_counts(counts: Dict[str, int] | None) -> Dict[str, int]:
    if not isinstance(counts, dict):
        counts = {}
    return {key: int(counts.get(key) or 0) for key in _REACTION_TYPES}


def _db_available() -> bool:
    if not get_database:
        return False
    try:
        db = get_database()
        db.initialize()
        return True
    except Exception:
        return False


# ---------------- reactions ----------------
def get_reactions(item_id: str) -> Dict[str, int]:
    if not item_id:
        return {}
    if _db_available():
        try:
            db = get_database()
            out = db.get_gallery_reactions_bulk([item_id]).get(item_id) or {}
            return _normalize_counts(out)
        except Exception:
            pass
    # fallback
    db = _reactions_db()
    q = Query()
    row = db.get((q._type == "reaction") & (q.item_id == item_id))
    counts = row.get("counts") if row else None
    return _normalize_counts(counts)


def list_reactions(item_ids: List[str]) -> Dict[str, Dict[str, int]]:
    return list_reactions_bulk(item_ids)


def list_reactions_bulk(item_ids: List[str]) -> Dict[str, Dict[str, int]]:
    if not item_ids:
        return {}
    if _db_available():
        try:
            db = get_database()
            rows = db.get_gallery_reactions_bulk(item_ids) or {}
            return {k: _normalize_counts(v) for k, v in rows.items()}
        except Exception:
            pass
    # fallback
    id_set = {item_id for item_id in item_ids if item_id}
    if not id_set:
        return {}
    db = _reactions_db()
    q = Query()
    rows = db.search(q._type == "reaction")
    out: Dict[str, Dict[str, int]] = {}
    for row in rows:
        iid = row.get("item_id")
        if iid in id_set:
            out[iid] = _normalize_counts(row.get("counts"))
    for iid in id_set:
        out.setdefault(iid, _normalize_counts({}))
    return out


def increment_reaction(item_id: str, reaction_id: str, amount: int = 1) -> Dict[str, int]:
    if not item_id:
        raise ValueError("item_id required")
    reaction_id = str(reaction_id or "").strip().lower()
    if reaction_id not in _REACTION_TYPES:
        raise ValueError("invalid reaction")
    if _db_available():
        try:
            db = get_database()
            counts = db.increment_gallery_reaction(item_id, reaction_id, int(amount or 1)) or {}
            return _normalize_counts(counts)
        except Exception:
            pass
    # fallback
    db = _reactions_db()
    q = Query()
    row = db.get((q._type == "reaction") & (q.item_id == item_id))
    counts = row.get("counts") if row else {}
    if not isinstance(counts, dict):
        counts = {}
    counts[reaction_id] = int(counts.get(reaction_id) or 0) + max(1, int(amount or 1))
    payload = {"_type": "reaction", "item_id": item_id, "counts": counts, "updated_at": _now()}
    if row:
        db.update(payload, (q._type == "reaction") & (q.item_id == item_id))
    else:
        db.insert(payload)
    return get_reactions(item_id)


# ---------------- hidden ----------------
def is_hidden(item_id: str) -> bool:
    if not item_id:
        return False
    if _db_available():
        try:
            db = get_database()
            return bool(db.is_gallery_hidden(item_id))
        except Exception:
            pass
    db = _hidden_db()
    q = Query()
    row = db.get((q._type == "hidden") & (q.item_id == item_id))
    return bool(row and row.get("hidden") is True)


def get_hidden_set() -> set[str]:
    if _db_available():
        try:
            db = get_database()
            return set(db.get_gallery_hidden_set() or set())
        except Exception:
            pass
    db = _hidden_db()
    q = Query()
    rows = db.search((q._type == "hidden") & (q.hidden == True))
    return {str(row.get("item_id")) for row in rows if row.get("item_id")}


def set_hidden(item_id: str, hidden: bool) -> Dict[str, int | str | bool]:
    if not item_id:
        raise ValueError("item_id required")
    if _db_available():
        try:
            db = get_database()
            db.set_gallery_hidden(item_id, bool(hidden))
            return {"_type": "hidden", "item_id": item_id, "hidden": bool(hidden)}
        except Exception:
            pass
    db = _hidden_db()
    q = Query()
    payload = {"_type": "hidden", "item_id": item_id, "hidden": bool(hidden), "updated_at": _now()}
    existing = db.get((q._type == "hidden") & (q.item_id == item_id))
    if existing:
        db.update(payload, (q._type == "hidden") & (q.item_id == item_id))
    else:
        db.insert(payload)
    return payload


# ---------------- settings ----------------
def get_upload_channel_id() -> Optional[int]:
    if _db_available():
        try:
            db = get_database()
            s = db.get_gallery_settings() or {}
            val = s.get("upload_channel_id")
            return int(val) if val else None
        except Exception:
            pass
    db = _settings_db()
    q = Query()
    row = db.get(q._type == "settings")
    if not row:
        return None
    try:
        value = int(row.get("upload_channel_id") or 0)
    except Exception:
        value = 0
    return value or None


def set_upload_channel_id(channel_id: Optional[int]) -> Dict:
    if _db_available():
        try:
            db = get_database()
            s = db.get_gallery_settings() or {}
            s["upload_channel_id"] = int(channel_id) if channel_id else None
            db.update_gallery_settings(s)
            return {"upload_channel_id": s.get("upload_channel_id")}
        except Exception:
            pass
    db = _settings_db()
    q = Query()
    payload = {"_type": "settings", "upload_channel_id": int(channel_id) if channel_id else None, "updated_at": _now()}
    existing = db.get(q._type == "settings")
    if existing:
        db.update(payload, q._type == "settings")
    else:
        db.insert(payload)
    return payload


def get_hidden_decks() -> List[str]:
    if _db_available():
        try:
            db = get_database()
            s = db.get_gallery_settings() or {}
            decks = s.get("hidden_decks") or []
            if not isinstance(decks, list):
                decks = []
            return [str(d).strip() for d in decks if str(d).strip()]
        except Exception:
            pass
    db = _settings_db()
    q = Query()
    row = db.get(q._type == "settings") or {}
    decks = row.get("hidden_decks") or []
    if not isinstance(decks, list):
        decks = []
    return [str(deck).strip() for deck in decks if str(deck).strip()]


def set_hidden_decks(deck_ids: List[str]) -> Dict:
    decks = [str(deck).strip() for deck in (deck_ids or []) if str(deck).strip()]
    if _db_available():
        try:
            db = get_database()
            s = db.get_gallery_settings() or {}
            s["hidden_decks"] = decks
            db.update_gallery_settings(s)
            return {"hidden_decks": decks}
        except Exception:
            pass
    db = _settings_db()
    q = Query()
    payload = {"_type": "settings", "hidden_decks": decks, "updated_at": _now()}
    existing = db.get(q._type == "settings")
    if existing:
        db.update(payload, q._type == "settings")
    else:
        db.insert(payload)
    return payload


# ---------------- calendar ----------------
def list_calendar() -> List[Dict]:
    if _db_available():
        try:
            db = get_database()
            rows = {int(r.get("month")): r for r in (db.list_gallery_calendar() or []) if r.get("month")}
        except Exception:
            rows = {}
    else:
        rows = {}
    if not rows:
        # fallback to tinydb
        db = _db()
        q = Query()
        trows = db.search(q._type == "month")
        rows = {int(r.get("month") or 0): r for r in trows if r.get("month")}
    out: List[Dict] = []
    for month in range(1, 13):
        entry = rows.get(month) or {}
        out.append(
            {
                "month": month,
                "month_name": _calendar.month_name[month],
                "image": entry.get("image"),
                "title": entry.get("title") or "",
                "artist_id": entry.get("artist_id"),
                "updated_at": entry.get("updated_at") or 0,
            }
        )
    return out


def set_month(month: int, image: str, title: str = "", artist_id: Optional[str] = None) -> Dict:
    month = int(month)
    if month < 1 or month > 12:
        raise ValueError("month must be 1-12")
    if _db_available():
        try:
            db = get_database()
            db.upsert_gallery_month(month, image, title or "", artist_id)
            return {"month": month, "image": image, "title": title or "", "artist_id": artist_id}
        except Exception:
            pass
    db = _db()
    q = Query()
    payload = {"_type": "month", "month": month, "image": image, "title": title or "", "artist_id": artist_id, "updated_at": _now()}
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
    if _db_available():
        try:
            db = get_database()
            db.clear_gallery_month(month)
            return True
        except Exception:
            pass
    db = _db()
    q = Query()
    removed = db.remove((q._type == "month") & (q.month == month))
    return bool(removed)
