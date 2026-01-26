# bigtree/modules/tarot.py
# Tarot sessions + decks with event stream support

from __future__ import annotations
import os
import json as _json
import hashlib
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
_DECKS_MIGRATED: Optional[bool] = None
_TEMPLATE_DECK_ID = "tarot-template"
_PLAYING_TEMPLATE_DECK_ID = "playing-template"
_DECK_PURPOSES = {"tarot", "playing"}
_DEFAULT_CARD_LIMIT = 2
_SEED_CACHE: Optional[Dict[str, Any]] = None

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

def _get_decks_dir() -> str:
    base = _get_base_dir()
    path = os.path.join(base, "decks")
    os.makedirs(path, exist_ok=True)
    return path

def _safe_deck_filename(deck_id: str) -> str:
    raw = str(deck_id or "").strip()
    keep = []
    for ch in raw:
        if ch.isalnum() or ch in ("-", "_"):
            keep.append(ch)
        else:
            keep.append("_")
    name = "".join(keep).strip("_") or "deck"
    if name != raw and raw:
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
        name = f"{name}_{digest}"
    return f"{name}.json"

def _deck_file_path(deck_id: str) -> str:
    return os.path.join(_get_decks_dir(), _safe_deck_filename(deck_id))

def _read_deck_file(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = _json.loads(fh.read())
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None

def _write_deck_file(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    text = _json.dumps(payload, ensure_ascii=True, indent=2)
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)

def _normalize_deck_file_data(data: Any) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    if not isinstance(data, dict):
        return None, []
    if "deck" in data:
        deck = data.get("deck") if isinstance(data.get("deck"), dict) else None
        cards = data.get("cards") if isinstance(data.get("cards"), list) else []
        return deck, cards
    if data.get("_type") == "deck":
        cards = data.get("cards") if isinstance(data.get("cards"), list) else []
        return data, cards
    return None, []

def _list_deck_files() -> List[str]:
    try:
        root = _get_decks_dir()
        return [
            os.path.join(root, name)
            for name in os.listdir(root)
            if name.lower().endswith(".json")
        ]
    except Exception:
        return []

def _load_deck_bundle(deck_id: str) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], Optional[str]]:
    _migrate_decks_to_files()
    deck_id = (deck_id or "").strip()
    if not deck_id:
        return None, [], None
    candidate = _deck_file_path(deck_id)
    if os.path.exists(candidate):
        data = _read_deck_file(candidate)
        deck, cards = _normalize_deck_file_data(data)
        if deck:
            return deck, cards, candidate
    for path in _list_deck_files():
        data = _read_deck_file(path)
        deck, cards = _normalize_deck_file_data(data)
        if deck and deck.get("deck_id") == deck_id:
            return deck, cards, path
    # Fallback: decks may have been synced into Postgres (deck_files) in
    # containerized deployments where the filesystem deck dir is empty.
    try:
        from bigtree.inc.database import get_database
        row = get_database().get_deck_file(deck_id)
        payload = row.get("payload") if isinstance(row, dict) else None
        if payload:
            deck, cards = _normalize_deck_file_data(payload)
            if deck:
                return deck, cards, None
    except Exception:
        pass
    return None, [], candidate

def _save_deck_bundle(deck: Dict[str, Any], cards: List[Dict[str, Any]], path: str) -> None:
    _write_deck_file(path, {"deck": deck, "cards": cards})

def _migrate_decks_to_files() -> None:
    global _DECKS_MIGRATED
    if _DECKS_MIGRATED is True:
        return
    base = _get_base_dir()
    marker = os.path.join(base, ".tarot_decks_files")
    try:
        if os.path.exists(marker):
            _DECKS_MIGRATED = True
            return
    except Exception:
        pass

    decks_dir = _get_decks_dir()
    try:
        if any(name.lower().endswith(".json") for name in os.listdir(decks_dir)):
            try:
                with open(marker, "w", encoding="utf-8") as fh:
                    fh.write("migrated=1\n")
            except Exception:
                pass
            _DECKS_MIGRATED = True
            return
    except Exception:
        pass

    _migrate_if_needed()
    deck_db_path = _get_deck_db_path()
    if os.path.exists(deck_db_path):
        db = TinyDB(deck_db_path)
        q = Query()
        decks = db.search(q._type == "deck")
        cards = db.search(q._type == "card")
        if decks or cards:
            grouped_cards: Dict[str, List[Dict[str, Any]]] = {}
            for card in cards:
                deck_id = (card.get("deck_id") or "elf-classic").strip() or "elf-classic"
                grouped_cards.setdefault(deck_id, []).append(card)
            if not decks and grouped_cards:
                decks = [
                    {
                        "_type": "deck",
                        "deck_id": deck_id,
                        "name": deck_id,
                        "theme": "classic",
                        "back_image": None,
                        "created_at": _now(),
                    }
                    for deck_id in grouped_cards.keys()
                ]
            for deck in decks:
                deck_id = (deck.get("deck_id") or "elf-classic").strip() or "elf-classic"
                deck["deck_id"] = deck_id
                deck.setdefault("_type", "deck")
                deck.setdefault("name", deck_id)
                deck.setdefault("theme", "classic")
                deck.setdefault("back_image", None)
                deck_path = _deck_file_path(deck_id)
                _save_deck_bundle(deck, grouped_cards.get(deck_id, []), deck_path)
            try:
                with open(marker, "w", encoding="utf-8") as fh:
                    fh.write(f"migrated={len(decks)}\n")
            except Exception:
                pass
            _DECKS_MIGRATED = True
            return
    _DECKS_MIGRATED = True

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
_NUMBERS_CACHE: Optional[List[Dict[str, Any]]] = None
_NUMBERS_WARNED = False

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

def _normalize_numbers(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, dict):
        raw = raw.get("numbers")
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            num = int(entry.get("number"))
        except Exception:
            continue
        if num < 0 or num > 10:
            continue
        label = str(entry.get("label") or "").strip()
        meaning = str(entry.get("meaning") or "").strip()
        out.append({
            "number": num,
            "label": label,
            "meaning": meaning,
        })
    out.sort(key=lambda n: int(n.get("number") or 0))
    return out

def _load_numbers() -> List[Dict[str, Any]]:
    global _NUMBERS_CACHE, _NUMBERS_WARNED
    if _NUMBERS_CACHE is not None:
        return _NUMBERS_CACHE
    candidates: List[str] = []
    env_path = os.getenv("BIGTREE_TAROT_NUMBERS")
    if env_path:
        candidates.append(env_path)
    base = _get_base_dir()
    candidates.append(os.path.join(base, "tarot_numbers.json"))
    try:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        candidates.append(os.path.join(repo_root, "tarot_numbers.json"))
        candidates.append(os.path.join(repo_root, "defaults", "tarot_numbers.json"))
    except Exception:
        pass
    for path in candidates:
        if os.path.exists(path):
            data = _read_json(path)
            numbers = _normalize_numbers(data)
            if numbers:
                _NUMBERS_CACHE = numbers
                return _NUMBERS_CACHE
    if not _NUMBERS_WARNED:
        _NUMBERS_WARNED = True
        logger.warning("[tarot] numbers file not found; checked: %s", ", ".join(candidates))
    _NUMBERS_CACHE = [
        {"number": 0, "label": "", "meaning": "The unmanifest, before identity, destiny"},
        {"number": 1, "label": "Aces", "meaning": "New beginnings, opportunity, potential"},
        {"number": 2, "label": "", "meaning": "Balance, partnership, duality"},
        {"number": 3, "label": "", "meaning": "Creativity, groups, growth"},
        {"number": 4, "label": "", "meaning": "Structure, stability, manifestation"},
        {"number": 5, "label": "", "meaning": "Change, instability, conflict"},
        {"number": 6, "label": "", "meaning": "Communication, cooperation, harmony"},
        {"number": 7, "label": "", "meaning": "Reflection, assessment, knowledge"},
        {"number": 8, "label": "", "meaning": "Mastery, action, accomplishment"},
        {"number": 9, "label": "", "meaning": "Fruition, attainment, fulfilment"},
        {"number": 10, "label": "", "meaning": "Completion, end of a cycle, renewal"},
    ]
    return _NUMBERS_CACHE

def list_numbers() -> List[Dict[str, Any]]:
    return list(_load_numbers())

# -------- Decks --------
_THEMES = {"classic", "wood", "neon"}

def _normalize_theme(theme: Optional[str]) -> str:
    theme = str(theme or "").strip().lower()
    return theme if theme in _THEMES else "classic"

def _normalize_purpose(purpose: Optional[str]) -> str:
    value = str(purpose or "").strip().lower()
    return value if value in _DECK_PURPOSES else "tarot"

_ROMAN_MAP = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}

def _parse_roman(value: str) -> Optional[int]:
    roman = (value or "").strip().upper()
    if not roman:
        return None
    total = 0
    prev = 0
    for ch in reversed(roman):
        num = _ROMAN_MAP.get(ch)
        if not num:
            return None
        if num < prev:
            total -= num
        else:
            total += num
            prev = num
    return total if total > 0 else None

def _parse_number(value: Any) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    return _parse_roman(text)

def _standard_tarot_cards() -> List[Dict[str, Any]]:
    majors = [
        "The Fool",
        "The Magician",
        "The High Priestess",
        "The Empress",
        "The Emperor",
        "The Hierophant",
        "The Lovers",
        "The Chariot",
        "Strength",
        "The Hermit",
        "Wheel of Fortune",
        "Justice",
        "The Hanged Man",
        "Death",
        "Temperance",
        "The Devil",
        "The Tower",
        "The Star",
        "The Moon",
        "The Sun",
        "Judgement",
        "The World",
    ]
    ranks = [
        "Ace",
        "Two",
        "Three",
        "Four",
        "Five",
        "Six",
        "Seven",
        "Eight",
        "Nine",
        "Ten",
        "Page",
        "Knight",
        "Queen",
        "King",
    ]
    suits = ["Wands", "Cups", "Swords", "Pentacles"]
    cards: List[Dict[str, Any]] = []
    for name in majors:
        cards.append({
            "name": name,
            "card_id": name.lower().replace(" ", "_"),
            "tags": ["major"],
        })
    for suit in suits:
        for rank in ranks:
            name = f"{rank} of {suit}"
            cards.append({
                "name": name,
                "card_id": name.lower().replace(" ", "_"),
                "tags": [suit.lower(), "minor"],
            })
    return cards

def _standard_playing_cards() -> List[Dict[str, Any]]:
    rank_labels = [
        ("A", "Ace"),
        ("2", "Two"),
        ("3", "Three"),
        ("4", "Four"),
        ("5", "Five"),
        ("6", "Six"),
        ("7", "Seven"),
        ("8", "Eight"),
        ("9", "Nine"),
        ("10", "Ten"),
        ("J", "Jack"),
        ("Q", "Queen"),
        ("K", "King"),
    ]
    suits = ["spades", "hearts", "diamonds", "clubs"]
    cards: List[Dict[str, Any]] = []
    for suit in suits:
        suit_name = suit.title()
        for rank, label in rank_labels:
            name = f"{label} of {suit_name}"
            card_id = f"{label.lower()}_of_{suit}"
            cards.append({
                "name": name,
                "card_id": card_id,
                "suit": suit,
                "number": rank,
                "tags": ["playing"],
            })
    return cards

def _seed_candidates() -> List[str]:
    candidates: List[str] = []
    env_path = os.getenv("BIGTREE_TAROT_SEED")
    if env_path:
        candidates.append(env_path)
    base = _get_base_dir()
    candidates.append(os.path.join(base, "tarot_seed_default.json"))
    candidates.append(os.path.join(base, "tarot", "seed.json"))
    try:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        candidates.append(os.path.join(repo_root, "tarot_seed_default.json"))
        candidates.append(os.path.join(repo_root, "defaults", "tarot_seed_default.json"))
    except Exception:
        pass
    return candidates

def _load_seed_data() -> Optional[Dict[str, Any]]:
    global _SEED_CACHE
    if _SEED_CACHE is not None:
        return _SEED_CACHE
    for path in _seed_candidates():
        if not os.path.exists(path):
            continue
        data = _read_json(path)
        if isinstance(data, dict):
            _SEED_CACHE = data
            return _SEED_CACHE
    _SEED_CACHE = None
    return None

def _normalize_seed_data(data: Optional[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    if not isinstance(data, dict):
        return None, []
    deck = data.get("deck") if isinstance(data.get("deck"), dict) else None
    cards = data.get("cards") if isinstance(data.get("cards"), list) else []
    return deck, [c for c in cards if isinstance(c, dict)]

def ensure_template_deck(deck_id: Optional[str] = None) -> Dict[str, Any]:
    template_id = (deck_id or _TEMPLATE_DECK_ID).strip() or _TEMPLATE_DECK_ID
    deck, cards, path = _load_deck_bundle(template_id)
    if deck and cards:
        if deck.get("purpose") != "tarot":
            deck["purpose"] = "tarot"
            _save_deck_bundle(deck, cards, path or _deck_file_path(template_id))
        return deck
    seed_data = _load_seed_data()
    seed_deck, seed_cards = _normalize_seed_data(seed_data)
    if seed_cards:
        name = (seed_deck or {}).get("name") if seed_deck else None
        theme = (seed_deck or {}).get("theme") if seed_deck else None
        deck = deck or create_deck(template_id, name=name or "Tarot Template", theme=theme, purpose="tarot")
        for card in seed_cards:
            payload = dict(card)
            payload["deck_id"] = template_id
            add_or_update_card(template_id, payload)
    else:
        deck = deck or create_deck(template_id, name="Tarot Template", theme="classic", purpose="tarot")
        existing_ids = {c.get("card_id") for c in (cards or []) if c.get("card_id")}
        for card in _standard_tarot_cards():
            if card.get("card_id") in existing_ids:
                continue
            add_or_update_card(template_id, card)
    return get_deck(template_id) or deck

def ensure_playing_template_deck(deck_id: Optional[str] = None) -> Dict[str, Any]:
    template_id = (deck_id or _PLAYING_TEMPLATE_DECK_ID).strip() or _PLAYING_TEMPLATE_DECK_ID
    deck, cards, path = _load_deck_bundle(template_id)
    if deck and cards:
        if deck.get("purpose") != "playing":
            deck["purpose"] = "playing"
            _save_deck_bundle(deck, cards, path or _deck_file_path(template_id))
        return deck
    deck = deck or create_deck(template_id, name="Playing Cards Template", theme="classic", purpose="playing")
    existing_ids = {c.get("card_id") for c in (cards or []) if c.get("card_id")}
    for card in _standard_playing_cards():
        if card.get("card_id") in existing_ids:
            continue
        add_or_update_card(template_id, card)
    return get_deck(template_id) or deck

def list_template_cards(purpose: Optional[str] = None) -> List[Dict[str, Any]]:
    purpose = _normalize_purpose(purpose)
    if purpose == "playing":
        ensure_playing_template_deck()
        return list_cards(_PLAYING_TEMPLATE_DECK_ID)
    ensure_template_deck()
    return list_cards(_TEMPLATE_DECK_ID)

def seed_deck_from_template(deck_id: str, template_id: Optional[str] = None) -> Dict[str, Any]:
    template_id = (template_id or _TEMPLATE_DECK_ID).strip() or _TEMPLATE_DECK_ID
    ensure_template_deck(template_id)
    deck = get_deck(deck_id)
    if not deck:
        deck = create_deck(deck_id, name=deck_id)
    for card in list_cards(template_id):
        payload = {
            "card_id": card.get("card_id"),
            "name": card.get("name"),
            "tags": card.get("tags", []),
        }
        add_or_update_card(deck_id, payload)
    return deck

def seed_deck_from_seed_file(deck_id: str) -> Dict[str, Any]:
    seed_data = _load_seed_data()
    seed_deck, seed_cards = _normalize_seed_data(seed_data)
    if not seed_cards:
        return seed_deck_from_template(deck_id)
    deck = get_deck(deck_id)
    if not deck:
        name = (seed_deck or {}).get("name") if seed_deck else None
        theme = (seed_deck or {}).get("theme") if seed_deck else None
        deck = create_deck(deck_id, name=name or deck_id, theme=theme)
    for card in seed_cards:
        payload = dict(card)
        payload["deck_id"] = deck_id
        add_or_update_card(deck_id, payload)
    return deck

def create_deck(
    deck_id: str,
    name: Optional[str] = None,
    theme: Optional[str] = None,
    purpose: Optional[str] = None,
    suits: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    deck_id = (deck_id or "").strip() or "elf-classic"
    _migrate_decks_to_files()
    existing, cards, path = _load_deck_bundle(deck_id)
    if existing:
        return existing
    deck = {
        "_type": "deck",
        "deck_id": deck_id,
        "name": (name or deck_id),
        "theme": _normalize_theme(theme),
        "purpose": _normalize_purpose(purpose),
        "back_image": None,
        "suits": suits or [],
        "created_at": _now(),
    }
    path = path or _deck_file_path(deck_id)
    _save_deck_bundle(deck, cards or [], path)
    return deck

def list_decks() -> List[Dict[str, Any]]:
    _migrate_decks_to_files()
    decks: List[Dict[str, Any]] = []

    # Prefer Postgres-synced decks if available (deck editor in containers
    # often does not have the filesystem deck directory mounted).
    try:
        from bigtree.inc.database import get_database
        rows = get_database().list_deck_files(module="tarot", limit=500)
        for row in rows or []:
            payload = row.get("payload") if isinstance(row, dict) else None
            if not payload:
                continue
            deck, _cards = _normalize_deck_file_data(payload)
            if deck:
                decks.append(deck)
    except Exception:
        pass

    # Fallback to filesystem deck bundles.
    if not decks:
        for path in _list_deck_files():
            data = _read_deck_file(path)
            deck, _cards = _normalize_deck_file_data(data)
            if deck:
                decks.append(deck)
    if not decks:
        create_deck("elf-classic")
        return list_decks()
    filtered: List[Dict[str, Any]] = []
    for deck in decks:
        if not isinstance(deck, dict):
            continue
        deck_id = str(deck.get("deck_id") or deck.get("id") or "").strip()
        if deck_id in {_TEMPLATE_DECK_ID, _PLAYING_TEMPLATE_DECK_ID}:
            continue
        if not deck.get("purpose"):
            deck["purpose"] = "tarot"
        filtered.append(deck)
    if not filtered:
        create_deck("elf-classic")
        return list_decks()
    return filtered

def get_deck_bundle(deck_id: str) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    deck, cards, _path = _load_deck_bundle(deck_id)
    return deck, cards or []

def delete_deck(deck_id: str) -> bool:
    deck_id = (deck_id or "").strip()
    if not deck_id:
        return False
    deck, _cards, path = _load_deck_bundle(deck_id)
    if not deck or not path:
        return False
    try:
        os.remove(path)
    except Exception:
        return False
    return True

def update_deck(
    deck_id: str,
    name: Optional[str] = None,
    theme: Optional[str] = None,
    purpose: Optional[str] = None,
    suits: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    deck_id = (deck_id or "").strip()
    if not deck_id:
        return None
    deck, cards, path = _load_deck_bundle(deck_id)
    if not deck:
        return None
    if name is not None:
        deck["name"] = (name or deck_id)
    if theme is not None:
        deck["theme"] = _normalize_theme(theme)
    if purpose is not None:
        deck["purpose"] = _normalize_purpose(purpose)
    if suits is not None:
        deck["suits"] = suits
    _save_deck_bundle(deck, cards, path or _deck_file_path(deck_id))
    return deck

def get_deck(deck_id: str) -> Optional[Dict[str, Any]]:
    deck, _cards, _path = _load_deck_bundle(deck_id)
    if deck and not deck.get("purpose"):
        deck["purpose"] = "tarot"
    return deck

def set_deck_back(deck_id: str, back_image: str, artist_id: Optional[str] = None) -> bool:
    deck = get_deck(deck_id)
    if not deck:
        create_deck(deck_id)
    deck, cards, path = _load_deck_bundle(deck_id)
    if not deck:
        return False
    deck["back_image"] = back_image
    if artist_id is not None:
        deck["back_artist_id"] = artist_id or None
    _save_deck_bundle(deck, cards, path or _deck_file_path(deck_id))
    return True

def add_or_update_card(deck_id: str, card: Dict[str, Any]) -> Dict[str, Any]:
    deck_id = (deck_id or "").strip() or "elf-classic"
    create_deck(deck_id)
    deck, cards, path = _load_deck_bundle(deck_id)
    cards = cards or []
    card_id = (card.get("id") or card.get("card_id") or "").strip()
    name = (card.get("name") or card.get("title") or "").strip()
    if not name:
        raise ValueError("name required")
    if not card_id:
        card_id = name.lower().replace(" ", "_")[:48]
    existing = next((c for c in cards if c.get("card_id") == card_id), None)
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
    if "themes" in card:
        raw_themes = card.get("themes")
    elif existing and isinstance(existing.get("themes"), dict):
        raw_themes = existing.get("themes")
    else:
        raw_themes = {}
    if "flavor_text" in card:
        flavor_text = str(card.get("flavor_text") or "").strip()
    elif existing:
        flavor_text = (existing.get("flavor_text") or "").strip()
    else:
        flavor_text = ""
    if "number" in card:
        raw_number = card.get("number")
    elif existing:
        raw_number = existing.get("number")
    else:
        raw_number = None
    if "claim_status" in card:
        claim_status = str(card.get("claim_status") or "").strip().lower() or None
    else:
        claim_status = (existing.get("claim_status") if existing else None)
    if "claimed_by" in card:
        claimed_by = card.get("claimed_by")
    else:
        claimed_by = existing.get("claimed_by") if existing else None
    if "claimed_by_name" in card:
        claimed_by_name = str(card.get("claimed_by_name") or "").strip() or None
    else:
        claimed_by_name = (existing.get("claimed_by_name") if existing else None)
    if "claimed_at" in card:
        claimed_at = card.get("claimed_at")
    else:
        claimed_at = existing.get("claimed_at") if existing else None
    if "filled_by" in card:
        filled_by = card.get("filled_by")
    else:
        filled_by = existing.get("filled_by") if existing else None
    if "filled_by_name" in card:
        filled_by_name = str(card.get("filled_by_name") or "").strip() or None
    else:
        filled_by_name = (existing.get("filled_by_name") if existing else None)
    if "filled_at" in card:
        filled_at = card.get("filled_at")
    else:
        filled_at = existing.get("filled_at") if existing else None
    number = _parse_number(raw_number)
    cleaned_themes = {}
    if isinstance(raw_themes, dict):
        for key, val in raw_themes.items():
            try:
                weight = int(val)
            except Exception:
                continue
            if weight <= 0:
                continue
            cleaned_themes[str(key)] = weight
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
        "suit": (card.get("suit") if "suit" in card else (existing.get("suit") if existing else None)),
        "upright": (card.get("upright") or card.get("meaning") or "").strip(),
        "reversed": (card.get("reversed") or "").strip(),
        "tags": card.get("tags") if isinstance(card.get("tags"), list) else [],
        "image": (card.get("image") or card.get("image_url") or "").strip(),
        "artist_id": artist_id,
        "artist_links": cleaned_links,
        "themes": cleaned_themes,
        "number": number,
        "flavor_text": flavor_text,
        "claim_status": claim_status,
        "claimed_by": claimed_by,
        "claimed_by_name": claimed_by_name,
        "claimed_at": claimed_at,
        "filled_by": filled_by,
        "filled_by_name": filled_by_name,
        "filled_at": filled_at,
        "updated_at": _now(),
    }
    if existing:
        for idx, entry in enumerate(cards):
            if entry.get("card_id") == card_id:
                payload["created_at"] = entry.get("created_at")
                cards[idx] = payload
                break
    else:
        payload["created_at"] = _now()
        cards.append(payload)
    _save_deck_bundle(deck or get_deck(deck_id) or {"_type": "deck", "deck_id": deck_id}, cards, path or _deck_file_path(deck_id))
    return payload

def list_cards(deck_id: str) -> List[Dict[str, Any]]:
    deck_id = (deck_id or "").strip() or "elf-classic"
    _deck, cards, _path = _load_deck_bundle(deck_id)
    return cards or []

def clear_image_references(image_url: str) -> int:
    """Remove image/back references pointing at the given URL (ignores query)."""
    target = (image_url or "").split("?", 1)[0]
    if not target:
        return 0
    updated = 0
    for path in _list_deck_files():
        data = _read_deck_file(path)
        deck, cards = _normalize_deck_file_data(data)
        if not deck:
            continue
        changed = False
        for card in cards:
            img = (card.get("image") or "").split("?", 1)[0]
            if img and img == target:
                card["image"] = ""
                updated += 1
                changed = True
        back = (deck.get("back_image") or "").split("?", 1)[0]
        if back and back == target:
            deck["back_image"] = None
            updated += 1
            changed = True
        if changed:
            _save_deck_bundle(deck, cards, path)
    return updated

def get_card(deck_id: str, card_id: str) -> Optional[Dict[str, Any]]:
    if not deck_id or not card_id:
        return None
    _deck, cards, _path = _load_deck_bundle(deck_id)
    for card in cards or []:
        if card.get("card_id") == card_id:
            return card
    return None

def set_card_image(card_id: str, image: str, artist_id: Optional[str] = None) -> bool:
    """Update card image (and artist_id) by card_id across decks."""
    for path in _list_deck_files():
        data = _read_deck_file(path)
        deck, cards = _normalize_deck_file_data(data)
        if not deck:
            continue
        updated = False
        for idx, card in enumerate(cards):
            if card.get("card_id") != card_id:
                continue
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
            cards[idx] = card
            updated = True
            break
        if updated:
            _save_deck_bundle(deck, cards, path)
            return True
    return False

def _user_claim_count(deck_id: str, user_id: int) -> int:
    count = 0
    for card in list_cards(deck_id):
        if card.get("claimed_by") == user_id and card.get("claim_status") == "claimed":
            count += 1
    return count

def claim_card(deck_id: str, card_id: str, user_id: int, user_name: str, limit: int = _DEFAULT_CARD_LIMIT) -> Tuple[bool, str]:
    card = get_card(deck_id, card_id)
    if not card:
        return False, "Card not found."
    if card.get("claim_status") == "done":
        return False, "Card is already marked done."
    claimed_by = card.get("claimed_by")
    if claimed_by and claimed_by != user_id:
        return False, "Card is already claimed."
    if claimed_by == user_id and card.get("claim_status") == "claimed":
        return False, "You already claimed this card."
    if _user_claim_count(deck_id, user_id) >= int(limit):
        return False, f"You can only claim {limit} card(s) at a time."
    card["claim_status"] = "claimed"
    card["claimed_by"] = user_id
    card["claimed_by_name"] = user_name
    card["claimed_at"] = _now()
    add_or_update_card(deck_id, card)
    return True, "Card claimed."

def unclaim_card(deck_id: str, card_id: str, user_id: int, force: bool = False) -> Tuple[bool, str]:
    card = get_card(deck_id, card_id)
    if not card:
        return False, "Card not found."
    if card.get("claim_status") != "claimed":
        return False, "Card is not claimed."
    if not force and card.get("claimed_by") != user_id:
        return False, "You do not own this claim."
    card["claim_status"] = None
    card["claimed_by"] = None
    card["claimed_by_name"] = None
    card["claimed_at"] = None
    add_or_update_card(deck_id, card)
    return True, "Card unclaimed."

def mark_card_done(deck_id: str, card_id: str, user_id: int, user_name: str, force: bool = False) -> Tuple[bool, str]:
    card = get_card(deck_id, card_id)
    if not card:
        return False, "Card not found."
    if card.get("claim_status") == "done":
        return False, "Card is already marked done."
    if not force and card.get("claimed_by") != user_id:
        return False, "You do not own this claim."
    card["claim_status"] = "done"
    card["filled_by"] = user_id
    card["filled_by_name"] = user_name
    card["filled_at"] = _now()
    card["claimed_by"] = None
    card["claimed_by_name"] = None
    card["claimed_at"] = None
    add_or_update_card(deck_id, card)
    return True, "Card marked done."

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
            "theme": deck.get("theme") or "classic",
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
