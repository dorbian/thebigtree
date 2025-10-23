# bigtree/webmods/contest.py
from __future__ import annotations
from aiohttp import web
from typing import Dict, Any, List, Optional
from tinydb import TinyDB
import os
import bigtree
from bigtree.inc.webserver import route

def _contest_db_path(channel_id: int) -> Optional[str]:
    contest_dir = getattr(bigtree, "contest_dir", "/data/contest")
    path = os.path.join(contest_dir, f"{channel_id}.json")
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

@route("GET", "/contests", allow_public=True)
async def list_contests(_req: web.Request):
    channels = list(map(int, getattr(bigtree, "contestid", []) or []))
    return web.json_response({"channels": channels})

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
