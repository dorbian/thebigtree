# bigtree/modules/bingo.py
# Core Bingo logic & persistence using TinyDB (game_id-first, background support)

import os
import uuid
import time
import random
import shutil
from typing import Dict, Any, List, Optional, Tuple
from tinydb import TinyDB, Query

# -------- logger (no circular import) --------
try:
    from bigtree.inc.logging import logger
except Exception:  # fallback if early import
    import logging
    logger = logging.getLogger("bigtree")

# -------- lazy workdir resolution (avoid touching bigtree at import time) --------
_BINGO_DIR: Optional[str] = None
_DB_DIR: Optional[str] = None
_ASSETS: Optional[str] = None
_INDEX: Optional[str] = None

# -------- stages --------
STAGES = ("single", "double", "full")  # single line, double line, whole card

def _now() -> float:
    return time.time()

def _get_workingdir() -> str:
    """Resolve BigTree working dir without importing bigtree at import time."""
    env = os.getenv("BIGTREE_WORKDIR")
    if env:
        return env
    try:
        import bigtree  # local import once package is fully ready
        wd = getattr(bigtree, "workingdir", None)
        if wd:
            return wd
    except Exception:
        pass
    return os.path.join(os.getcwd(), ".bigtree")

def _ensure_dirs():
    """Initialize bingo directories the first time they're needed."""
    global _BINGO_DIR, _DB_DIR, _ASSETS, _INDEX
    if _BINGO_DIR is not None:
        return
    base = os.path.join(_get_workingdir(), "bingo")
    db = os.path.join(base, "db")
    assets = os.path.join(base, "assets")
    os.makedirs(db, exist_ok=True)
    os.makedirs(assets, exist_ok=True)
    _BINGO_DIR = base
    _DB_DIR = db
    _ASSETS = assets
    _INDEX = os.path.join(base, "index.json")

def _db_path(game_id: str) -> str:
    _ensure_dirs()
    return os.path.join(_DB_DIR, f"{game_id}.json")

def _open(game_id: str) -> TinyDB:
    _ensure_dirs()
    return TinyDB(_db_path(game_id))

def _new_game_id() -> str:
    return uuid.uuid4().hex

def _new_card_id() -> str:
    return uuid.uuid4().hex

# -------- header & column helpers --------
def _normalize_header(h: Optional[str]) -> str:
    h = (h or "BING").upper()
    return (h[:4]).ljust(4, " ")

def _column_ranges() -> List[range]:
    # 4 equal buckets across 1..80
    # c0: 1-20, c1: 21-40, c2: 41-60, c3: 61-80
    return [range(1, 21), range(21, 41), range(41, 61), range(61, 81)]

# ------------- Card generation (4x4 respecting column ranges) -------------
def generate_card_numbers() -> List[List[int]]:
    cols = _column_ranges()
    grid: List[List[int]] = [[0]*4 for _ in range(4)]
    # Build by columns to ensure 4 unique per column
    for c, rng in enumerate(cols):
        picks = random.sample(list(rng), 4)
        for r in range(4):
            grid[r][c] = picks[r]
    return grid

# ------- indexing helpers (track active game per channel) -------
def _read_index() -> Dict[str, Any]:
    _ensure_dirs()
    try:
        import json
        if os.path.exists(_INDEX):
            with open(_INDEX, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"active_by_channel": {}}  # channel_id(str) -> game_id

def _write_index(idx: Dict[str, Any]):
    _ensure_dirs()
    import json
    with open(_INDEX, "w", encoding="utf-8") as f:
        json.dump(idx, f, indent=2)

def set_active_for_channel(channel_id: int, game_id: str):
    idx = _read_index()
    idx["active_by_channel"][str(channel_id)] = game_id
    _write_index(idx)

def get_active_for_channel(channel_id: int) -> Optional[str]:
    return _read_index()["active_by_channel"].get(str(channel_id))

# ----------------- Game lifecycle -----------------
def create_game(
    channel_id: int,
    title: str,
    price: int,
    currency: str,
    max_cards_per_player: int,
    created_by: int,
    header_text: Optional[str] = None,  # NEW
) -> Dict[str, Any]:
    _ensure_dirs()
    game_id = _new_game_id()
    game = {
        "_type": "game",
        "game_id": game_id,
        "channel_id": int(channel_id),
        "title": (title or "").strip() or "Bingo",
        "header": _normalize_header(header_text),  # NEW
        "price": int(price),
        "currency": (currency or "").strip() or "gil",
        "max_cards_per_player": int(max_cards_per_player),
        "created_by": int(created_by),
        "created_at": _now(),
        "pot": 0,
        "called": [],
        "stage": "single",  # NEW
        "active": True,
        "background_path": None,  # file path under assets
        "claims": [],
    }
    db = _open(game_id)
    db.insert(game)
    set_active_for_channel(channel_id, game_id)
    logger.info(
        f"[bingo] Created game {game_id} (channel={channel_id}, price={price} {game['currency']}, header='{game['header']}', stage={game['stage']})"
    )
    return game

def get_game(game_id: str) -> Optional[Dict[str, Any]]:
    _ensure_dirs()
    if not os.path.exists(_db_path(game_id)):
        return None
    db = _open(game_id)
    rows = db.search(Query()._type == "game")
    return rows[-1] if rows else None

def end_game(game_id: str) -> bool:
    g = get_game(game_id)
    if not g:
        return False
    db = _open(game_id)
    g["active"] = False
    db.update(g, doc_ids=[g.doc_id])
    logger.info(f"[bingo] Ended game {game_id}")
    return True

def set_stage(game_id: str, stage: str) -> Tuple[bool, str]:
    stage = (stage or "").lower().strip()
    if stage not in STAGES:
        return False, f"Stage must be one of: {', '.join(STAGES)}"
    g = get_game(game_id)
    if not g:
        return False, "Game not found."
    db = _open(game_id)
    g["stage"] = stage
    db.update(g, doc_ids=[g.doc_id])
    logger.info(f"[bingo] Stage set to {stage} for game {game_id}")
    return True, "OK"

def claim_bingo(game_id: str, card_id: str) -> Tuple[bool, str]:
    g = get_game(game_id)
    if not g:
        return False, "Game not found."
    if not g.get("active"):
        return False, "Game is not active."

    db = _open(game_id)
    Card = Query()
    rows = db.search((Card._type == "card") & (Card.card_id == card_id))
    if not rows:
        return False, "Card not found."
    card = rows[-1]

    if card.get("claimed"):
        return True, "Already claimed."

    # mark claimed
    card["claimed"] = True
    db.update(card, doc_ids=[card.doc_id])

    # record claim entry on the game
    claim = {
        "ts": _now(),
        "card_id": card_id,
        "owner_name": card.get("owner_name"),
        "stage": g.get("stage", "single"),
    }
    g.setdefault("claims", []).append(claim)
    db.update(g, doc_ids=[g.doc_id])

    logger.info(f"[bingo] Claim by {claim['owner_name']} on card {card_id} (stage={claim['stage']}) in game {game_id}")
    return True, "OK"

def _payouts(pot: int) -> Dict[str, int]:
    # split pot into 6 parts: 1/6, 2/6, 3/6 (last gets remainder)
    p1 = pot // 6
    p2 = (2 * pot) // 6
    p3 = pot - (p1 + p2)
    return {"single": p1, "double": p2, "full": p3}

def player_card_count(db: TinyDB, game_id: str, owner_name: str) -> int:
    Card = Query()
    return len(db.search((Card._type == "card") & (Card.game_id == game_id) & (Card.owner_name == owner_name)))

def buy_card(game_id: str, owner_name: str, owner_user_id: Optional[int]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Backward-compatible single-card purchase."""
    cards, err = buy_cards(game_id, owner_name, 1, owner_user_id)
    if err:
        return None, err
    return (cards[0] if cards else None), None

def buy_cards(game_id: str, owner_name: str, count: int, owner_user_id: Optional[int]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Bulk purchase (1..10) respecting per-player cap and updating pot accordingly."""
    try:
        count = max(1, min(int(count or 1), 10))
    except Exception:
        count = 1

    g = get_game(game_id)
    if not g:
        return [], "Game not found."
    if not g.get("active"):
        return [], "Game is not active."
    owner_name = (owner_name or "").strip()
    if not owner_name:
        return [], "Owner name required."

    db = _open(game_id)
    have = player_card_count(db, game_id, owner_name)
    allow = g["max_cards_per_player"] - have
    if allow <= 0:
        return [], f"Player already has {have} cards (max {g['max_cards_per_player']})."

    to_buy = min(count, allow)
    cards: List[Dict[str, Any]] = []
    for _ in range(to_buy):
        numbers = generate_card_numbers()
        marks = [[False] * 4 for _ in range(4)]
        card = {
            "_type": "card",
            "game_id": game_id,
            "card_id": _new_card_id(),
            "owner_name": owner_name,
            "owner_user_id": int(owner_user_id) if owner_user_id else None,
            "numbers": numbers,
            "marks": marks,
            "purchased_at": _now(),
        }
        db.insert(card)
        cards.append(card)

    g["pot"] = int(g["pot"]) + int(g["price"]) * len(cards)
    db.update(g, doc_ids=[g.doc_id])
    logger.info(
        f"[bingo] {owner_name} bought {len(cards)} card(s) in game {game_id} "
        f"(+{g['price']*len(cards)} {g['currency']}, pot={g['pot']})"
    )
    return cards, None

def call_number(game_id: str, number: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    n = int(number)
    if n < 1 or n > 80:
        return None, "Number must be between 1 and 80."
    g = get_game(game_id)
    if not g:
        return None, "Game not found."

    called = set(g.get("called", []))
    if n in called:
        return g, "Number already called."

    called.add(n)
    g["called"] = sorted(list(called))
    db = _open(game_id)
    db.update(g, doc_ids=[g.doc_id])
    logger.info(f"[bingo] Called number {n} in game {game_id}")
    return g, None

def mark_card(game_id: str, card_id: str, row: int, col: int) -> Tuple[bool, str]:
    db = _open(game_id)
    Card = Query()
    rows = db.search((Card._type == "card") & (Card.card_id == card_id))
    if not rows:
        return False, "Card not found."
    card = rows[-1]
    if not (0 <= row < 4 and 0 <= col < 4):
        return False, "Row/col out of range."
    card["marks"][row][col] = True
    db.update(card, doc_ids=[card.doc_id])
    return True, "Marked."

def get_public_state(game_id: str) -> Dict[str, Any]:
    g = get_game(game_id)
    if not g:
        return {"active": False}
    db = _open(game_id)
    Card = Query()
    cards = db.search((Card._type == "card") & (Card.game_id == game_id))
    pot = int(g["pot"])
    pays = _payouts(pot)
    # minimal public claim info
    claims = [
        {
            "ts": c.get("ts"),
            "owner_name": c.get("owner_name"),
            "card_id": c.get("card_id"),
            "stage": c.get("stage"),
        }
        for c in g.get("claims", [])
    ]
    return {
        "active": True,
        "game": {
            "game_id": g["game_id"],
            "channel_id": g["channel_id"],
            "title": g["title"],
            "header": g.get("header", "BING"),
            "price": g["price"],
            "currency": g["currency"],
            "max_cards_per_player": g["max_cards_per_player"],
            "pot": pot,
            "called": g["called"],
            "stage": g.get("stage", "single"),
            "payouts": pays,
            "background": (f"/bingo/assets/{g['game_id']}" if g.get("background_path") else None),
            "claims": claims,                      # NEW
        },
        "stats": {
            "cards": len(cards),
            "players": len({c["owner_name"] for c in cards}),
        },
    }


def get_card(game_id: str, card_id: str) -> Optional[Dict[str, Any]]:
    db = _open(game_id)
    Card = Query()
    rows = db.search((Card._type == "card") & (Card.card_id == card_id))
    return rows[-1] if rows else None

def get_owner_cards(
    game_id: str,
    owner_name: Optional[str] = None,
    owner_user_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    db = _open(game_id)
    Card = Query()
    q = (Card._type == "card") & (Card.game_id == game_id)
    if owner_name:
        q = q & (Card.owner_name == owner_name)
    elif owner_user_id is not None:
        q = q & (Card.owner_user_id == int(owner_user_id))
    else:
        return []
    rows = db.search(q)
    rows.sort(key=lambda c: c.get("purchased_at", 0))  # oldest first
    return rows[:10]

# -------- background handling --------
def save_background(game_id: str, src_path: str) -> Tuple[bool, str]:
    _ensure_dirs()
    g = get_game(game_id)
    if not g:
        return False, "Game not found."
    ext = os.path.splitext(src_path)[1].lower() or ".png"
    dest = os.path.join(_ASSETS, f"{game_id}{ext}")
    try:
        shutil.copyfile(src_path, dest)
    except Exception as e:
        logger.error(f"[bingo] BG upload failed: {e}", exc_info=True)
        return False, "Failed to store background."
    g["background_path"] = dest
    db = _open(game_id)
    db.update(g, doc_ids=[g.doc_id])
    return True, dest
