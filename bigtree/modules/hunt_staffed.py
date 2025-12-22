# bigtree/modules/hunt_staffed.py
# Staffed scavenger hunt logic & persistence using TinyDB

import os
import uuid
import time
import secrets
from typing import Dict, Any, List, Optional, Tuple
from tinydb import TinyDB, Query

try:
    from bigtree.inc.logging import logger
except Exception:
    import logging
    logger = logging.getLogger("bigtree")

_HUNT_DIR: Optional[str] = None
_DB_DIR: Optional[str] = None
_INDEX: Optional[str] = None

def _now() -> float:
    return time.time()

def _get_workingdir() -> str:
    env_data = os.getenv("BIGTREE__BOT__DATA_DIR") or os.getenv("BIGTREE_DATA_DIR")
    if env_data:
        return os.path.join(env_data, "hunts")
    env = os.getenv("BIGTREE_WORKDIR")
    if env:
        return os.path.join(env, "hunts")
    try:
        import bigtree
        try:
            settings = getattr(bigtree, "settings", None)
            data_dir = settings.get("BOT.DATA_DIR", None, str) if settings else None
            if data_dir:
                return os.path.join(data_dir, "hunts")
        except Exception:
            pass
        wd = getattr(bigtree, "workingdir", None)
        if wd:
            return os.path.join(wd, "hunts")
    except Exception:
        pass
    return os.path.join(os.getcwd(), ".bigtree", "hunts")

def _ensure_dirs():
    global _HUNT_DIR, _DB_DIR, _INDEX
    if _HUNT_DIR is not None:
        return
    base = _get_workingdir()
    db = os.path.join(base, "db")
    os.makedirs(db, exist_ok=True)
    _HUNT_DIR = base
    _DB_DIR = db
    _INDEX = os.path.join(base, "index.json")

def _db_path(hunt_id: str) -> str:
    _ensure_dirs()
    return os.path.join(_DB_DIR, f"{hunt_id}.json")

def _open(hunt_id: str) -> TinyDB:
    _ensure_dirs()
    return TinyDB(_db_path(hunt_id))

def _new_id() -> str:
    return uuid.uuid4().hex

def _read_index() -> Dict[str, Any]:
    _ensure_dirs()
    try:
        import json
        if os.path.exists(_INDEX):
            with open(_INDEX, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("join_codes", {})
                    return data
    except Exception:
        pass
    return {"join_codes": {}}

def _write_index(idx: Dict[str, Any]):
    _ensure_dirs()
    import json
    with open(_INDEX, "w", encoding="utf-8") as f:
        json.dump(idx, f, indent=2)

def _register_join_code(hunt_id: str) -> str:
    idx = _read_index()
    join_codes = idx.setdefault("join_codes", {})
    for code, hid in join_codes.items():
        if hid == hunt_id:
            return code
    while True:
        code = secrets.token_urlsafe(5).replace("-", "").replace("_", "")[:8]
        if code and code not in join_codes:
            join_codes[code] = hunt_id
            _write_index(idx)
            return code

def resolve_join_code(code: str) -> Optional[str]:
    if not code:
        return None
    idx = _read_index()
    return idx.get("join_codes", {}).get(code)

def create_hunt(
    title: str,
    territory_id: int,
    created_by: int,
    description: Optional[str] = None,
    rules: Optional[str] = None,
    allow_implicit_groups: bool = True,
) -> Dict[str, Any]:
    _ensure_dirs()
    hunt_id = _new_id()
    hunt = {
        "_type": "hunt",
        "hunt_id": hunt_id,
        "title": (title or "").strip() or "Scavenger Hunt",
        "description": (description or "").strip() or None,
        "rules": (rules or "").strip() or None,
        "territory_id": int(territory_id),
        "created_by": int(created_by),
        "created_at": _now(),
        "started": False,
        "ended": False,
        "active": True,
        "allow_implicit_groups": bool(allow_implicit_groups),
    }
    db = _open(hunt_id)
    db.insert(hunt)
    code = _register_join_code(hunt_id)
    hunt["join_code"] = code
    db.update(hunt, doc_ids=[hunt.doc_id])
    logger.info(f"[hunt] Created hunt {hunt_id} (join_code={code})")
    return hunt

def get_hunt(hunt_id: str) -> Optional[Dict[str, Any]]:
    if not hunt_id:
        return None
    if not os.path.exists(_db_path(hunt_id)):
        return None
    db = _open(hunt_id)
    rows = db.search(Query()._type == "hunt")
    if not rows:
        return None
    h = rows[-1]
    if "join_code" not in h:
        h["join_code"] = _register_join_code(hunt_id)
        db.update(h, doc_ids=[h.doc_id])
    return h

def list_hunts() -> List[Dict[str, Any]]:
    _ensure_dirs()
    hunts: List[Dict[str, Any]] = []
    for name in os.listdir(_DB_DIR):
        if not name.endswith(".json"):
            continue
        hunt_id = name[:-5]
        h = get_hunt(hunt_id)
        if not h:
            continue
        hunts.append({
            "hunt_id": h.get("hunt_id"),
            "title": h.get("title"),
            "territory_id": h.get("territory_id"),
            "created_at": h.get("created_at"),
            "active": h.get("active", False),
            "started": h.get("started", False),
            "ended": h.get("ended", False),
        })
    hunts.sort(key=lambda x: x.get("created_at") or 0, reverse=True)
    return hunts

def start_hunt(hunt_id: str) -> Tuple[bool, str]:
    h = get_hunt(hunt_id)
    if not h:
        return False, "Hunt not found."
    if h.get("ended"):
        return False, "Hunt already ended."
    h["started"] = True
    h["active"] = True
    db = _open(hunt_id)
    db.update(h, doc_ids=[h.doc_id])
    logger.info(f"[hunt] Started hunt {hunt_id}")
    return True, "OK"

def end_hunt(hunt_id: str) -> Tuple[bool, str]:
    h = get_hunt(hunt_id)
    if not h:
        return False, "Hunt not found."
    h["ended"] = True
    h["active"] = False
    db = _open(hunt_id)
    db.update(h, doc_ids=[h.doc_id])
    logger.info(f"[hunt] Ended hunt {hunt_id}")
    return True, "OK"

def add_checkpoint(
    hunt_id: str,
    label: str,
    territory_id: int,
    pos: Dict[str, float],
    radius_m: float,
) -> Dict[str, Any]:
    h = get_hunt(hunt_id)
    if not h:
        raise ValueError("Hunt not found.")
    checkpoint = {
        "_type": "checkpoint",
        "hunt_id": hunt_id,
        "checkpoint_id": _new_id(),
        "label": (label or "").strip() or "Checkpoint",
        "territory_id": int(territory_id),
        "pos": {
            "x": float(pos.get("x", 0)),
            "y": float(pos.get("y", 0)),
            "z": float(pos.get("z", 0)),
        },
        "radius_m": float(radius_m),
        "claimed_by": [],
        "created_at": _now(),
    }
    db = _open(hunt_id)
    db.insert(checkpoint)
    return checkpoint

def list_checkpoints(hunt_id: str) -> List[Dict[str, Any]]:
    db = _open(hunt_id)
    Row = Query()
    rows = db.search((Row._type == "checkpoint") & (Row.hunt_id == hunt_id))
    rows.sort(key=lambda c: c.get("created_at", 0))
    return rows

def get_checkpoint(hunt_id: str, checkpoint_id: str) -> Optional[Dict[str, Any]]:
    db = _open(hunt_id)
    Row = Query()
    rows = db.search((Row._type == "checkpoint") & (Row.hunt_id == hunt_id) & (Row.checkpoint_id == checkpoint_id))
    return rows[-1] if rows else None

def staff_join(hunt_id: str, staff_name: str, staff_id: Optional[str] = None) -> Dict[str, Any]:
    h = get_hunt(hunt_id)
    if not h:
        raise ValueError("Hunt not found.")
    staff_name = (staff_name or "").strip() or "Staff"
    db = _open(hunt_id)
    Row = Query()
    if staff_id:
        rows = db.search((Row._type == "staff") & (Row.staff_id == staff_id))
        if rows:
            staff = rows[-1]
            staff["name"] = staff_name
            db.update(staff, doc_ids=[staff.doc_id])
            return staff
    staff = {
        "_type": "staff",
        "hunt_id": hunt_id,
        "staff_id": staff_id or _new_id(),
        "name": staff_name,
        "checkpoint_id": None,
        "joined_at": _now(),
    }
    db.insert(staff)
    return staff

def list_staff(hunt_id: str) -> List[Dict[str, Any]]:
    db = _open(hunt_id)
    Row = Query()
    rows = db.search((Row._type == "staff") & (Row.hunt_id == hunt_id))
    rows.sort(key=lambda s: s.get("joined_at", 0))
    return rows

def claim_checkpoint(hunt_id: str, staff_id: str, checkpoint_id: str) -> Tuple[bool, str]:
    db = _open(hunt_id)
    Row = Query()
    staff_rows = db.search((Row._type == "staff") & (Row.staff_id == staff_id))
    if not staff_rows:
        return False, "Staff not found."
    cp_rows = db.search((Row._type == "checkpoint") & (Row.checkpoint_id == checkpoint_id))
    if not cp_rows:
        return False, "Checkpoint not found."
    staff = staff_rows[-1]
    checkpoint = cp_rows[-1]
    staff["checkpoint_id"] = checkpoint_id
    db.update(staff, doc_ids=[staff.doc_id])
    claimed = checkpoint.get("claimed_by") or []
    if staff_id not in claimed:
        claimed.append(staff_id)
        checkpoint["claimed_by"] = claimed
        db.update(checkpoint, doc_ids=[checkpoint.doc_id])
    return True, "OK"

def _get_group(hunt_id: str, group_id: str) -> Optional[Dict[str, Any]]:
    db = _open(hunt_id)
    Row = Query()
    rows = db.search((Row._type == "group") & (Row.hunt_id == hunt_id) & (Row.group_id == group_id))
    return rows[-1] if rows else None

def create_group(
    hunt_id: str,
    group_id: Optional[str],
    name: Optional[str],
    captain_name: Optional[str] = None,
) -> Dict[str, Any]:
    if not group_id:
        group_id = secrets.token_urlsafe(4).replace("-", "").replace("_", "")[:6].upper()
    group = {
        "_type": "group",
        "hunt_id": hunt_id,
        "group_id": group_id,
        "name": (name or "").strip() or group_id,
        "captain_name": (captain_name or "").strip() or None,
        "score": 0,
        "visited_checkpoints": [],
        "created_at": _now(),
    }
    db = _open(hunt_id)
    db.insert(group)
    return group

def list_groups(hunt_id: str) -> List[Dict[str, Any]]:
    db = _open(hunt_id)
    Row = Query()
    rows = db.search((Row._type == "group") & (Row.hunt_id == hunt_id))
    rows.sort(key=lambda g: g.get("created_at", 0))
    return rows

def record_checkin(
    hunt_id: str,
    group_id: str,
    checkpoint_id: str,
    staff_id: str,
    evidence: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    h = get_hunt(hunt_id)
    if not h:
        return False, "Hunt not found.", None
    if not h.get("active", True):
        return False, "Hunt is not active.", None
    if not h.get("started"):
        return False, "Hunt has not started.", None

    db = _open(hunt_id)
    Row = Query()
    staff = db.search((Row._type == "staff") & (Row.staff_id == staff_id))
    if not staff:
        return False, "Staff not found.", None
    checkpoint = db.search((Row._type == "checkpoint") & (Row.checkpoint_id == checkpoint_id))
    if not checkpoint:
        return False, "Checkpoint not found.", None

    group = _get_group(hunt_id, group_id)
    if not group:
        if h.get("allow_implicit_groups", True):
            group = create_group(hunt_id, group_id, group_id, None)
        else:
            return False, "Group not found.", None

    visited = set(group.get("visited_checkpoints") or [])
    if checkpoint_id in visited:
        return False, "Group already checked in here.", None

    visited.add(checkpoint_id)
    group["visited_checkpoints"] = sorted(list(visited))
    group["score"] = int(group.get("score", 0)) + 1
    db.update(group, doc_ids=[group.doc_id])

    checkin = {
        "_type": "checkin",
        "hunt_id": hunt_id,
        "checkin_id": _new_id(),
        "group_id": group_id,
        "checkpoint_id": checkpoint_id,
        "staff_id": staff_id,
        "ts": _now(),
        "evidence": evidence or {},
    }
    db.insert(checkin)
    return True, "OK", checkin

def list_checkins(hunt_id: str) -> List[Dict[str, Any]]:
    db = _open(hunt_id)
    Row = Query()
    rows = db.search((Row._type == "checkin") & (Row.hunt_id == hunt_id))
    rows.sort(key=lambda c: c.get("ts", 0))
    return rows

def get_state(hunt_id: str) -> Dict[str, Any]:
    h = get_hunt(hunt_id)
    if not h:
        return {"ok": False, "error": "not found"}
    checkpoints = list_checkpoints(hunt_id)
    groups = list_groups(hunt_id)
    staff = list_staff(hunt_id)
    checkins = list_checkins(hunt_id)
    last_checkins = sorted(checkins, key=lambda c: c.get("ts", 0), reverse=True)[:10]
    return {
        "ok": True,
        "hunt": {
            "hunt_id": h.get("hunt_id"),
            "title": h.get("title"),
            "description": h.get("description"),
            "rules": h.get("rules"),
            "territory_id": h.get("territory_id"),
            "join_code": h.get("join_code"),
            "created_at": h.get("created_at"),
            "started": bool(h.get("started")),
            "ended": bool(h.get("ended")),
            "active": bool(h.get("active", True)),
            "allow_implicit_groups": bool(h.get("allow_implicit_groups", True)),
        },
        "checkpoints": checkpoints,
        "groups": groups,
        "staff": staff,
        "checkins": last_checkins,
    }
