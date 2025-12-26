# bigtree/webmods/contest.py
from __future__ import annotations
from aiohttp import web
from typing import Dict, Any, List, Optional
from tinydb import TinyDB
import os
import bigtree
from bigtree.inc.webserver import route

_IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

def _contest_dir() -> str:
    return getattr(bigtree, "contest_dir", "/data/contest")

def _contest_db_path(channel_id: int) -> Optional[str]:
    path = os.path.join(_contest_dir(), f"{channel_id}.json")
    return path if os.path.exists(path) else None

def _read_contest(channel_id: int) -> Dict[str, Any]:
    path = _contest_db_path(channel_id)
    if not path:
        return {"exists": False}
    db = TinyDB(path)
    docs = db.all()
    meta = None
    entries: List[Dict[str, Any]] = []
    for d in docs:
        if d.get("_type") == "meta":
            meta = d
        else:
            entries.append(d)
    return {
        "exists": True,
        "channel_id": channel_id,
        "meta": meta,
        "entries": entries,
        "counts": {"entries": len(entries)},
    }

def _contest_name(meta: Dict[str, Any] | None, channel_id: int) -> str:
    if meta:
        for key in ("name", "title", "contest_name", "label", "channel_name", "channel", "channel_title"):
            value = (meta.get(key) or "").strip()
            if value:
                return value
    return f"Contest {channel_id}"

def _list_contest_entries() -> List[Dict[str, Any]]:
    contest_dir = _contest_dir()
    items: List[Dict[str, Any]] = []
    if not os.path.isdir(contest_dir):
        return items
    for name in os.listdir(contest_dir):
        if not name.endswith(".json"):
            continue
        stem = name[:-5]
        if not stem.isdigit():
            continue
        channel_id = int(stem)
        data = _read_contest(channel_id)
        if not data.get("exists"):
            continue
        meta = data.get("meta")
        contest_name = _contest_name(meta, channel_id)
        for entry in data.get("entries") or []:
            filename = (entry.get("file") or "").strip()
            if not filename:
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext not in _IMG_EXTS:
                continue
            if not os.path.exists(os.path.join(contest_dir, filename)):
                continue
            items.append({
                "title": "Contest Entry",
                "contest": contest_name,
                "url": f"/contest/media/{filename}",
                "source": "contest",
                "artist": {"artist_id": None, "name": "Forest", "links": {}},
            })
    return items

@route("GET", "/contests", allow_public=True)
async def list_contests(_req: web.Request):
    channels = set(map(int, getattr(bigtree, "contestid", []) or []))
    contest_dir = getattr(bigtree, "contest_dir", "/data/contest")
    try:
        for name in os.listdir(contest_dir):
            if not name.endswith(".json"):
                continue
            stem = name[:-5]
            if stem.isdigit():
                channels.add(int(stem))
    except Exception:
        pass
    return web.json_response({"channels": sorted(channels)})

@route("GET", "/contests/{channel_id}", allow_public=True)
async def get_contest(req: web.Request):
    try:
        channel_id = int(req.match_info["channel_id"])
    except ValueError:
        return web.json_response({"error": "channel_id must be an integer"}, status=400)
    return web.json_response(_read_contest(channel_id))

@route("GET", "/contests/{channel_id}/entries", allow_public=True)
async def list_entries(req: web.Request):
    try:
        channel_id = int(req.match_info["channel_id"])
    except ValueError:
        return web.json_response({"error": "channel_id must be an integer"}, status=400)
    data = _read_contest(channel_id)
    if not data.get("exists"):
        return web.json_response({"error": "contest not found"}, status=404)
    return web.json_response({"channel_id": channel_id, "entries": data["entries"]})
