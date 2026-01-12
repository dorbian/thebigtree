from __future__ import annotations
import os
import json
import time
import secrets
import random
import itertools
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple

try:
    import bigtree
except Exception:
    bigtree = None

try:
    from bigtree.inc.logging import logger
except Exception:
    import logging
    logger = logging.getLogger("bigtree")

GAMES = {"blackjack", "poker", "highlow"}
_DB_PATH: Optional[str] = None
_DB_READY = False
_DB_CONFIGURED = False
_DB_LOCK = threading.RLock()
_FINISHED_TTL = 15.0

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["spades", "hearts", "diamonds", "clubs"]
RANK_VALUES = {r: i + 1 for i, r in enumerate(RANKS)}

def _now() -> float:
    return time.time()

def _get_base_dir() -> str:
    base = os.getenv("BIGTREE_CARDGAMES_DB_DIR")
    if base:
        return base
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

def _get_db_path() -> str:
    global _DB_PATH
    if _DB_PATH:
        return _DB_PATH
    base = _get_base_dir()
    if not base:
        base = "/opt/bigtree/database"
    path = os.path.join(base, "cardgames")
    os.makedirs(path, exist_ok=True)
    _DB_PATH = os.path.join(path, "cardgames.db")
    return _DB_PATH

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_get_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn

def _with_conn(fn, retries: int = 10, delay: float = 0.2):
    last_err = None
    for attempt in range(retries):
        with _DB_LOCK:
            try:
                with _connect() as conn:
                    return fn(conn)
            except sqlite3.OperationalError as exc:
                last_err = exc
                if "locked" not in str(exc).lower():
                    raise
        time.sleep(delay * (attempt + 1))
    if last_err:
        raise last_err

def _configure_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA synchronous=NORMAL")

def _ensure_column(conn: sqlite3.Connection, table: str, column: str, col_def: str) -> None:
    cols = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")

def _ensure_db() -> None:
    global _DB_READY, _DB_CONFIGURED
    if _DB_READY:
        return
    with _DB_LOCK:
        if _DB_READY:
            return
        def _init(conn):
            if not _DB_CONFIGURED:
                _configure_db(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    join_code TEXT UNIQUE,
                    priestess_token TEXT,
                    player_token TEXT,
                    game_id TEXT,
                    deck_id TEXT,
                    background_url TEXT,
                    background_artist_id TEXT,
                    background_artist_name TEXT,
                    currency TEXT,
                    status TEXT,
                    pot INTEGER,
                    winnings INTEGER,
                    state_json TEXT,
                    created_at REAL,
                    updated_at REAL
                )
                """
            )
            _ensure_column(conn, "sessions", "deck_id", "TEXT")
            _ensure_column(conn, "sessions", "background_url", "TEXT")
            _ensure_column(conn, "sessions", "background_artist_id", "TEXT")
            _ensure_column(conn, "sessions", "background_artist_name", "TEXT")
            _ensure_column(conn, "sessions", "currency", "TEXT")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    session_id TEXT,
                    seq INTEGER,
                    ts REAL,
                    type TEXT,
                    data_json TEXT,
                    PRIMARY KEY (session_id, seq)
                )
                """
            )
        _with_conn(_init, retries=15, delay=0.3)
        _DB_CONFIGURED = True
        _DB_READY = True

def _new_id() -> str:
    return secrets.token_urlsafe(10)

def _new_code() -> str:
    return secrets.token_urlsafe(5).replace("-", "").replace("_", "")[:8]

def _standard_deck() -> List[Dict[str, str]]:
    cards: List[Dict[str, str]] = []
    for suit in SUITS:
        for rank in RANKS:
            cards.append({
                "rank": rank,
                "suit": suit,
                "code": f"{rank}{suit[0].upper()}",
                "name": f"{rank} of {suit.title()}",
            })
    return cards

def _normalize_rank(value: Any) -> Optional[str]:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if text in RANKS:
        return text
    if text.isdigit():
        num = int(text)
        if num == 1:
            return "A"
        if num == 11:
            return "J"
        if num == 12:
            return "Q"
        if num == 13:
            return "K"
        if 2 <= num <= 10:
            return str(num)
    roman = {"I":1,"II":2,"III":3,"IV":4,"V":5,"VI":6,"VII":7,"VIII":8,"IX":9,"X":10,"XI":11,"XII":12,"XIII":13}
    if text in roman:
        return _normalize_rank(roman[text])
    return None

def _normalize_suit(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    if not text:
        return None
    aliases = {
        "hearts": "hearts", "heart": "hearts", "h": "hearts",
        "spades": "spades", "spade": "spades", "s": "spades",
        "clubs": "clubs", "club": "clubs", "c": "clubs",
        "diamonds": "diamonds", "diamond": "diamonds", "d": "diamonds",
    }
    return aliases.get(text)

def _extract_rank_suit(card: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    suit = _normalize_suit(card.get("suit"))
    rank = _normalize_rank(card.get("number") or card.get("rank"))
    if suit and rank:
        return rank, suit
    text = " ".join([str(card.get(k) or "") for k in ("card_id", "name", "title")]).lower()
    for candidate in ("hearts", "spades", "clubs", "diamonds"):
        if candidate in text:
            suit = candidate
            break
    rank_aliases = {
        "ace": "A",
        "king": "K",
        "queen": "Q",
        "jack": "J",
        "ten": "10",
        "nine": "9",
        "eight": "8",
        "seven": "7",
        "six": "6",
        "five": "5",
        "four": "4",
        "three": "3",
        "two": "2",
        "a": "A",
        "k": "K",
        "q": "Q",
        "j": "J",
    }
    for key, value in rank_aliases.items():
        if f" {key} " in f" {text.replace('_', ' ')} ":
            rank = _normalize_rank(value)
            break
    return rank, suit

def _load_playing_deck(deck_id: Optional[str]) -> List[Dict[str, Any]]:
    if not deck_id:
        return _standard_deck()
    try:
        from bigtree.modules import tarot
    except Exception:
        return _standard_deck()
    deck, cards = tarot.get_deck_bundle(deck_id)
    if not cards:
        raise ValueError("deck has no cards")
    seen = set()
    playing: List[Dict[str, Any]] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        rank, suit = _extract_rank_suit(card)
        if not rank or not suit:
            continue
        key = (rank, suit)
        if key in seen:
            continue
        seen.add(key)
        image = card.get("image") or card.get("img") or card.get("url") or card.get("image_url")
        name = card.get("name") or card.get("title") or card.get("card_id")
        playing.append({
            "rank": rank,
            "suit": suit,
            "code": f"{rank}{suit[0].upper()}",
            "image": image,
            "name": name or f"{rank} of {suit.title()}",
        })
    if not playing:
        raise ValueError("deck has no playing cards")
    return playing

def _get_deck_back_image(deck_id: Optional[str]) -> Optional[str]:
    if not deck_id:
        return None
    try:
        from bigtree.modules import tarot
    except Exception:
        return None
    try:
        deck, _cards = tarot.get_deck_bundle(deck_id)
    except Exception:
        return None
    if not isinstance(deck, dict):
        return None
    return deck.get("back_image") or deck.get("back") or deck.get("back_url")

def _draw(deck: List[Dict[str, str]], count: int = 1) -> List[Dict[str, str]]:
    drawn = []
    for _ in range(count):
        if not deck:
            break
        drawn.append(deck.pop(0))
    return drawn

def _blackjack_value(hand: List[Dict[str, str]]) -> int:
    total = 0
    aces = 0
    for card in hand:
        rank = card.get("rank")
        if rank == "A":
            aces += 1
            total += 11
        elif rank in ("J", "Q", "K"):
            total += 10
        else:
            total += int(rank)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total

def _init_blackjack_state(deck_id: Optional[str] = None) -> Dict[str, Any]:
    deck = _load_playing_deck(deck_id)
    random.shuffle(deck)
    return {
        "deck": deck,
        "player_hand": [],
        "player_hands": [],
        "hand_multipliers": [],
        "hand_results": [],
        "active_hand": 0,
        "dealer_hand": [],
        "status": "created",
        "result": None,
    }

def _start_blackjack(state: Dict[str, Any]) -> None:
    if state.get("status") == "live":
        return
    deck = state.get("deck") or []
    player_hand = _draw(deck, 2)
    state["player_hand"] = player_hand
    state["player_hands"] = [player_hand]
    state["hand_multipliers"] = [1]
    state["hand_results"] = [None]
    state["active_hand"] = 0
    state["dealer_hand"] = _draw(deck, 2)
    state["status"] = "live"
    state["result"] = None
    state["deck"] = deck

def _finish_blackjack(state: Dict[str, Any], result: str) -> None:
    state["status"] = "finished"
    state["result"] = result

def _advance_blackjack_hand(state: Dict[str, Any]) -> bool:
    hands = state.get("player_hands") or []
    results = state.get("hand_results") or []
    for idx in range(len(hands)):
        if idx >= len(results) or results[idx] is None:
            state["active_hand"] = idx
            return True
    return False

def _resolve_blackjack(state: Dict[str, Any]) -> None:
    deck = state.get("deck") or []
    dealer = state.get("dealer_hand") or []
    while _blackjack_value(dealer) < 17:
        dealer += _draw(deck, 1)
    state["dealer_hand"] = dealer
    state["deck"] = deck

    hands = state.get("player_hands") or []
    results = list(state.get("hand_results") or [])
    while len(results) < len(hands):
        results.append(None)
    dealer_total = _blackjack_value(dealer)
    overall = []
    for idx, hand in enumerate(hands):
        if results[idx] == "bust":
            overall.append("lose")
            continue
        player_total = _blackjack_value(hand)
        if player_total > 21:
            results[idx] = "bust"
            overall.append("lose")
            continue
        if dealer_total > 21 or player_total > dealer_total:
            results[idx] = "win"
        elif player_total < dealer_total:
            results[idx] = "lose"
        else:
            results[idx] = "push"
        overall.append(results[idx])
    state["hand_results"] = results
    state["result"] = overall[0] if overall and all(r == overall[0] for r in overall) else "mixed"
    state["status"] = "finished"

def _apply_blackjack_action(state: Dict[str, Any], action: str) -> Tuple[Dict[str, Any], Optional[str]]:
    deck = state.get("deck") or []
    hands = state.get("player_hands") or []
    results = list(state.get("hand_results") or [])
    multipliers = list(state.get("hand_multipliers") or [])
    if not hands:
        hands = [state.get("player_hand") or []]
    while len(results) < len(hands):
        results.append(None)
    while len(multipliers) < len(hands):
        multipliers.append(1)
    active = int(state.get("active_hand") or 0)
    if active < 0 or active >= len(hands):
        active = 0
    if action == "hit":
        hands[active] = (hands[active] or []) + _draw(deck, 1)
        player_total = _blackjack_value(hands[active])
        if player_total > 21:
            results[active] = "bust"
            if not _advance_blackjack_hand({"player_hands": hands, "hand_results": results, "active_hand": active, **state}):
                state["player_hands"] = hands
                state["hand_results"] = results
                state["hand_multipliers"] = multipliers
                _resolve_blackjack(state)
                return state, None
        state["player_hands"] = hands
        state["hand_results"] = results
        state["hand_multipliers"] = multipliers
        state["active_hand"] = active
        state["player_hand"] = hands[active]
        state["deck"] = deck
        return state, None
    if action == "stand":
        results[active] = results[active] or "pending"
        state["player_hands"] = hands
        state["hand_results"] = results
        state["hand_multipliers"] = multipliers
        if not _advance_blackjack_hand({"player_hands": hands, "hand_results": results, "active_hand": active, **state}):
            _resolve_blackjack(state)
        state["player_hand"] = hands[state.get("active_hand", 0)] if hands else []
        return state, None
    if action == "double":
        if len(hands[active]) != 2:
            return state, "double down requires two cards"
        multipliers[active] = 2
        hands[active] = (hands[active] or []) + _draw(deck, 1)
        if _blackjack_value(hands[active]) > 21:
            results[active] = "bust"
        else:
            results[active] = results[active] or "pending"
        state["player_hands"] = hands
        state["hand_results"] = results
        state["hand_multipliers"] = multipliers
        if not _advance_blackjack_hand({"player_hands": hands, "hand_results": results, "active_hand": active, **state}):
            _resolve_blackjack(state)
        state["player_hand"] = hands[state.get("active_hand", 0)] if hands else []
        state["deck"] = deck
        return state, None
    if action == "split":
        if len(hands) >= 2:
            return state, "already split"
        hand = hands[active]
        if len(hand) != 2:
            return state, "split requires two cards"
        if hand[0].get("rank") != hand[1].get("rank"):
            return state, "split requires matching ranks"
        left = [hand[0]] + _draw(deck, 1)
        right = [hand[1]] + _draw(deck, 1)
        state["player_hands"] = [left, right]
        state["hand_multipliers"] = [1, 1]
        state["hand_results"] = [None, None]
        state["active_hand"] = 0
        state["player_hand"] = left
        state["deck"] = deck
        return state, None
    return state, "unknown action"

def _init_highlow_state(deck_id: Optional[str] = None) -> Dict[str, Any]:
    deck = _load_playing_deck(deck_id)
    random.shuffle(deck)
    return {
        "deck": deck,
        "current": None,
        "next": None,
        "revealed": None,
        "status": "created",
        "phase": "created",
        "result": None,
        "last_result": None,
        "intent": None,
        "base_pot": 0,
        "winnings": 0,
        "pending_multiplier": 1,
        "doubles_used": 0,
        "max_doubles": 2,
    }

def _start_highlow(state: Dict[str, Any]) -> None:
    if state.get("status") == "live":
        return
    deck = state.get("deck") or []
    current = _draw(deck, 1)
    state["current"] = current[0] if current else None
    state["deck"] = deck
    state["status"] = "live"
    state["phase"] = "decision"
    state["intent"] = None
    state["pending_multiplier"] = 1

def _apply_highlow_action(state: Dict[str, Any], action: str) -> Tuple[Dict[str, Any], Optional[str]]:
    deck = state.get("deck") or []
    phase = state.get("phase") or "created"
    if state.get("status") != "live" or phase == "settlement":
        return state, "not active"
    if action == "stop":
        if int(state.get("winnings") or 0) <= 0:
            return state, "no winnings to stop"
        state["intent"] = "stop"
        state["result"] = "stopped"
        state["last_result"] = "stopped"
        state["phase"] = "settlement"
        state["pending_multiplier"] = 1
        return state, None
    if action == "double":
        if phase != "decision":
            return state, "not in decision phase"
        if int(state.get("winnings") or 0) <= 0:
            return state, "cannot double yet"
        max_doubles = int(state.get("max_doubles") or 0)
        doubles_used = int(state.get("doubles_used") or 0)
        if max_doubles and doubles_used >= max_doubles:
            return state, "max doubles reached"
        state["pending_multiplier"] = int(state.get("pending_multiplier") or 1) * 2
        state["doubles_used"] = doubles_used + 1
        state["intent"] = "double"
        return state, None
    if action not in ("higher", "lower"):
        return state, "invalid action"
    if phase != "decision":
        return state, "not in decision phase"
    if not deck or not state.get("current"):
        return state, "no cards"
    next_card = _draw(deck, 1)[0]
    state["next"] = next_card
    state["revealed"] = next_card
    state["deck"] = deck
    state["intent"] = action
    current_val = RANK_VALUES.get(state["current"]["rank"], 0)
    next_val = RANK_VALUES.get(next_card["rank"], 0)
    if action == "higher":
        state["result"] = "win" if next_val >= current_val else "lose"
    elif action == "lower":
        state["result"] = "win" if next_val <= current_val else "lose"
    else:
        return state, "invalid guess"
    state["last_result"] = state.get("result")
    base = int(state.get("winnings") or 0) or int(state.get("base_pot") or 0) or 0
    if base <= 0:
        base = 0
    multiplier = int(state.get("pending_multiplier") or 1)
    if state["result"] == "win":
        if base == 0:
            base = int(state.get("base_pot") or 0) or 0
        state["winnings"] = max(base, int(state.get("winnings") or 0)) * multiplier
    else:
        state["winnings"] = 0
    state["pending_multiplier"] = 1
    state["current"] = next_card
    state["next"] = None
    state["phase"] = "decision"
    return state, None

def _init_poker_state(deck_id: Optional[str] = None) -> Dict[str, Any]:
    deck = _load_playing_deck(deck_id)
    random.shuffle(deck)
    return {
        "deck": deck,
        "player_hand": [],
        "dealer_hand": [],
        "community": [],
        "stage": "created",
        "status": "created",
        "result": None,
        "winner": None,
        "player_rank": None,
        "dealer_rank": None,
        "pot": 0,
        "player_commit": 0,
        "dealer_commit": 0,
        "last_action": None,
        "ended_reason": None,
    }

def _start_poker(state: Dict[str, Any]) -> None:
    if state.get("status") == "live":
        return
    deck = state.get("deck") or []
    state["player_hand"] = _draw(deck, 2)
    state["dealer_hand"] = _draw(deck, 2)
    state["community"] = []
    state["stage"] = "preflop"
    state["status"] = "live"
    state["deck"] = deck
    state["player_commit"] = int(state.get("player_commit") or 0)
    state["dealer_commit"] = int(state.get("dealer_commit") or 0)
    state["pot"] = int(state.get("pot") or 0)
    state["last_action"] = None
    state["ended_reason"] = None

def _is_straight(values: List[int]) -> Tuple[bool, int]:
    unique = sorted(set(values))
    if len(unique) < 5:
        return False, 0
    for i in range(len(unique) - 4):
        window = unique[i:i + 5]
        if window == list(range(window[0], window[0] + 5)):
            return True, window[-1]
    if set([14, 2, 3, 4, 5]).issubset(set(unique)):
        return True, 5
    return False, 0

def _poker_hand_rank_5(cards: List[Dict[str, str]]) -> Tuple[int, List[int], str]:
    values = [RANK_VALUES.get(c.get("rank"), 0) for c in cards]
    values = [14 if v == 1 else v for v in values]
    values.sort(reverse=True)
    suits = [c.get("suit") for c in cards]
    counts: Dict[int, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    count_items = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    count_values = sorted(counts.values(), reverse=True)
    is_flush = len(set(suits)) == 1
    straight, straight_high = _is_straight(values)
    if is_flush and straight:
        return 8, [straight_high], "straight_flush"
    if 4 in count_values:
        four = next(v for v, c in count_items if c == 4)
        kicker = max(v for v, c in count_items if c == 1)
        return 7, [four, kicker], "four_kind"
    if count_values == [3, 2]:
        three = next(v for v, c in count_items if c == 3)
        pair = next(v for v, c in count_items if c == 2)
        return 6, [three, pair], "full_house"
    if is_flush:
        return 5, values, "flush"
    if straight:
        return 4, [straight_high], "straight"
    if 3 in count_values:
        three = next(v for v, c in count_items if c == 3)
        kickers = [v for v, c in count_items if c == 1]
        return 3, [three] + kickers, "three_kind"
    if count_values == [2, 2, 1]:
        pairs = [v for v, c in count_items if c == 2]
        kicker = next(v for v, c in count_items if c == 1)
        return 2, pairs + [kicker], "two_pair"
    if 2 in count_values:
        pair = next(v for v, c in count_items if c == 2)
        kickers = [v for v, c in count_items if c == 1]
        return 1, [pair] + kickers, "pair"
    return 0, values, "high_card"

def _best_poker_hand(cards: List[Dict[str, str]]) -> Tuple[str, Tuple[int, List[int]]]:
    best_score: Optional[Tuple[int, List[int]]] = None
    best_rank = "high_card"
    for combo in itertools.combinations(cards, 5):
        score, tie, name = _poker_hand_rank_5(list(combo))
        current = (score, tie)
        if best_score is None or current > best_score:
            best_score = current
            best_rank = name
    return best_rank, best_score or (0, [])

def _advance_poker(state: Dict[str, Any]) -> None:
    if state.get("status") != "live":
        return
    deck = state.get("deck") or []
    stage = state.get("stage") or "preflop"
    if stage == "preflop":
        state["community"] = _draw(deck, 3)
        state["stage"] = "flop"
    elif stage == "flop":
        state["community"] = (state.get("community") or []) + _draw(deck, 1)
        state["stage"] = "turn"
    elif stage == "turn":
        state["community"] = (state.get("community") or []) + _draw(deck, 1)
        state["stage"] = "river"
    elif stage == "river":
        state["stage"] = "showdown"
        player = (state.get("player_hand") or []) + (state.get("community") or [])
        dealer = (state.get("dealer_hand") or []) + (state.get("community") or [])
        player_rank, player_score = _best_poker_hand(player)
        dealer_rank, dealer_score = _best_poker_hand(dealer)
        state["player_rank"] = player_rank
        state["dealer_rank"] = dealer_rank
        if player_score > dealer_score:
            state["winner"] = "player"
        elif dealer_score > player_score:
            state["winner"] = "dealer"
        else:
            state["winner"] = "push"
        state["result"] = state["winner"]
        state["status"] = "finished"
    state["deck"] = deck

def _apply_poker_action(state: Dict[str, Any], action: str, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    if state.get("status") != "live":
        return state, "not active"
    stage = state.get("stage") or "preflop"
    if stage not in ("preflop", "flop", "turn", "river"):
        return state, "no actions allowed"
    action = str(action or "").strip().lower()
    if action not in ("check", "call", "bet", "raise", "fold"):
        return state, "invalid action"
    if action == "fold":
        state["status"] = "finished"
        state["result"] = "dealer"
        state["winner"] = "dealer"
        state["ended_reason"] = "fold"
        state["last_action"] = {"actor": "player", "action": "fold", "amount": 0, "stage": stage}
        return state, None
    amount = 0
    if action in ("bet", "raise"):
        try:
            amount = int(payload.get("amount") or 0)
        except Exception:
            amount = 0
        if amount <= 0:
            return state, "invalid bet"
        state["player_commit"] = int(state.get("player_commit") or 0) + amount
        state["dealer_commit"] = int(state.get("dealer_commit") or 0) + amount
        state["pot"] = int(state.get("pot") or 0) + (amount * 2)
    state["last_action"] = {"actor": "player", "action": action, "amount": amount, "stage": stage}
    _advance_poker(state)
    return state, None

def _init_state(game_id: str, deck_id: Optional[str]) -> Dict[str, Any]:
    if game_id == "blackjack":
        return _init_blackjack_state(deck_id)
    if game_id == "poker":
        return _init_poker_state(deck_id)
    if game_id == "highlow":
        return _init_highlow_state(deck_id)
    raise ValueError("invalid game")

def _start_game(game_id: str, state: Dict[str, Any]) -> None:
    if game_id == "blackjack":
        _start_blackjack(state)
    elif game_id == "poker":
        _start_poker(state)
    elif game_id == "highlow":
        _start_highlow(state)

def _apply_action(game_id: str, state: Dict[str, Any], action: str, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    if game_id == "blackjack":
        return _apply_blackjack_action(state, action)
    if game_id == "poker":
        return _apply_poker_action(state, action, payload)
    if game_id == "highlow":
        choice = ""
        if action == "guess":
            choice = str(payload.get("guess") or "")
        else:
            choice = str(action or "")
        return _apply_highlow_action(state, choice)
    return state, "invalid game"

def _poker_visible_community(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    community = list(state.get("community") or [])
    stage = state.get("stage") or "preflop"
    if stage in ("created", "preflop"):
        return []
    if stage == "flop":
        return community[:3]
    if stage == "turn":
        return community[:4]
    return community

def _session_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    deck_id = None
    background_url = None
    background_artist_id = None
    background_artist_name = None
    currency = None
    try:
        deck_id = row["deck_id"]
    except Exception:
        deck_id = None
    try:
        background_url = row["background_url"]
    except Exception:
        background_url = None
    try:
        background_artist_id = row["background_artist_id"]
    except Exception:
        background_artist_id = None
    try:
        background_artist_name = row["background_artist_name"]
    except Exception:
        background_artist_name = None
    try:
        currency = row["currency"]
    except Exception:
        currency = None
    return {
        "session_id": row["session_id"],
        "join_code": row["join_code"],
        "priestess_token": row["priestess_token"],
        "player_token": row["player_token"],
        "game_id": row["game_id"],
        "deck_id": deck_id,
        "background_url": background_url,
        "background_artist_id": background_artist_id,
        "background_artist_name": background_artist_name,
        "currency": currency,
        "status": row["status"],
        "pot": int(row["pot"] or 0),
        "winnings": int(row["winnings"] or 0),
        "state": json.loads(row["state_json"] or "{}"),
        "created_at": float(row["created_at"] or 0),
        "updated_at": float(row["updated_at"] or 0),
    }

def _delete_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

def _cleanup_finished(conn: sqlite3.Connection) -> None:
    now = _now()
    rows = conn.execute(
        "SELECT session_id, updated_at FROM sessions WHERE status = 'finished'"
    ).fetchall()
    for row in rows:
        updated = float(row["updated_at"] or 0)
        if now - updated >= _FINISHED_TTL:
            _delete_session(conn, row["session_id"])

def create_session(
    game_id: str,
    pot: int = 0,
    deck_id: Optional[str] = None,
    background_url: Optional[str] = None,
    background_artist_id: Optional[str] = None,
    background_artist_name: Optional[str] = None,
    currency: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    game_id = str(game_id or "").strip().lower()
    if game_id not in GAMES:
        raise ValueError("invalid game")
    _ensure_db()
    session_id = _new_id()
    join_code = _new_code()
    priestess_token = _new_id()
    deck_id = (deck_id or "").strip() or None
    background_url = (background_url or "").strip() or None
    background_artist_id = (background_artist_id or "").strip() or None
    background_artist_name = (background_artist_name or "").strip() or None
    currency = (currency or "").strip() or None
    status = str(status or "").strip().lower() or "created"
    if status not in ("created", "draft"):
        status = "created"
    state = _init_state(game_id, deck_id)
    now = _now()
    def _insert(conn):
        conn.execute(
            """
            INSERT INTO sessions (session_id, join_code, priestess_token, player_token, game_id, deck_id, background_url, background_artist_id, background_artist_name, currency, status, pot, winnings, state_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, join_code, priestess_token, None, game_id, deck_id, background_url, background_artist_id, background_artist_name, currency, status, int(pot or 0), 0, json.dumps(state), now, now)
        )
    _with_conn(_insert)
    _add_event(session_id, "SESSION_CREATED", {"join_code": join_code, "game_id": game_id})
    return get_session_by_id(session_id) or {}

def list_sessions(game_id: Optional[str] = None) -> List[Dict[str, Any]]:
    _ensure_db()
    def _load(conn):
        _cleanup_finished(conn)
        if game_id:
            return conn.execute(
                "SELECT * FROM sessions WHERE game_id = ? AND status != 'finished' ORDER BY created_at DESC",
                (game_id,),
            ).fetchall()
        return conn.execute("SELECT * FROM sessions WHERE status != 'finished' ORDER BY created_at DESC").fetchall()
    rows = _with_conn(_load)
    return [_session_from_row(row) for row in rows]

def get_session_by_join_code(join_code: str) -> Optional[Dict[str, Any]]:
    _ensure_db()
    def _load(conn):
        _cleanup_finished(conn)
        return conn.execute("SELECT * FROM sessions WHERE join_code = ?", (join_code,)).fetchone()
    row = _with_conn(_load)
    if not row:
        return None
    s = _session_from_row(row)
    if s.get("status") == "finished":
        return None
    return s

def get_session_by_id(session_id: str) -> Optional[Dict[str, Any]]:
    _ensure_db()
    def _load(conn):
        _cleanup_finished(conn)
        return conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    row = _with_conn(_load)
    if not row:
        return None
    s = _session_from_row(row)
    if s.get("status") == "finished":
        return None
    return s

def _update_session(session_id: str, payload: Dict[str, Any]) -> None:
    _ensure_db()
    now = _now()
    def _update(conn):
        conn.execute(
            "UPDATE sessions SET status = ?, pot = ?, winnings = ?, state_json = ?, updated_at = ? WHERE session_id = ?",
            (payload.get("status"), int(payload.get("pot") or 0), int(payload.get("winnings") or 0), json.dumps(payload.get("state") or {}), now, session_id)
        )
    _with_conn(_update)

def join_session(join_code: str) -> Dict[str, Any]:
    s = get_session_by_join_code(join_code)
    if not s:
        raise ValueError("not found")
    token = _new_id()
    def _update(conn):
        conn.execute("UPDATE sessions SET player_token = ?, updated_at = ? WHERE session_id = ?", (token, _now(), s["session_id"]))
    _with_conn(_update)
    _add_event(s["session_id"], "PLAYER_JOINED", {})
    s["player_token"] = token
    return {"player_token": token, "session": s}

def _add_event(session_id: str, event_type: str, data: Dict[str, Any]) -> None:
    _ensure_db()
    def _insert(conn):
        row = conn.execute("SELECT MAX(seq) AS max_seq FROM events WHERE session_id = ?", (session_id,)).fetchone()
        seq = int(row["max_seq"] or 0) + 1
        conn.execute(
            "INSERT INTO events (session_id, seq, ts, type, data_json) VALUES (?, ?, ?, ?, ?)",
            (session_id, seq, _now(), event_type, json.dumps(data or {}))
        )
    _with_conn(_insert)

def list_events(session_id: str, since_seq: int) -> List[Dict[str, Any]]:
    _ensure_db()
    def _load(conn):
        return conn.execute(
            "SELECT seq, ts, type, data_json FROM events WHERE session_id = ? AND seq > ? ORDER BY seq ASC",
            (session_id, int(since_seq))
        ).fetchall()
    rows = _with_conn(_load)
    return [{
        "seq": int(r["seq"]),
        "ts": float(r["ts"] or 0),
        "type": r["type"],
        "data": json.loads(r["data_json"] or "{}"),
    } for r in rows]

def start_session(session_id: str, token: str) -> Dict[str, Any]:
    s = get_session_by_id(session_id)
    if not s:
        raise ValueError("not found")
    if token != s.get("priestess_token"):
        raise PermissionError("unauthorized")
    state = s.get("state") or {}
    if s.get("game_id") == "poker":
        state["pot"] = int(s.get("pot") or 0)
    if s.get("game_id") == "highlow" and not state.get("base_pot"):
        state["base_pot"] = int(s.get("pot") or 0)
    _start_game(s["game_id"], state)
    s["status"] = "live"
    s["state"] = state
    _update_session(session_id, s)
    _add_event(session_id, "SESSION_STARTED", {})
    return s

def finish_session(session_id: str, token: str) -> Dict[str, Any]:
    s = get_session_by_id(session_id)
    if not s:
        raise ValueError("not found")
    if token != s.get("priestess_token"):
        raise PermissionError("unauthorized")
    s["status"] = "finished"
    _update_session(session_id, s)
    _add_event(session_id, "SESSION_FINISHED", {})
    def _delete(conn):
        _delete_session(conn, session_id)
    _with_conn(_delete)
    return s

def host_action(session_id: str, token: str, action: str) -> Dict[str, Any]:
    s = get_session_by_id(session_id)
    if not s:
        raise ValueError("not found")
    if token != s.get("priestess_token"):
        raise PermissionError("unauthorized")
    state = s.get("state") or {}
    if s.get("game_id") == "blackjack" and action in ("hit", "stand", "double", "split"):
        if s.get("status") != "live":
            raise ValueError("session not live")
        updated, err = _apply_action(s["game_id"], state, action, {})
        if err:
            raise ValueError(err)
        s["state"] = updated
        if updated.get("status") == "finished":
            result = updated.get("result")
            pot = int(s.get("pot") or 0)
            winnings = 0
            results = updated.get("hand_results") or []
            multipliers = updated.get("hand_multipliers") or []
            if not results and result:
                results = [result]
            for idx, hand_result in enumerate(results):
                if hand_result not in ("win", "push"):
                    continue
                multiplier = 1
                if idx < len(multipliers):
                    try:
                        multiplier = int(multipliers[idx] or 1)
                    except Exception:
                        multiplier = 1
                if hand_result == "win":
                    winnings += pot * max(1, multiplier)
                else:
                    winnings += int(pot * max(1, multiplier) / 2)
            s["winnings"] = winnings
        _update_session(session_id, s)
        _add_event(session_id, "STATE_UPDATED", {"action": action})
        return s
    if s.get("game_id") == "poker" and action == "advance":
        _advance_poker(state)
        if state.get("status") == "finished":
            pot = int(s.get("pot") or 0)
            result = state.get("result")
            if result == "player":
                s["winnings"] = pot
            elif result == "push":
                s["winnings"] = int(pot / 2)
            else:
                s["winnings"] = 0
        s["state"] = state
        _update_session(session_id, s)
        _add_event(session_id, "STATE_UPDATED", {"action": action})
        return s
    if s.get("game_id") == "highlow" and action in ("higher", "lower", "double", "stop"):
        if not state.get("base_pot"):
            state["base_pot"] = int(s.get("pot") or 0)
        updated, err = _apply_highlow_action(state, action)
        if err:
            raise ValueError(err)
        s["state"] = updated
        s["winnings"] = int(updated.get("winnings") or 0)
        _update_session(session_id, s)
        _add_event(session_id, "STATE_UPDATED", {"action": action})
        return s
    raise ValueError("invalid action")

def player_action(session_id: str, token: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    s = get_session_by_id(session_id)
    if not s:
        raise ValueError("not found")
    if token != s.get("player_token"):
        raise PermissionError("unauthorized")
    state = s.get("state") or {}
    if s.get("game_id") == "highlow" and not state.get("base_pot"):
        state["base_pot"] = int(s.get("pot") or 0)
    if s.get("status") != "live":
        raise ValueError("session not live")
    updated, err = _apply_action(s["game_id"], state, action, payload or {})
    if err:
        raise ValueError(err)
    s["state"] = updated
    if s.get("game_id") == "highlow":
        s["winnings"] = int(updated.get("winnings") or 0)
    if s.get("game_id") == "poker":
        s["pot"] = int(updated.get("pot") or s.get("pot") or 0)
    if updated.get("status") == "finished":
        result = updated.get("result")
        pot = int(s.get("pot") or 0)
        winnings = 0
        if s.get("game_id") == "poker":
            if result == "player":
                winnings = pot
            elif result == "push":
                winnings = int(pot / 2)
        elif s.get("game_id") == "blackjack":
            results = updated.get("hand_results") or []
            multipliers = updated.get("hand_multipliers") or []
            if not results and result:
                results = [result]
            for idx, hand_result in enumerate(results):
                if hand_result not in ("win", "push"):
                    continue
                multiplier = 1
                if idx < len(multipliers):
                    try:
                        multiplier = int(multipliers[idx] or 1)
                    except Exception:
                        multiplier = 1
                if hand_result == "win":
                    winnings += pot * max(1, multiplier)
                else:
                    winnings += int(pot * max(1, multiplier) / 2)
        else:
            if result == "win":
                winnings = pot
            elif result == "push":
                winnings = int(pot / 2)
        s["winnings"] = winnings
    _update_session(session_id, s)
    _add_event(session_id, "STATE_UPDATED", {"action": action})
    return s

def _background_artist_payload(artist_id: Optional[str], artist_name: Optional[str]) -> Dict[str, Any]:
    if artist_id:
        try:
            from bigtree.modules import artists
            artist = artists.get_artist(artist_id)
        except Exception:
            artist = None
        if artist:
            return {
                "artist_id": artist.get("artist_id"),
                "name": artist.get("name") or artist_name or "Forest",
                "links": artist.get("links") or {},
            }
    name = (artist_name or "").strip()
    if name:
        return {"artist_id": artist_id, "name": name, "links": {}}
    return {"artist_id": None, "name": "Forest", "links": {}}

def get_state(session: Dict[str, Any], view: str = "player") -> Dict[str, Any]:
    state = session.get("state") or {}
    game_id = session.get("game_id")
    if game_id == "blackjack" and view != "priestess":
        dealer = list(state.get("dealer_hand") or [])
        if session.get("status") == "live" and len(dealer) > 1:
            back_image = _get_deck_back_image(session.get("deck_id"))
            hidden_card = {"rank": "?", "suit": "hidden", "code": "??"}
            if back_image:
                hidden_card["image"] = back_image
            dealer = [dealer[0], hidden_card]
        state = dict(state)
        state["dealer_hand"] = dealer
    if game_id == "poker" and view != "priestess":
        state = dict(state)
        back_image = _get_deck_back_image(session.get("deck_id")) or ""
        dealer_hand = list(state.get("dealer_hand") or [])
        state["dealer_hand_count"] = len(dealer_hand)
        state["dealer_hand_back"] = back_image
        stage = state.get("stage") or ""
        if stage != "showdown" and (state.get("status") or "") != "finished":
            state["dealer_hand"] = []
        state["community"] = _poker_visible_community(state)
    if game_id == "poker" and view == "priestess":
        state = dict(state)
        back_image = _get_deck_back_image(session.get("deck_id")) or ""
        player_hand = list(state.get("player_hand") or [])
        state["player_hand_count"] = len(player_hand)
        state["player_hand_back"] = back_image
        stage = state.get("stage") or ""
        if stage != "showdown" and (state.get("status") or "") != "finished":
            state["player_hand"] = []
    return {
        "session": {
            "session_id": session.get("session_id"),
            "join_code": session.get("join_code"),
            "game_id": game_id,
            "deck_id": session.get("deck_id"),
            "currency": session.get("currency"),
            "background_url": session.get("background_url"),
            "background_artist": _background_artist_payload(
                session.get("background_artist_id"),
                session.get("background_artist_name"),
            ),
            "status": session.get("status"),
            "pot": int(session.get("pot") or 0),
            "winnings": int(session.get("winnings") or 0),
            "created_at": session.get("created_at"),
        },
        "state": state,
    }
def delete_session(session_id: str, token: Optional[str] = None) -> None:
    _ensure_db()
    if token:
        s = get_session_by_id(session_id)
        if not s:
            raise ValueError("not found")
        if token != s.get("priestess_token"):
            raise PermissionError("unauthorized")
    def _delete(conn):
        _delete_session(conn, session_id)
    _with_conn(_delete)
