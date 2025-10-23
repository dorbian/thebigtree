# bigtree/webmods/admin.py
from __future__ import annotations
from aiohttp import web
from typing import Any, Dict
import time
import os
from tinydb import TinyDB, Query
import bigtree
from bigtree.inc.webserver import route

# ---------- TinyDB for admin clients ----------
def _admin_db_path() -> str:
    contest_dir = getattr(bigtree, "contest_dir", "/data/contest")
    return os.path.join(contest_dir, "admin_clients.json")

def _admin_db() -> TinyDB:
    path = _admin_db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return TinyDB(path)

# ---------- Send a Discord message ----------
@route("POST", "/message", scopes=["admin:message"])
async def send_message(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    channel_id = body.get("channel_id")
    content = body.get("content")
    if not channel_id or not content:
        return web.json_response({"error": "channel_id and content are required"}, status=400)

    try:
        channel_id = int(channel_id)
    except Exception:
        return web.json_response({"error": "channel_id must be an integer"}, status=400)

    chan = bigtree.bot.get_channel(channel_id)
    if not chan:
        bigtree.logger.warning(f"/message: channel {channel_id} not found or uncached")
        return web.json_response({"error": "channel not found or not cached"}, status=404)

    await chan.send(content)
    bigtree.logger.info(f"Message sent to channel {channel_id} via API")
    return web.json_response({"ok": True})

# ---------- FFXIV client announce ----------
@route("POST", "/admin/announce", scopes=["admin:announce"])
async def admin_announce(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    client_id = str(body.get("client_id") or "").strip()
    if not client_id:
        return web.json_response({"ok": False, "error": "client_id required"}, status=400)

    ip = req.headers.get("X-Forwarded-For") or req.remote
    ua = req.headers.get("User-Agent", "")
    now_ms = int(time.time() * 1000)

    doc = {
        "client_id": client_id,
        "app": str(body.get("app") or "unknown"),
        "version": str(body.get("version") or ""),
        "character": str(body.get("character") or ""),
        "world": str(body.get("world") or ""),
        "region": str(body.get("region") or ""),
        "extra": body.get("extra") or {},
        "ip": ip,
        "user_agent": ua,
        "ts": now_ms,
        "last_seen": now_ms,
    }

    db = _admin_db()
    q = Query()
    existing = db.get(q.client_id == client_id)
    if existing:
        doc["ts"] = existing.get("ts") or now_ms
        db.update(doc, q.client_id == client_id)
    else:
        db.insert(doc)

    bigtree.logger.info(
        "[announce] client_id=%s app=%s ver=%s char=%s world=%s ip=%s",
        client_id, doc["app"], doc["version"], doc["character"], doc["world"], ip
    )
    return web.json_response({"ok": True, "client_id": client_id})
