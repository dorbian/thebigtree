# bigtree/modules/tarot.py
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from tinydb import TinyDB, Query
import secrets, time
import bigtree

def _db() -> TinyDB:
    tarot_db_path = bigtree.config.config["BOT"]["tarot_db"]
    Path(tarot_db_path).parent.mkdir(parents=True, exist_ok=True)
    return TinyDB(tarot_db_path)

def add_card(deck: str, title: str, meaning: str, image_url: str = "", tags=None) -> int:
    db = _db()
    return db.insert({"_type":"card","deck":deck,"title":title,"meaning":meaning,"image":image_url,"tags":tags or []})

def list_cards(deck: str) -> List[Dict[str, Any]]:
    db = _db(); q = Query()
    return db.search((q._type == "card") & (q.deck == deck))

def new_session(owner_id: int, deck: str, spread: str = "single") -> str:
    db = _db()
    sid = secrets.token_urlsafe(8)
    db.insert({"_type":"session","sid":sid,"owner":owner_id,"deck":deck,"spread":spread,"state":{"drawn":[],"flipped":[]},"created":int(time.time())})
    return sid

def get_session(sid: str) -> Optional[Dict[str, Any]]:
    db = _db(); q = Query()
    return db.get((q._type=="session") & (q.sid==sid))

def update_session(sid: str, fn: Callable[[Dict[str, Any]], Dict[str, Any] | None]) -> Optional[Dict[str, Any]]:
    db = _db(); q = Query()
    s = get_session(sid)
    if not s: return None
    ns = fn(s) or s
    db.update(ns, (q._type=="session") & (q.sid==sid))
    return ns

def end_session(sid: str) -> None:
    db = _db(); q = Query()
    db.remove((q._type=="session") & (q.sid==sid))

def draw_cards(sid: str, count: int = 1) -> List[Dict[str, Any]]:
    s = get_session(sid); 
    if not s: return []
    deck = s["deck"]
    all_cards = list_cards(deck)
    have = {c["title"] for c in s["state"]["drawn"]}
    remaining = [c for c in all_cards if c["title"] not in have]
    drawn = remaining[:max(1, min(10, count))]
    def _apply(x):
        x["state"]["drawn"].extend(drawn); 
        return x
    update_session(sid, _apply)
    return drawn

def flip_card(sid: str, index: int) -> Optional[Dict[str, Any]]:
    s = get_session(sid)
    if not s: return None
    if index < 0 or index >= len(s["state"]["drawn"]):
        return None
    if index not in s["state"]["flipped"]:
        def _apply(x):
            x["state"]["flipped"].append(index)
            return x
        update_session(sid, _apply)
    return get_session(sid)

def user_is_priestish(member) -> bool:
    conf = bigtree.config.config["BOT"]
    priest = set(map(int, conf.get("priest_role_ids", [])))
    elfmin = set(map(int, conf.get("elfministrator_role_ids", [])))
    roles = {r.id for r in getattr(member, "roles", [])}
    return bool(priest & roles or elfmin & roles or member.guild_permissions.administrator)
