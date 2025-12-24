from __future__ import annotations
import os
from aiohttp import web
from bigtree.inc.webserver import route
from bigtree.webmods import tarot_api
from bigtree.modules import bingo as bingo_mod

_IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

def _list_dir(path: str, prefix: str) -> list[dict]:
    items = []
    try:
        for name in os.listdir(path):
            ext = os.path.splitext(name)[1].lower()
            if ext not in _IMG_EXTS:
                continue
            items.append({
                "name": name,
                "url": f"{prefix}/{name}",
            })
    except Exception:
        return []
    items.sort(key=lambda i: i["name"])
    return items

@route("GET", "/api/uploads/tarot/cards", scopes=["tarot:admin"])
async def list_tarot_cards(_req: web.Request):
    path = tarot_api._cards_dir()
    return web.json_response({"ok": True, "items": _list_dir(path, "/tarot/cards")})

@route("GET", "/api/uploads/tarot/backs", scopes=["tarot:admin"])
async def list_tarot_backs(_req: web.Request):
    path = tarot_api._backs_dir()
    return web.json_response({"ok": True, "items": _list_dir(path, "/tarot/backs")})

@route("GET", "/api/uploads/bingo/backgrounds", scopes=["bingo:admin"])
async def list_bingo_backgrounds(_req: web.Request):
    items = []
    try:
        for g in bingo_mod.list_games():
            gid = g.get("game_id")
            if not gid:
                continue
            game = bingo_mod.get_game(gid)
            if not game or not game.get("background_path"):
                continue
            items.append({
                "name": f"{gid}.png",
                "game_id": gid,
                "url": f"/bingo/assets/{gid}",
            })
    except Exception:
        items = []
    return web.json_response({"ok": True, "items": items})

