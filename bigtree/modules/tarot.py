# bigtree/modules/tarot.py
# Tarot sessions + decks with event stream support

from __future__ import annotations
import os
import secrets
import time
import random
from typing import Any, Dict, List, Optional, Callable, Tuple
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

_LEGACY_DB_PATH: Optional[str] = None
_DECK_DB_PATH: Optional[str] = None
_SESSION_DB_PATH: Optional[str] = None
_MIGRATED: Optional[bool] = None

def _now() -> float:
    return time.time()

def _get_base_dir() -> str:
    # Prefer legacy config path if present
    try:
        cfg = getattr(getattr(bigtree, "config", None), "config", None) or {}
        tarot_db = cfg.get("BOT", {}).get("tarot_db")
        if tarot_db:
            return os.path.dirname(tarot_db)
    except Exception:
        pass

    # New default location
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

def _get_legacy_db_path() -> str:
    global _LEGACY_DB_PATH
    if _LEGACY_DB_PATH:
        return _LEGACY_DB_PATH
    base = _get_base_dir()
    path = os.path.join(base, "tarot.json")
    _LEGACY_DB_PATH = path
    return _LEGACY_DB_PATH

def _get_deck_db_path() -> str:
    global _DECK_DB_PATH
    if _DECK_DB_PATH:
        return _DECK_DB_PATH
    base = _get_base_dir()
    path = os.path.join(base, "tarot_decks.json")
    _DECK_DB_PATH = path
    return _DECK_DB_PATH

def _get_session_db_path() -> str:
    global _SESSION_DB_PATH
    if _SESSION_DB_PATH:
        return _SESSION_DB_PATH
    base = _get_base_dir()
    path = os.path.join(base, "tarot_sessions.json")
    _SESSION_DB_PATH = path
    return _SESSION_DB_PATH

def _migrate_if_needed() -> None:
    global _MIGRATED
    if _MIGRATED is True:
        return
    base = _get_base_dir()
    marker = os.path.join(base, ".tarot_migrated")
    legacy_path = _get_legacy_db_path()
    deck_db = TinyDB(_get_deck_db_path())
    session_db = TinyDB(_get_session_db_path())
    if os.path.exists(marker):
        if deck_db.all() or session_db.all():
            _MIGRATED = True
            return
        if not os.path.exists(legacy_path):
            _MIGRATED = True
            return
        legacy_db = TinyDB(legacy_path)
        if not legacy_db.all():
            _MIGRATED = True
            return
        # marker exists but split dbs are empty; re-migrate
    else:
        if not os.path.exists(legacy_path):
            _MIGRATED = True
            return
        if deck_db.all() or session_db.all():
            _MIGRATED = True
            return
    legacy_db = TinyDB(legacy_path)
    moved = 0
    for entry in legacy_db.all():
        etype = entry.get("_type")
        if etype in ("deck", "card"):
            deck_db.insert(entry)
            moved += 1
        elif etype == "session":
            session_db.insert(entry)
            moved += 1
    try:
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write(f"migrated={moved}\n")
    except Exception:
        pass
    logger.info(f"[tarot] migrated {moved} entries to split dbs")
    _MIGRATED = True

def _db_decks() -> TinyDB:
    _migrate_if_needed()
    return TinyDB(_get_deck_db_path())

def _db_sessions() -> TinyDB:
    _migrate_if_needed()
    return TinyDB(_get_session_db_path())

def _new_id() -> str:
    return secrets.token_urlsafe(10)

def _new_code() -> str:
    return secrets.token_urlsafe(5).replace("-", "").replace("_", "")[:8]

SPREADS = {
    "single": [
        {"id": "root", "label": "Root", "prompt": "What holds"},
    ],
    "tree": [
        {"id": "root", "label": "Root", "prompt": "What holds"},
        {"id": "trunk", "label": "Trunk", "prompt": "What grows"},
        {"id": "canopy", "label": "Canopy", "prompt": "What reveals"},
    ],
    "cross": [
        {"id": "past", "label": "Past", "prompt": "What shaped this"},
        {"id": "present", "label": "Present", "prompt": "What surrounds you"},
        {"id": "future", "label": "Future", "prompt": "What may come"},
    ],
}

_SPREADS_CACHE: Optional[List[Dict[str, Any]]] = None
_SPREADS_WARNED = False

def _read_json(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return _json.loads(fh.read())
    except Exception:
        return None

def _normalize_spreads(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, dict):
        raw = raw.get("spreads")
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        sid = str(entry.get("id") or "").strip()
        if not sid:
            continue
        label = str(entry.get("label") or sid.title()).strip()
        positions = []
        for pos in entry.get("positions") or []:
            if not isinstance(pos, dict):
                continue
            pid = str(pos.get("id") or "").strip()
            if not pid:
                continue
            positions.append({
                "id": pid,
                "label": str(pos.get("label") or pid.title()).strip(),
                "prompt": str(pos.get("prompt") or "").strip(),
            })
        if not positions:
            continue
        out.append({
            "id": sid,
            "label": label,
            "positions": positions,
        })
    return out

def _load_spreads() -> List[Dict[str, Any]]:
    global _SPREADS_CACHE, _SPREADS_WARNED
    if _SPREADS_CACHE is not None:
        return _SPREADS_CACHE
    candidates: List[str] = []
    env_path = os.getenv("BIGTREE_TAROT_SPREADS")
    if env_path:
        candidates.append(env_path)
    base = _get_base_dir()
    candidates.append(os.path.join(base, "spreads.json"))
    try:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        candidates.append(os.path.join(repo_root, "tarot_spreads.json"))
        candidates.append(os.path.join(repo_root, "defaults", "tarot_spreads.json"))
    except Exception:
        pass
    for path in candidates:
        if os.path.exists(path):
            data = _read_json(path)
            spreads = _normalize_spreads(data)
            if spreads:
                _SPREADS_CACHE = spreads
                return _SPREADS_CACHE
    if not _SPREADS_WARNED:
        _SPREADS_WARNED = True
        logger.warning("[tarot] spreads file not found; checked: %s", ", ".join(candidates))
    # fallback to defaults
    fallback = []
    for sid, positions in SPREADS.items():
        fallback.append({
            "id": sid,
            "label": sid.title(),
            "positions": positions,
        })
    _SPREADS_CACHE = fallback
    return _SPREADS_CACHE

def list_spreads() -> List[Dict[str, Any]]:
    return list(_load_spreads())

def _get_spread(spread_id: str) -> List[Dict[str, Any]]:
    spread_id = (spread_id or "").strip().lower()
    for spread in _load_spreads():
        if spread.get("id") == spread_id:
            return spread.get("positions") or SPREADS["single"]
    return SPREADS["single"]

# -------- Decks --------
def create_deck(deck_id: str, name: Optional[str] = None) -> Dict[str, Any]:
    deck_id = (deck_id or "").strip() or "elf-classic"
    db = _db_decks(); q = Query()
    existing = db.get((q._type == "deck") & (q.deck_id == deck_id))
    if existing:
        return existing
    deck = {
        "_type": "deck",
        "deck_id": deck_id,
        "name": (name or deck_id),
        "back_image": None,
        "created_at": _now(),
    }
    db.insert(deck)
    return deck

def list_decks() -> List[Dict[str, Any]]:
    db = _db_decks(); q = Query()
    decks = db.search(q._type == "deck")
    if not decks:
        create_deck("elf-classic")
        decks = db.search(q._type == "deck")
    return decks

def get_deck(deck_id: str) -> Optional[Dict[str, Any]]:
    db = _db_decks(); q = Query()
    return db.get((q._type == "deck") & (q.deck_id == deck_id))

def set_deck_back(deck_id: str, back_image: str, artist_id: Optional[str] = None) -> bool:
    db = _db_decks(); q = Query()
    deck = get_deck(deck_id)
    if not deck:
        create_deck(deck_id)
    deck = get_deck(deck_id)
    if not deck:
        return False
    deck["back_image"] = back_image
    if artist_id is not None:
        deck["back_artist_id"] = artist_id or None
    db.update(deck, (q._type == "deck") & (q.deck_id == deck_id))
    return True

def add_or_update_card(deck_id: str, card: Dict[str, Any]) -> Dict[str, Any]:
    deck_id = (deck_id or "").strip() or "elf-classic"
    create_deck(deck_id)
    db = _db_decks(); q = Query()
    card_id = (card.get("id") or card.get("card_id") or "").strip()
    name = (card.get("name") or card.get("title") or "").strip()
    if not name:
        raise ValueError("name required")
    if not card_id:
        card_id = name.lower().replace(" ", "_")[:48]
    existing = db.get((q._type == "card") & (q.deck_id == deck_id) & (q.card_id == card_id))
    if "artist_id" in card:
        artist_id = (card.get("artist_id") or "").strip() or None
    else:
        artist_id = (existing.get("artist_id") or "").strip() or None if existing else None
    artist_links = card.get("artist_links") if isinstance(card.get("artist_links"), dict) else {}
    if not artist_links and existing and isinstance(existing.get("artist_links"), dict):
        artist_links = existing.get("artist_links") or {}
    if artist_id:
        try:
            from bigtree.modules import artists
            artist = artists.get_artist(artist_id)
            if artist and isinstance(artist.get("links"), dict):
                artist_links = artist.get("links") or {}
        except Exception:
            pass
    if not artist_links:
        artist_links = {
            "instagram": card.get("artist_instagram"),
            "bluesky": card.get("artist_bluesky"),
            "x": card.get("artist_x") or card.get("artist_twitter"),
            "artstation": card.get("artist_artstation"),
            "website": card.get("artist_website"),
        }
    cleaned_links = {}
    for key, val in artist_links.items():
        if not val:
            continue
        cleaned_links[str(key)] = str(val).strip()
    payload = {
        "_type": "card",
        "deck_id": deck_id,
        "card_id": card_id,
        "name": name,
        "house": (card.get("house") or "").strip() or None,
        "upright": (card.get("upright") or card.get("meaning") or "").strip(),
        "reversed": (card.get("reversed") or "").strip(),
        "tags": card.get("tags") if isinstance(card.get("tags"), list) else [],
        "image": (card.get("image") or card.get("image_url") or "").strip(),
        "artist_id": artist_id,
        "artist_links": cleaned_links,
        "updated_at": _now(),
    }
    if existing:
        db.update(payload, (q._type == "card") & (q.deck_id == deck_id) & (q.card_id == card_id))
    else:
        payload["created_at"] = _now()
        db.insert(payload)
    return payload

def list_cards(deck_id: str) -> List[Dict[str, Any]]:
    deck_id = (deck_id or "").strip() or "elf-classic"
    db = _db_decks(); q = Query()
    return db.search((q._type == "card") & (q.deck_id == deck_id))

def clear_image_references(image_url: str) -> int:
    """Remove image/back references pointing at the given URL (ignores query)."""
    target = (image_url or "").split("?", 1)[0]
    if not target:
        return 0
    db = _db_decks(); q = Query()
    updated = 0
    for card in db.search(q._type == "card"):
        img = (card.get("image") or "").split("?", 1)[0]
        if img and img == target:
            card["image"] = ""
            db.update(card, (q._type == "card") & (q.deck_id == card.get("deck_id")) & (q.card_id == card.get("card_id")))
            updated += 1
    for deck in db.search(q._type == "deck"):
        back = (deck.get("back_image") or "").split("?", 1)[0]
        if back and back == target:
            deck["back_image"] = None
            db.update(deck, (q._type == "deck") & (q.deck_id == deck.get("deck_id")))
            updated += 1
    return updated

def get_card(deck_id: str, card_id: str) -> Optional[Dict[str, Any]]:
    db = _db_decks(); q = Query()
    return db.get((q._type == "card") & (q.deck_id == deck_id) & (q.card_id == card_id))

def set_card_image(card_id: str, image: str, artist_id: Optional[str] = None) -> bool:
    """Update card image (and artist_id) by card_id across decks."""
    db = _db_decks(); q = Query()
    card = db.get((q._type == "card") & (q.card_id == card_id))
    if not card:
        return False
    card["image"] = image
    if artist_id is not None:
        card["artist_id"] = artist_id or None
        # refresh artist_links if we can resolve it
        try:
            from bigtree.modules import artists
            artist = artists.get_artist(artist_id) if artist_id else None
            if artist and isinstance(artist.get("links"), dict):
                card["artist_links"] = artist.get("links") or {}
        except Exception:
            pass
    db.update(card, (q._type == "card") & (q.deck_id == card.get("deck_id")) & (q.card_id == card_id))
    return True

# -------- Sessions --------
def list_sessions() -> List[Dict[str, Any]]:
    db = _db_sessions(); q = Query()
    sessions = db.search(q._type == "session")
    sessions.sort(key=lambda s: float(s.get("created_at") or 0), reverse=True)
    return sessions

def create_session(priestess_id: int, deck_id: str, spread_id: str) -> Dict[str, Any]:
    db = _db_sessions()
    session_id = _new_id()
    join_code = _new_code()
    priestess_token = _new_id()
    spread_positions = _get_spread(spread_id)
    session = {
        "_type": "session",
        "session_id": session_id,
        "join_code": join_code,
        "priestess_id": int(priestess_id),
        "priestess_token": priestess_token,
        "deck_id": (deck_id or "").strip() or "elf-classic",
        "spread_id": (spread_id or "").strip() or "single",
        "spread_positions": spread_positions,
        "status": "created",
        "participants": [],
        "draw": [],
        "narration": [],
        "event_seq": 0,
        "events": [],
        "created_at": _now(),
    }
    db.insert(session)
    _add_event(session, "SESSION_CREATED", {"session_id": session_id})
    logger.info(f"[tarot] Session created {session_id} join={join_code}")
    return session

def _get_session_by(field: str, value: str) -> Optional[Dict[str, Any]]:
    db = _db_sessions(); q = Query()
    return db.get((q._type == "session") & (getattr(q, field) == value))

def get_session_by_id(session_id: str) -> Optional[Dict[str, Any]]:
    return _get_session_by("session_id", session_id)

def get_session_by_join_code(join_code: str) -> Optional[Dict[str, Any]]:
    return _get_session_by("join_code", join_code)

def _update_session(session_id: str, session: Dict[str, Any]) -> None:
    db = _db_sessions(); q = Query()
    db.update(session, (q._type == "session") & (q.session_id == session_id))

def _add_event(session: Dict[str, Any], event_type: str, data: Dict[str, Any]) -> None:
    seq = int(session.get("event_seq", 0)) + 1
    session["event_seq"] = seq
    ev = {"seq": seq, "ts": _now(), "type": event_type, "data": data}
    session.setdefault("events", []).append(ev)
    _update_session(session["session_id"], session)

def list_events(session_id: str, since_seq: int) -> List[Dict[str, Any]]:
    s = get_session_by_id(session_id)
    if not s:
        return []
    return [e for e in s.get("events", []) if int(e.get("seq", 0)) > since_seq]

def join_session(join_code: str, viewer_id: Optional[int] = None) -> Dict[str, Any]:
    s = get_session_by_join_code(join_code)
    if not s:
        raise ValueError("not found")
    viewer_token = _new_id()
    entry = {
        "viewer_token": viewer_token,
        "viewer_id": int(viewer_id) if viewer_id is not None else None,
        "joined_at": _now(),
    }
    s.setdefault("participants", []).append(entry)
    _update_session(s["session_id"], s)
    _add_event(s, "PLAYER_JOINED", {"viewer_id": entry["viewer_id"]})
    return {"viewer_token": viewer_token, "session": s}

def _require_priestess(session: Dict[str, Any], token: str) -> None:
    if not token or token != session.get("priestess_token"):
        raise PermissionError("invalid token")

def start_session(session_id: str, token: str) -> Dict[str, Any]:
    s = get_session_by_id(session_id)
    if not s:
        raise ValueError("not found")
    _require_priestess(s, token)
    if s["status"] != "live":
        s["status"] = "live"
        _update_session(session_id, s)
        _add_event(s, "SESSION_STARTED", {})
    return s

def finish_session(session_id: str, token: str) -> Dict[str, Any]:
    s = get_session_by_id(session_id)
    if not s:
        raise ValueError("not found")
    _require_priestess(s, token)
    s["status"] = "finished"
    _update_session(session_id, s)
    _add_event(s, "SESSION_FINISHED", {})
    return s

def shuffle_session(session_id: str, token: str) -> Dict[str, Any]:
    s = get_session_by_id(session_id)
    if not s:
        raise ValueError("not found")
    _require_priestess(s, token)
    _add_event(s, "SHUFFLE_STARTED", {})
    _add_event(s, "SHUFFLE_ENDED", {})
    return s

def draw_cards(session_id: str, token: str, count: int = 1, position_id: Optional[str] = None) -> Dict[str, Any]:
    s = get_session_by_id(session_id)
    if not s:
        raise ValueError("not found")
    _require_priestess(s, token)

    positions = [p["id"] for p in s.get("spread_positions", [])]
    existing = {d["position_id"]: d for d in s.get("draw", [])}
    open_positions = [p for p in positions if p not in existing]
    if position_id:
        if position_id not in positions:
            raise ValueError("invalid position_id")
        open_positions = [position_id] if position_id in open_positions else []
    count = max(1, min(int(count or 1), len(open_positions)))

    deck_cards = list_cards(s["deck_id"])
    used_ids = {d["card_id"] for d in s.get("draw", [])}
    remaining = [c for c in deck_cards if c.get("card_id") not in used_ids]
    random.shuffle(remaining)
    to_draw = remaining[:count]

    for idx, card in enumerate(to_draw):
        pos = open_positions[idx]
        entry = {
            "position_id": pos,
            "card_id": card.get("card_id"),
            "reversed": bool(random.getrandbits(1)),
            "revealed": False,
            "revealed_at": None,
        }
        s.setdefault("draw", []).append(entry)
        _add_event(s, "CARD_DRAWN", {"position_id": pos, "card_id": entry["card_id"], "reversed": entry["reversed"]})

    _update_session(session_id, s)
    return s

def reveal(session_id: str, token: str, mode: str = "next", position_id: Optional[str] = None) -> Dict[str, Any]:
    s = get_session_by_id(session_id)
    if not s:
        raise ValueError("not found")
    _require_priestess(s, token)
    draw = s.get("draw", [])

    def _reveal_entry(entry: Dict[str, Any]) -> None:
        if entry.get("revealed"):
            return
        entry["revealed"] = True
        entry["revealed_at"] = _now()
        _add_event(s, "CARD_REVEALED", {"position_id": entry["position_id"]})

    if mode == "all":
        for entry in draw:
            _reveal_entry(entry)
    elif mode == "position" and position_id:
        for entry in draw:
            if entry.get("position_id") == position_id:
                _reveal_entry(entry)
                break
    else:
        for entry in draw:
            if not entry.get("revealed"):
                _reveal_entry(entry)
                break

    _update_session(session_id, s)
    return s

def add_narration(session_id: str, token: str, text: str, style: Optional[str] = None) -> Dict[str, Any]:
    s = get_session_by_id(session_id)
    if not s:
        raise ValueError("not found")
    _require_priestess(s, token)
    entry = {"ts": _now(), "text": (text or "").strip(), "style": (style or "").strip() or None}
    if not entry["text"]:
        raise ValueError("text required")
    s.setdefault("narration", []).append(entry)
    _update_session(session_id, s)
    _add_event(s, "NARRATION_ADDED", {"text": entry["text"], "style": entry["style"]})
    return s

def _safe_draw(session: Dict[str, Any], reveal_all: bool) -> List[Dict[str, Any]]:
    out = []
    for entry in session.get("draw", []):
        revealed = bool(entry.get("revealed"))
        if reveal_all or revealed:
            card = get_card(session["deck_id"], entry.get("card_id"))
        else:
            card = None
        out.append({
            "position_id": entry.get("position_id"),
            "card_id": entry.get("card_id"),
            "reversed": bool(entry.get("reversed")),
            "revealed": revealed,
            "revealed_at": entry.get("revealed_at"),
            "card": card,
        })
    return out

def get_state(session: Dict[str, Any], view: str = "player") -> Dict[str, Any]:
    deck = get_deck(session.get("deck_id")) or {"deck_id": session.get("deck_id")}
    reveal_all = view == "priestess"
    return {
        "session": {
            "session_id": session.get("session_id"),
            "join_code": session.get("join_code"),
            "deck_id": session.get("deck_id"),
            "spread_id": session.get("spread_id"),
            "status": session.get("status"),
            "created_at": session.get("created_at"),
        },
        "spread": {
            "id": session.get("spread_id"),
            "positions": session.get("spread_positions", []),
        },
        "deck": {
            "deck_id": deck.get("deck_id"),
            "name": deck.get("name"),
            "back_image": deck.get("back_image"),
        },
        "draw": _safe_draw(session, reveal_all),
        "narration": session.get("narration", []),
    }

# -------- Compatibility (legacy commands) --------
def add_card(deck: str, title: str, meaning: str, image_url: str = "", tags=None) -> int:
    card = add_or_update_card(deck, {
        "id": title.lower().replace(" ", "_"),
        "name": title,
        "upright": meaning,
        "image": image_url,
        "tags": tags or [],
    })
    return 1 if card else 0

def new_session(owner_id: int, deck: str, spread: str = "single") -> str:
    s = create_session(owner_id, deck, spread)
    return s["session_id"]

def get_session(sid: str) -> Optional[Dict[str, Any]]:
    return get_session_by_id(sid)

def update_session(sid: str, fn: Callable[[Dict[str, Any]], Dict[str, Any] | None]) -> Optional[Dict[str, Any]]:
    s = get_session_by_id(sid)
    if not s:
        return None
    ns = fn(s) or s
    _update_session(sid, ns)
    return ns

def end_session(sid: str) -> None:
    s = get_session_by_id(sid)
    if not s:
        return
    s["status"] = "finished"
    _update_session(sid, s)

def delete_session(session_id: str, token: str) -> bool:
    s = get_session_by_id(session_id)
    if not s:
        return False
    _require_priestess(s, token)
    db = _db_sessions(); q = Query()
    db.remove((q._type == "session") & (q.session_id == session_id))
    return True

def draw_cards_legacy(sid: str, count: int = 1) -> List[Dict[str, Any]]:
    s = get_session_by_id(sid)
    if not s:
        return []
    draw_cards(sid, s.get("priestess_token", ""), count=count)
    return s.get("draw", [])

def flip_card(sid: str, index: int) -> Optional[Dict[str, Any]]:
    s = get_session_by_id(sid)
    if not s:
        return None
    if index < 0 or index >= len(s.get("draw", [])):
        return None
    position_id = s["draw"][index]["position_id"]
    reveal(sid, s.get("priestess_token", ""), mode="position", position_id=position_id)
    return get_session_by_id(sid)

def user_is_priestish(member) -> bool:
    conf = {}
    try:
        conf = bigtree.config.config.get("BOT", {}) if bigtree else {}
    except Exception:
        conf = {}
    priest = set(map(int, conf.get("priest_role_ids", [])))
    elfmin = set(map(int, conf.get("elfministrator_role_ids", [])))
    roles = {r.id for r in getattr(member, "roles", [])}
    return bool(priest & roles or elfmin & roles or member.guild_permissions.administrator)
