# bigtree/webmods/gallery.py
from __future__ import annotations
from aiohttp import web
from typing import Dict, Any, List
import os
from bigtree.inc.webserver import route
from bigtree.modules import media as media_mod
from bigtree.modules import artists as artist_mod
from bigtree.modules import tarot as tarot_mod
from bigtree.modules import gallery as gallery_mod
from bigtree.webmods import contest as contest_mod

_IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

def _artist_payload(artist_id: str | None) -> Dict[str, Any]:
    if artist_id:
        artist = artist_mod.get_artist(artist_id)
        if artist:
            return {
                "artist_id": artist.get("artist_id"),
                "name": artist.get("name"),
                "links": artist.get("links") or {},
            }
        return {"artist_id": artist_id, "name": "Forest", "links": {}}
    return {"artist_id": None, "name": "Forest", "links": {}}

def _contest_name(meta: Dict[str, Any] | None, channel_id: int) -> str:
    if meta:
        for key in ("name", "title", "contest_name", "label"):
            value = (meta.get(key) or "").strip()
            if value:
                return value
    return f"Contest {channel_id}"

def _contest_media_url(filename: str) -> str:
    return f"/contest/media/{filename}"

def _strip_query(url: str) -> str:
    return (url or "").split("?", 1)[0]

def _media_path(filename: str) -> str:
    return os.path.join(media_mod.get_media_dir(), filename)

@route("GET", "/contest/media/{filename}", allow_public=True)
async def contest_media_file(req: web.Request):
    filename = os.path.basename(req.match_info["filename"])
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _IMG_EXTS:
        return web.Response(status=404)
    path = os.path.join(contest_mod._contest_dir(), filename)
    if not os.path.exists(path):
        return web.Response(status=404)
    return web.FileResponse(path)

@route("GET", "/api/gallery/images", allow_public=True)
async def gallery_images(_req: web.Request):
    items: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for entry in media_mod.list_media():
        filename = entry.get("filename")
        if not filename:
            continue
        if not os.path.exists(_media_path(filename)):
            continue
        url = f"/media/{filename}"
        seen.add(url)
        items.append({
            "title": entry.get("title") or entry.get("original_name") or filename,
            "url": url,
            "source": "media",
            "artist": _artist_payload(entry.get("artist_id")),
        })

    for deck in tarot_mod.list_decks():
        deck_id = deck.get("deck_id") or "elf-classic"
        back = (deck.get("back_image") or "").strip()
        if back:
            url = _strip_query(back)
            if url and url not in seen:
                items.append({
                    "title": deck.get("name") or deck_id,
                    "url": url,
                    "source": "tarot-back",
                    "artist": _artist_payload(deck.get("back_artist_id")),
                })
                seen.add(url)
        for card in tarot_mod.list_cards(deck_id):
            img = (card.get("image") or "").strip()
            if not img:
                continue
            url = _strip_query(img)
            if not url or url in seen:
                continue
            items.append({
                "title": card.get("name") or card.get("card_id") or "Card",
                "url": url,
                "source": "tarot-card",
                "artist": _artist_payload(card.get("artist_id")),
            })
            seen.add(url)

    try:
        contests = contest_mod._list_contest_entries()
        items.extend(contests)
    except Exception:
        pass

    return web.json_response({"ok": True, "items": items})

@route("GET", "/api/gallery/calendar", allow_public=True)
async def gallery_calendar(_req: web.Request):
    months = []
    for entry in gallery_mod.list_calendar():
        months.append({
            "month": entry.get("month"),
            "month_name": entry.get("month_name"),
            "image": entry.get("image"),
            "title": entry.get("title") or "",
            "artist": _artist_payload(entry.get("artist_id")),
        })
    return web.json_response({"ok": True, "months": months})

@route("POST", "/api/gallery/calendar", scopes=["tarot:admin"])
async def gallery_calendar_set(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)
    month = int(body.get("month") or 0)
    image = (body.get("image") or "").strip()
    title = (body.get("title") or "").strip()
    artist_id = (body.get("artist_id") or "").strip() or None
    if month < 1 or month > 12:
        return web.json_response({"ok": False, "error": "month must be 1-12"}, status=400)
    if not image:
        gallery_mod.clear_month(month)
        return web.json_response({"ok": True, "cleared": month})
    try:
        entry = gallery_mod.set_month(month, image, title=title, artist_id=artist_id)
    except Exception as ex:
        return web.json_response({"ok": False, "error": str(ex)}, status=400)
    return web.json_response({"ok": True, "month": entry})
