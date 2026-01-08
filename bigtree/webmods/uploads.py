from __future__ import annotations
import os
from aiohttp import web
from bigtree.inc.webserver import route
from bigtree.webmods import tarot_api
from bigtree.modules import bingo as bingo_mod
from bigtree.modules import tarot as tarot_mod
from bigtree.modules import artists as artist_mod
from bigtree.modules import media as media_mod
from bigtree.modules import gallery as gallery_mod
import uuid
import imghdr

_IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

def _media_dir() -> str:
    return media_mod.get_media_dir()

def _media_thumbs_dir() -> str:
    return media_mod.get_media_thumbs_dir()

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

def _add_usage(usage: dict[str, set[str]], filename: str, label: str):
    if not filename:
        return
    usage.setdefault(filename, set()).add(label)

def _build_usage_map() -> dict[str, set[str]]:
    usage: dict[str, set[str]] = {}
    for deck in tarot_mod.list_decks():
        back = (deck.get("back_image") or "").strip()
        if back:
            name = os.path.basename(_strip_query(back))
            _add_usage(usage, name, "Tarot Back")
    for deck in tarot_mod.list_decks():
        deck_id = deck.get("deck_id") or "elf-classic"
        for c in tarot_mod.list_cards(deck_id):
            img = (c.get("image") or "").strip()
            if not img:
                continue
            name = os.path.basename(_strip_query(img))
            _add_usage(usage, name, "Tarot Card")
    return usage

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

def _media_item(
    filename: str,
    artist_id: str | None,
    original_name: str = "",
    title: str = "",
    used_in: list[str] | None = None,
    discord_url: str | None = None,
    prefer_discord: bool = True,
    origin_type: str | None = None,
    origin_label: str | None = None,
) -> dict:
    url = (discord_url if (prefer_discord and discord_url) else f"/media/{filename}")
    item_id = f"media:{filename}" if filename else ""
    item = {
        "item_id": item_id,
        "name": filename,
        "url": url,
        "fallback_url": f"/media/{filename}" if discord_url else "",
        "discord_url": discord_url or "",
        "source": "media",
        "origin_type": origin_type or "",
        "origin_label": origin_label or "",
        "original_name": original_name,
        "title": title,
        "delete_url": f"/api/media/{filename}",
        "used_in": used_in or [],
        "hidden": gallery_mod.is_hidden(item_id) if item_id else False,
    }
    item.update(_artist_info(artist_id))
    if artist_id and not item.get("artist_id"):
        item["artist_id"] = artist_id
    return item

def resolve_media_path(url: str) -> str | None:
    if not url:
        return None
    url = url.split("?", 1)[0]
    if url.startswith("/media/"):
        filename = url.split("/", 2)[-1]
        return os.path.join(_media_dir(), filename)
    if url.startswith("/tarot/cards/"):
        filename = url.split("/", 3)[-1]
        return os.path.join(tarot_api._cards_dir(), filename)
    if url.startswith("/tarot/backs/"):
        filename = url.split("/", 3)[-1]
        return os.path.join(tarot_api._backs_dir(), filename)
    if url.startswith("/bingo/assets/"):
        game_id = url.split("/", 3)[-1]
        g = bingo_mod.get_game(game_id)
        if g and g.get("background_path"):
            return g.get("background_path")
    return None


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

@route("GET", "/media/{filename}", allow_public=True)
async def media_file(req: web.Request):
    filename = req.match_info["filename"]
    path = os.path.join(_media_dir(), filename)
    if not os.path.exists(path):
        return web.Response(status=404)
    resp = web.FileResponse(path)
    resp.headers["Cache-Control"] = "public, max-age=86400, immutable"
    return resp

@route("GET", "/media/thumbs/{filename}", allow_public=True)
async def media_thumb(req: web.Request):
    filename = req.match_info["filename"]
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _IMG_EXTS:
        return web.Response(status=404)
    thumb_path = os.path.join(_media_thumbs_dir(), filename)
    if not os.path.exists(thumb_path):
        if not media_mod.ensure_thumb(filename):
            return web.Response(status=404)
    resp = web.FileResponse(thumb_path)
    resp.headers["Cache-Control"] = "public, max-age=86400, immutable"
    return resp

@route("POST", "/api/media/upload", scopes=["tarot:admin", "bingo:admin", "admin:web"])
async def upload_media(req: web.Request):
    fields, filename_hint, data = await read_multipart(req)
    if not data:
        return web.json_response({"ok": False, "error": "file required"}, status=400)
    artist_id = (fields.get("artist_id") or "").strip() or None
    title = (fields.get("title") or "").strip() or None
    origin_type = (fields.get("origin_type") or "").strip() or None
    origin_label = (fields.get("origin_label") or "").strip() or None
    kind = imghdr.what(None, h=data)
    ext_map = {
        "jpeg": ".jpg",
        "png": ".png",
        "gif": ".gif",
        "bmp": ".bmp",
        "webp": ".webp",
    }
    ext = ext_map.get(kind)
    if not ext:
        raw_ext = os.path.splitext(filename_hint or "")[1].lower()
        alias = {".jpeg": ".jpg", ".jfif": ".jpg"}
        raw_ext = alias.get(raw_ext, raw_ext)
        if raw_ext in _IMG_EXTS:
            ext = raw_ext
    if not ext:
        return web.json_response({"ok": False, "error": "unsupported image format"}, status=400)
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = os.path.join(_media_dir(), filename)
    try:
        with open(dest, "wb") as f:
            f.write(data)
    except Exception:
        return web.json_response({"ok": False, "error": "save failed"}, status=500)
    entry = media_mod.add_media(
        filename,
        original_name=filename_hint,
        artist_id=artist_id,
        title=title,
        origin_type=origin_type,
        origin_label=origin_label,
    )
    try:
        from bigtree.webmods import gallery as gallery_web
        gallery_web.invalidate_gallery_cache()
    except Exception:
        pass
    item = _media_item(
        filename,
        entry.get("artist_id"),
        entry.get("original_name") or "",
        entry.get("title") or "",
        discord_url=entry.get("discord_url") or None,
        prefer_discord=False,
        origin_type=entry.get("origin_type") or "",
        origin_label=entry.get("origin_label") or "",
    )
    return web.json_response({"ok": True, "item": item})

@route("GET", "/api/media/list", scopes=["tarot:admin", "bingo:admin", "admin:web"])
async def list_media(_req: web.Request):
    items: list[dict] = []
    seen: set[str] = set()
    usage_map = _build_usage_map()
    for entry in media_mod.list_media():
        filename = entry.get("filename")
        if not filename or filename in seen:
            continue
        seen.add(filename)
        items.append(_media_item(
            filename,
            entry.get("artist_id"),
            entry.get("original_name") or "",
            entry.get("title") or "",
            used_in=sorted(usage_map.get(filename, set())),
            discord_url=entry.get("discord_url") or None,
            prefer_discord=False,
            origin_type=entry.get("origin_type") or "",
            origin_label=entry.get("origin_label") or "",
        ))

    for deck in tarot_mod.list_decks():
        back = (deck.get("back_image") or "").strip()
        if back:
            url = _strip_query(back)
            name = os.path.basename(url)
            if name not in seen:
                entry = {
                    "name": name,
                    "url": url,
                    "source": "tarot-back",
                    "delete_url": f"/api/uploads/tarot/backs/{name}",
                    "used_in": sorted(usage_map.get(name, {"Tarot Back"})),
                }
                entry.update(_artist_info(deck.get("back_artist_id")))
                items.append(entry)
                seen.add(name)
    for deck in tarot_mod.list_decks():
        for c in tarot_mod.list_cards(deck.get("deck_id") or "elf-classic"):
            img = (c.get("image") or "").strip()
            if not img:
                continue
            url = _strip_query(img)
            name = os.path.basename(url)
            if name in seen:
                continue
            entry = {
                "name": name,
                "url": url,
                "source": "tarot-card",
                "delete_url": f"/api/uploads/tarot/cards/{name}",
                "used_in": sorted(usage_map.get(name, {"Tarot Card"})),
            }
            entry.update(_artist_info(c.get("artist_id")))
            items.append(entry)
            seen.add(name)

    return web.json_response({"ok": True, "items": items})

@route("DELETE", "/api/media/{filename}", scopes=["admin:web"])
async def delete_media(req: web.Request):
    filename = req.match_info["filename"]
    path = os.path.join(_media_dir(), filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            return web.json_response({"ok": False, "error": "delete failed"}, status=500)
    media_mod.delete_media(filename)
    tarot_mod.clear_image_references(f"/media/{filename}")
    try:
        from bigtree.webmods import gallery as gallery_web
        gallery_web.invalidate_gallery_cache()
    except Exception:
        pass
    return web.json_response({"ok": True})

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
    try:
        from bigtree.webmods import gallery as gallery_web
        gallery_web.invalidate_gallery_cache()
    except Exception:
        pass
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
    try:
        from bigtree.webmods import gallery as gallery_web
        gallery_web.invalidate_gallery_cache()
    except Exception:
        pass
    return web.json_response({"ok": True})

@route("DELETE", "/api/uploads/bingo/backgrounds/{game_id}", scopes=["bingo:admin"])
async def delete_bingo_background(req: web.Request):
    game_id = req.match_info["game_id"]
    ok, msg = bingo_mod.delete_background(game_id)
    if not ok:
        return web.json_response({"ok": False, "error": msg}, status=400)
    return web.json_response({"ok": True})
