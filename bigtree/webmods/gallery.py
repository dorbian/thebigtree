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
_REACTION_TYPES = set(gallery_mod.reaction_types())

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

def _item_id(source: str, identifier: str) -> str:
    identifier = (identifier or "").strip()
    return f"{source}:{identifier}" if identifier else ""

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
        item_id = _item_id("media", filename)
        seen.add(url)
        items.append({
            "item_id": item_id,
            "title": entry.get("title") or entry.get("original_name") or filename,
            "url": url,
            "source": "media",
            "type": "Artifact",
            "artist": _artist_payload(entry.get("artist_id")),
            "reactions": gallery_mod.get_reactions(item_id),
        })

    for deck in tarot_mod.list_decks():
        deck_id = deck.get("deck_id") or "elf-classic"
        back = (deck.get("back_image") or "").strip()
        if back:
            url = _strip_query(back)
            if url and url not in seen:
                item_id = _item_id("tarot-back", deck_id)
                items.append({
                    "item_id": item_id,
                    "title": deck.get("name") or deck_id,
                    "url": url,
                    "source": "tarot-back",
                    "type": "Tarot",
                    "artist": _artist_payload(deck.get("back_artist_id")),
                    "reactions": gallery_mod.get_reactions(item_id),
                })
                seen.add(url)
        for card in tarot_mod.list_cards(deck_id):
            img = (card.get("image") or "").strip()
            if not img:
                continue
            url = _strip_query(img)
            if not url or url in seen:
                continue
            card_id = card.get("card_id") or card.get("name") or url
            item_id = _item_id("tarot-card", f"{deck_id}:{card_id}")
            items.append({
                "item_id": item_id,
                "title": card.get("name") or card.get("card_id") or "Card",
                "url": url,
                "source": "tarot-card",
                "type": "Tarot",
                "artist": _artist_payload(card.get("artist_id")),
                "reactions": gallery_mod.get_reactions(item_id),
            })
            seen.add(url)

    try:
        contests = contest_mod._list_contest_entries()
        for entry in contests:
            url = _strip_query(entry.get("url") or "")
            filename = os.path.basename(url) if url else ""
            item_id = _item_id("contest", filename or url)
            entry["item_id"] = item_id
            entry["type"] = entry.get("type") or "Contest"
            entry["reactions"] = gallery_mod.get_reactions(item_id)
            if entry.get("contest"):
                entry["event_name"] = entry.get("contest")
            items.append(entry)
    except Exception:
        pass

    return web.json_response({"ok": True, "items": items})

@route("GET", "/api/gallery/reactions", allow_public=True)
async def gallery_reactions(req: web.Request):
    item_id = (req.query.get("item_id") or "").strip()
    if not item_id:
        return web.json_response({"ok": False, "error": "item_id required"}, status=400)
    return web.json_response({"ok": True, "item_id": item_id, "reactions": gallery_mod.get_reactions(item_id)})

@route("POST", "/api/gallery/reactions", allow_public=True)
async def gallery_react(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    item_id = str(body.get("item_id") or "").strip()
    reaction_id = str(body.get("reaction") or "").strip().lower()
    if not item_id:
        return web.json_response({"ok": False, "error": "item_id required"}, status=400)
    if reaction_id not in _REACTION_TYPES:
        return web.json_response({"ok": False, "error": "invalid reaction"}, status=400)
    try:
        counts = gallery_mod.increment_reaction(item_id, reaction_id)
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response({"ok": True, "item_id": item_id, "reactions": counts})

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
