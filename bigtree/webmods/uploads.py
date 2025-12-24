from __future__ import annotations
import os
from aiohttp import web
from bigtree.inc.webserver import route
from bigtree.webmods import tarot_api
from bigtree.modules import bingo as bingo_mod
from bigtree.modules import tarot as tarot_mod
from bigtree.modules import artists as artist_mod

_IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

async def read_multipart(req: web.Request, *, file_field: str = "file") -> tuple[dict, str, bytes]:
    reader = await req.multipart()
    fields: dict[str, str] = {}
    filename = ""
    data = bytearray()
    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == file_field:
            filename = getattr(part, "filename", "") or ""
            while True:
                chunk = await part.read_chunk()
                if not chunk:
                    break
                data.extend(chunk)
        else:
            fields[part.name] = (await part.text()).strip()
    return fields, filename, bytes(data)

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

def _strip_query(url: str) -> str:
    return url.split("?", 1)[0]

def _artist_info(artist_id: str | None) -> dict:
    if not artist_id:
        return {}
    artist = artist_mod.get_artist(artist_id)
    if not artist:
        return {"artist_id": artist_id}
    return {
        "artist_id": artist.get("artist_id"),
        "artist_name": artist.get("name"),
        "artist_links": artist.get("links") or {},
    }


@route("GET", "/api/uploads/tarot/cards", scopes=["tarot:admin"])
async def list_tarot_cards(_req: web.Request):
    items: list[dict] = []
    for deck in tarot_mod.list_decks():
        deck_id = deck.get("deck_id") or "elf-classic"
        for c in tarot_mod.list_cards(deck_id):
            img = (c.get("image") or "").strip()
            if not img:
                continue
            url = _strip_query(img)
            name = os.path.basename(url)
            entry = {"name": name, "url": url, "deck_id": deck_id, "card_id": c.get("card_id")}
            entry.update(_artist_info(c.get("artist_id")))
            items.append(entry)
    by_name = {item.get("name"): item for item in items if item.get("name")}
    for item in _list_dir(tarot_api._cards_dir(), "/tarot/cards"):
        name = item.get("name")
        if name and name not in by_name:
            items.append(item)
    return web.json_response({"ok": True, "items": items})

@route("GET", "/api/uploads/tarot/backs", scopes=["tarot:admin"])
async def list_tarot_backs(_req: web.Request):
    items: list[dict] = []
    for deck in tarot_mod.list_decks():
        back = (deck.get("back_image") or "").strip()
        if not back:
            continue
        url = _strip_query(back)
        name = os.path.basename(url)
        entry = {"name": name, "url": url, "deck_id": deck.get("deck_id")}
        entry.update(_artist_info(deck.get("back_artist_id")))
        items.append(entry)
    by_name = {item.get("name"): item for item in items if item.get("name")}
    for item in _list_dir(tarot_api._backs_dir(), "/tarot/backs"):
        name = item.get("name")
        if name and name not in by_name:
            items.append(item)
    return web.json_response({"ok": True, "items": items})

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

@route("DELETE", "/api/uploads/tarot/cards/{filename}", scopes=["tarot:admin"])
async def delete_tarot_card_file(req: web.Request):
    filename = req.match_info["filename"]
    path = os.path.join(tarot_api._cards_dir(), filename)
    if not os.path.exists(path):
        return web.json_response({"ok": False, "error": "not found"}, status=404)
    try:
        os.remove(path)
    except Exception:
        return web.json_response({"ok": False, "error": "delete failed"}, status=500)
    tarot_mod.clear_image_references(f"/tarot/cards/{filename}")
    return web.json_response({"ok": True})

@route("DELETE", "/api/uploads/tarot/backs/{filename}", scopes=["tarot:admin"])
async def delete_tarot_back_file(req: web.Request):
    filename = req.match_info["filename"]
    path = os.path.join(tarot_api._backs_dir(), filename)
    if not os.path.exists(path):
        return web.json_response({"ok": False, "error": "not found"}, status=404)
    try:
        os.remove(path)
    except Exception:
        return web.json_response({"ok": False, "error": "delete failed"}, status=500)
    tarot_mod.clear_image_references(f"/tarot/backs/{filename}")
    return web.json_response({"ok": True})

@route("DELETE", "/api/uploads/bingo/backgrounds/{game_id}", scopes=["bingo:admin"])
async def delete_bingo_background(req: web.Request):
    game_id = req.match_info["game_id"]
    ok, msg = bingo_mod.delete_background(game_id)
    if not ok:
        return web.json_response({"ok": False, "error": msg}, status=400)
    return web.json_response({"ok": True})
