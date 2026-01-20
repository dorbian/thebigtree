# bigtree/webmods/gallery.py
from __future__ import annotations
from aiohttp import web
from typing import Dict, Any, List
import unicodedata
import asyncio
import os
import discord
import bigtree
from bigtree.inc.plogon import get_with_leaf_path
from bigtree.inc.webserver import route
from bigtree.inc.database import get_database
from bigtree.modules import media as media_mod
from bigtree.modules import artists as artist_mod
from bigtree.modules import gallery as gallery_mod
from bigtree.webmods import contest as contest_mod
import random
import time

_GALLERY_CACHE: dict | None = None
_GALLERY_CACHE_AT = 0.0
_GALLERY_CACHE_TTL = 600.0
_GALLERY_SHUFFLES: dict[int, list[int]] = {}
_THUMB_WARM_AT = 0.0
_THUMB_WARM_TTL = 30.0
_CONTEST_THUMB_DIR = "thumbs"

def invalidate_gallery_cache() -> None:
    global _GALLERY_CACHE, _GALLERY_CACHE_AT, _GALLERY_SHUFFLES
    _GALLERY_CACHE = None
    _GALLERY_CACHE_AT = 0.0
    _GALLERY_SHUFFLES = {}

def _get_gallery_cached(include_hidden: bool) -> list[dict]:
    global _GALLERY_CACHE, _GALLERY_CACHE_AT, _GALLERY_SHUFFLES
    now = time.time()
    if _GALLERY_CACHE is not None and (now - _GALLERY_CACHE_AT) < _GALLERY_CACHE_TTL:
        cached = _GALLERY_CACHE.get("items", [])
        if include_hidden:
            return list(cached)
        return [item for item in cached if not item.get("hidden")]
    items = _collect_gallery_items(include_hidden=True)
    _GALLERY_CACHE = {"items": items}
    _GALLERY_CACHE_AT = now
    _GALLERY_SHUFFLES = {}
    if include_hidden:
        return list(items)
    return [item for item in items if not item.get("hidden")]

_IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
_REACTION_TYPES = set(gallery_mod.reaction_types())

def _is_image_attachment(att: discord.Attachment) -> bool:
    filename = (att.filename or "")
    ext = os.path.splitext(filename)[1].lower()
    if ext in _IMG_EXTS:
        return True
    content_type = (att.content_type or "").lower()
    return content_type.startswith("image/")

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

def _contest_thumb_dir() -> str:
    path = os.path.join(contest_mod._contest_dir(), _CONTEST_THUMB_DIR)
    os.makedirs(path, exist_ok=True)
    return path

def _contest_thumb_path(filename: str) -> str:
    return os.path.join(_contest_thumb_dir(), filename)

def _ensure_contest_thumb(filename: str, size: tuple[int, int] = (480, 672)) -> bool:
    if not filename:
        return False
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _IMG_EXTS:
        return False
    thumb_path = _contest_thumb_path(filename)
    if os.path.exists(thumb_path):
        return True
    source = os.path.join(contest_mod._contest_dir(), filename)
    if not os.path.exists(source):
        return False
    try:
        from PIL import Image
    except Exception:
        return False
    try:
        with Image.open(source) as img:
            try:
                img.seek(0)
            except Exception:
                pass
            img.thumbnail(size)
            fmt = {
                ".jpg": "JPEG",
                ".jpeg": "JPEG",
                ".png": "PNG",
                ".gif": "GIF",
                ".bmp": "BMP",
                ".webp": "WEBP",
            }.get(ext, "PNG")
            save_kwargs = {}
            if fmt == "JPEG":
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                save_kwargs = {"quality": 82, "optimize": True, "progressive": True}
            img.save(thumb_path, fmt, **save_kwargs)
    except Exception:
        return False
    return True

def _strip_emojis(text: str) -> str:
    if not text:
        return ""
    cleaned = []
    for ch in text:
        code = ord(ch)
        if code in (0x200D, 0xFE0E, 0xFE0F):
            continue
        if 0x1F3FB <= code <= 0x1F3FF:
            continue
        category = unicodedata.category(ch)
        if category in ("So", "Cs"):
            continue
        cleaned.append(ch)
    return "".join(cleaned)

def _strip_query(url: str) -> str:
    return (url or "").split("?", 1)[0]

def _media_path(filename: str) -> str:
    return os.path.join(media_mod.get_media_dir(), filename)

def _media_thumb_url(url: str) -> str:
    if not url or not url.startswith("/media/"):
        return ""
    filename = url.split("/media/", 1)[1]
    if not filename:
        return ""
    if media_mod.ensure_thumb(filename):
        return f"/media/thumbs/{filename}"
    return ""

def _item_id(source: str, identifier: str) -> str:
    identifier = (identifier or "").strip()
    return f"{source}:{identifier}" if identifier else ""

def _collect_gallery_items(include_hidden: bool) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    hidden_set = set(gallery_mod.get_hidden_set() or [])

    # Ensure legacy media.json and filesystem-only uploads are migrated into Postgres.
    db = get_database()
    try:
        db.initialize()
    except Exception:
        pass

    # Pull from Postgres as the source of truth.
    # NOTE: we keep legacy reaction/hidden ids stable by still using the
    # "media:<filename>" item_id shape.
    rows = []
    try:
        rows = db.list_media_items(limit=5000, offset=0, include_hidden=True)
    except Exception:
        rows = []

    for row in rows:
        filename = (row.get("filename") or row.get("media_id") or "").strip()
        if not filename:
            continue
        item_id = _item_id("media", filename)
        hidden = bool(row.get("hidden")) or (item_id in hidden_set)
        if not include_hidden and hidden:
            continue
        url = (row.get("url") or "").strip() or f"/media/{filename}"
        thumb_url = (row.get("thumb_url") or "").strip() or f"/media/thumbs/{filename}"
        if url in seen:
            continue
        # Ensure thumb exists for disk-backed images.
        try:
            if url.startswith("/media/"):
                _ = media_mod.ensure_thumb(filename)
        except Exception:
            pass
        artist_name = (row.get("artist_name") or "").strip() or "Forest"
        artist_links = row.get("artist_links") if isinstance(row.get("artist_links"), dict) else {}
        items.append({
            "item_id": item_id,
            "filename": filename,
            "title": row.get("title") or filename,
            "url": url,
            "fallback_url": f"/media/{filename}" if url != f"/media/{filename}" else "",
            "thumb_url": thumb_url,
            "source": "media",
            "type": row.get("origin_type") or "Artifact",
            "origin": row.get("origin_label") or "",
            "artist": {"artist_id": None, "name": artist_name, "links": artist_links},
            "reactions": {},
            "hidden": hidden,
        })
        seen.add(url)

    # Opportunistic: if files exist in the media dir but have not been migrated yet,
    # upsert them into Postgres so the feed remains complete.
    try:
        media_dir = media_mod.get_media_dir()
        for name in os.listdir(media_dir):
            if name in ("media.json", "thumbs"):
                continue
            path = os.path.join(media_dir, name)
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in _IMG_EXTS:
                continue
            item_id = _item_id("media", name)
            hidden = item_id in hidden_set
            if not include_hidden and hidden:
                continue
            url = f"/media/{name}"
            if url in seen:
                continue
            try:
                _ = media_mod.ensure_thumb(name)
            except Exception:
                pass
            try:
                db.upsert_media_item(
                    media_id=name,
                    filename=name,
                    title=name,
                    url=url,
                    thumb_url=f"/media/thumbs/{name}",
                    hidden=hidden,
                    kind="image",
                    metadata={"filesystem_only": True, "auto_migrated": True},
                )
            except Exception:
                pass
            items.append({
                "item_id": item_id,
                "filename": name,
                "title": name,
                "url": url,
                "fallback_url": "",
                "thumb_url": f"/media/thumbs/{name}",
                "source": "media",
                "type": "Artifact",
                "origin": "",
                "artist": {"artist_id": None, "name": "Forest", "links": {}},
                "reactions": {},
                "hidden": hidden,
            })
            seen.add(url)
    except Exception:
        pass

    try:
        contests = contest_mod._list_contest_entries()
        for entry in contests:
            url = _strip_query(entry.get("url") or "")
            filename = os.path.basename(url) if url else ""
            item_id = _item_id("contest", filename or url)
            hidden = item_id in hidden_set
            if not include_hidden and hidden:
                continue
            thumb_url = ""
            if filename and _ensure_contest_thumb(filename):
                thumb_url = f"/contest/media/thumbs/{filename}"
            entry["item_id"] = item_id
            entry["type"] = entry.get("type") or "Contest"
            entry["reactions"] = {}
            entry["hidden"] = hidden
            if thumb_url:
                entry["thumb_url"] = thumb_url
            if entry.get("contest"):
                entry["event_name"] = entry.get("contest")
            items.append(entry)
    except Exception:
        pass

    item_ids = [item.get("item_id") or "" for item in items]
    reactions_map = gallery_mod.list_reactions_bulk(item_ids)
    for item in items:
        item_id = item.get("item_id") or ""
        item["reactions"] = reactions_map.get(item_id, {})

    return items

def _get_shuffle_indices(total: int, seed: int) -> list[int]:
    indices = _GALLERY_SHUFFLES.get(seed)
    if indices is not None and len(indices) == total:
        return indices
    rng = random.Random(seed)
    indices = list(range(total))
    rng.shuffle(indices)
    _GALLERY_SHUFFLES[seed] = indices
    return indices

def _schedule_thumb_warm(items: list[dict]) -> None:
    global _THUMB_WARM_AT
    now = time.time()
    if (now - _THUMB_WARM_AT) < _THUMB_WARM_TTL:
        return
    _THUMB_WARM_AT = now
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_warm_thumbnails(items))

def _media_filename_from_url(url: str) -> str:
    if not url or not url.startswith("/media/"):
        return ""
    return url.split("/media/", 1)[1]

def _contest_filename_from_url(url: str) -> str:
    if not url or not url.startswith("/contest/media/"):
        return ""
    return url.split("/contest/media/", 1)[1]

def _ensure_thumb_for_item(item: dict) -> None:
    url = (item.get("url") or "").strip()
    if url.startswith("/media/"):
        name = _media_filename_from_url(url)
        if name:
            media_mod.ensure_thumb(name)
        return
    if url.startswith("/contest/media/"):
        name = _contest_filename_from_url(url)
        if name:
            _ensure_contest_thumb(name)
        return

async def _warm_thumbnails(items: list[dict], limit: int = 48) -> None:
    if not items:
        return
    slice_items = items[:limit]
    await asyncio.to_thread(_ensure_thumbs_for_items, slice_items)

def _ensure_thumbs_for_items(items: list[dict]) -> None:
    for item in items:
        try:
            _ensure_thumb_for_item(item)
        except Exception:
            continue

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

@route("GET", "/contest/media/thumbs/{filename}", allow_public=True)
async def contest_media_thumb(req: web.Request):
    filename = os.path.basename(req.match_info["filename"])
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _IMG_EXTS:
        return web.Response(status=404)
    if not _ensure_contest_thumb(filename):
        return web.Response(status=404)
    path = _contest_thumb_path(filename)
    if not os.path.exists(path):
        return web.Response(status=404)
    return web.FileResponse(path)

@route("GET", "/api/gallery/images", allow_public=True)
async def gallery_images(_req: web.Request):
    items = _get_gallery_cached(include_hidden=False)
    total = len(items)
    seed_raw = _req.query.get("seed")
    try:
        seed = int(seed_raw) if seed_raw is not None else None
    except Exception:
        seed = None
    if seed is None:
        seed = int(time.time() * 1000) & 0x7FFFFFFF
    indices = _get_shuffle_indices(total, seed)
    _schedule_thumb_warm(items)
    try:
        limit = int(_req.query.get("limit") or 0)
    except Exception:
        limit = 0
    try:
        offset = int(_req.query.get("offset") or 0)
    except Exception:
        offset = 0
    if offset < 0:
        offset = 0
    if limit and limit > 0:
        indices = indices[offset:offset + limit]
        items = [items[idx] for idx in indices]
    else:
        items = [items[idx] for idx in indices]
    cfg = get_database().get_system_config("gallery") or {}
    # Backwards compat: earlier configs used singular keys.
    inspiration_cfg = (
        cfg.get("inspiration_texts")
        or cfg.get("inspiration_text")
        or cfg.get("inspirational_text")
        or cfg.get("flair_text")
        or ""
    )
    settings = {
        "columns": cfg.get("columns"),
        "inspiration_every": cfg.get("inspiration_every"),
        "inspiration_texts": inspiration_cfg,
        # Optional UI copy overrides (so inspirational / flavor text can be managed in DB)
        "header_subtitle": cfg.get("header_subtitle") or "",
        "header_context": cfg.get("header_context") or "",
        "suggestions_title": cfg.get("suggestions_title") or "",
        "post_game_title": cfg.get("post_game_title") or "",
        "post_game_body": cfg.get("post_game_body") or "",
        "return_title": cfg.get("return_title") or "",
        "return_body": cfg.get("return_body") or "",
    }
    resp = web.json_response({
        "ok": True,
        "items": items,
        "total": total,
        "seed": seed,
        "offset": offset,
        "limit": limit,
        "settings": settings,
    })
    resp.headers["Cache-Control"] = "public, max-age=60"
    return resp

@route("GET", "/api/gallery/admin/items", scopes=["tarot:admin"])
async def gallery_admin_items(_req: web.Request):
    items = _get_gallery_cached(include_hidden=True)
    return web.json_response({"ok": True, "items": items})

@route("POST", "/api/gallery/hidden", scopes=["tarot:admin"])
async def gallery_hidden_set(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    item_id = str(body.get("item_id") or "").strip()
    hidden = bool(body.get("hidden"))
    if not item_id:
        return web.json_response({"ok": False, "error": "item_id required"}, status=400)
    # Persist hidden flag in Postgres (source of truth). Keep legacy TinyDB
    # hidden store only for backwards compatibility with old item ids.
    media_id = item_id
    if ":" in item_id:
        media_id = item_id.split(":", 1)[1]
    try:
        get_database().set_media_hidden(media_id, hidden)
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    try:
        # Backwards-compat: still update the legacy hidden set so older cached
        # reaction views behave.
        gallery_mod.set_hidden(item_id, hidden)
    except Exception:
        pass
    invalidate_gallery_cache()
    return web.json_response({"ok": True, "item_id": item_id, "hidden": hidden})

@route("GET", "/api/gallery/settings", scopes=["tarot:admin", "admin:web"])
async def gallery_settings_get(_req: web.Request):
    db = get_database()
    cfg = db.get_system_config("gallery") or {}
    return web.json_response({
        "ok": True,
        "upload_channel_id": gallery_mod.get_upload_channel_id(),
        "hidden_decks": gallery_mod.get_hidden_decks(),
        "flair_text": cfg.get("flair_text") or "",
        "columns": cfg.get("columns"),
        "inspiration_every": cfg.get("inspiration_every"),
        "inspiration_texts": cfg.get("inspiration_texts") or "",
    })

@route("POST", "/api/gallery/settings", scopes=["tarot:admin", "admin:web"])
async def gallery_settings_set(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    channel_present = "upload_channel_id" in body
    hidden_present = "hidden_decks" in body
    flair_present = "flair_text" in body
    columns_present = "columns" in body
    inspiration_every_present = "inspiration_every" in body
    inspiration_texts_present = "inspiration_texts" in body

    payload = {"upload_channel_id": gallery_mod.get_upload_channel_id()}
    if channel_present:
        channel_id = body.get("upload_channel_id")
        try:
            channel_id = int(channel_id) if channel_id else None
        except Exception:
            channel_id = None
        payload = gallery_mod.set_upload_channel_id(channel_id)

    deck_payload = {"hidden_decks": gallery_mod.get_hidden_decks()}
    if hidden_present:
        hidden_decks = body.get("hidden_decks")
        if hidden_decks is None:
            hidden_decks = []
        if isinstance(hidden_decks, str):
            hidden_decks = [item.strip() for item in hidden_decks.split(",") if item.strip()]
        if not isinstance(hidden_decks, list):
            hidden_decks = []
        deck_payload = gallery_mod.set_hidden_decks(hidden_decks)
        invalidate_gallery_cache()

    
    if flair_present:
        db = get_database()
        cfg = db.get_system_config("gallery") or {}
        cfg["flair_text"] = str(body.get("flair_text") or "").strip()
        db.update_system_config("gallery", cfg)
    if columns_present or inspiration_every_present or inspiration_texts_present:
        db = get_database()
        cfg = db.get_system_config("gallery") or {}
        if columns_present:
            try:
                cfg["columns"] = int(body.get("columns") or 0) or None
            except Exception:
                cfg["columns"] = None
        if inspiration_every_present:
            try:
                cfg["inspiration_every"] = int(body.get("inspiration_every") or 0) or None
            except Exception:
                cfg["inspiration_every"] = None
        if inspiration_texts_present:
            raw = body.get("inspiration_texts")
            if isinstance(raw, list):
                cfg["inspiration_texts"] = [str(x).strip() for x in raw if str(x).strip()]
            else:
                cfg["inspiration_texts"] = str(raw or "").strip()
        db.update_system_config("gallery", cfg)

    return web.json_response({
        "ok": True,
        "settings": payload,
        "hidden_decks": deck_payload.get("hidden_decks"),
        "flair_text": (get_database().get_system_config("gallery") or {}).get("flair_text") or "",
        "columns": (get_database().get_system_config("gallery") or {}).get("columns"),
        "inspiration_every": (get_database().get_system_config("gallery") or {}).get("inspiration_every"),
        "inspiration_texts": (get_database().get_system_config("gallery") or {}).get("inspiration_texts") or "",
    })

@route("POST", "/api/gallery/upload-channel", scopes=["tarot:admin"])
async def gallery_upload_channel_create(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    name = str(body.get("name") or "").strip()
    try:
        category_id = int(body.get("category_id") or 0)
    except Exception:
        category_id = 0
    try:
        template_channel_id = int(body.get("template_channel_id") or 0)
    except Exception:
        template_channel_id = 0
    if not name:
        return web.json_response({"ok": False, "error": "name required"}, status=400)
    if not category_id:
        return web.json_response({"ok": False, "error": "category_id required"}, status=400)
    bot = getattr(bigtree, "bot", None)
    if not bot:
        return web.json_response({"ok": False, "error": "bot not ready"}, status=503)
    category = bot.get_channel(category_id)
    if not category or not isinstance(category, discord.CategoryChannel):
        return web.json_response({"ok": False, "error": "category not found"}, status=404)
    guild = category.guild
    overwrites = {}
    topic = None
    slowmode_delay = 0
    nsfw = False
    if template_channel_id:
        template = bot.get_channel(template_channel_id)
        if template and isinstance(template, discord.TextChannel):
            overwrites = dict(template.overwrites)
            topic = template.topic
            slowmode_delay = template.slowmode_delay or 0
            nsfw = bool(template.nsfw)
    everyone = guild.default_role
    if everyone not in overwrites:
        overwrites[everyone] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    else:
        ow = overwrites[everyone]
        if ow.view_channel is not True:
            ow.view_channel = True
        if ow.send_messages is not True:
            ow.send_messages = True
        if ow.read_message_history is not True:
            ow.read_message_history = True
        overwrites[everyone] = ow
    try:
        channel = await guild.create_text_channel(
            name=name,
            category=category,
            overwrites=overwrites,
            topic=topic,
            slowmode_delay=slowmode_delay,
            nsfw=nsfw
        )
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)
    gallery_mod.set_upload_channel_id(channel.id)
    return web.json_response({"ok": True, "channel_id": channel.id, "name": channel.name})

@route("POST", "/api/gallery/import-channel", scopes=["tarot:admin"])
async def gallery_import_channel(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    channel_id = body.get("channel_id")
    origin_type = str(body.get("origin_type") or "").strip() or "Artifact"
    origin_label = str(body.get("origin_label") or "").strip()
    try:
        channel_id = int(channel_id) if channel_id else None
    except Exception:
        channel_id = None
    if not channel_id:
        return web.json_response({"ok": False, "error": "channel_id required"}, status=400)
    bot = getattr(bigtree, "bot", None)
    if not bot:
        return web.json_response({"ok": False, "error": "bot not ready"}, status=503)
    channel = bot.get_channel(channel_id)
    if not channel or not isinstance(channel, discord.TextChannel):
        return web.json_response({"ok": False, "error": "channel not found"}, status=404)

    imported = 0
    skipped = 0
    try:
        async for message in channel.history(limit=None, oldest_first=True):
            if not message.attachments:
                continue
            author = message.author
            artist_id = str(author.id)
            display_name = getattr(author, "display_name", None) or author.name
            artist_mod.upsert_artist(artist_id, display_name, {})
            base_title = _strip_emojis((message.content or "").strip())
            for idx, att in enumerate(message.attachments):
                if not _is_image_attachment(att):
                    continue
                discord_url = getattr(att, "url", None) or ""
                if discord_url and media_mod.get_media_by_discord_url(discord_url):
                    skipped += 1
                    continue
                filename = _strip_emojis(att.filename or "image")
                ext = os.path.splitext(filename)[1].lower()
                if ext not in _IMG_EXTS:
                    ext = ".png"
                save_name = f"discord_{message.id}_{idx}{ext}"
                try:
                    await att.save(fp=os.path.join(media_mod.get_media_dir(), save_name))
                except Exception:
                    skipped += 1
                    continue
                title = base_title or filename
                if idx > 0 and base_title:
                    title = f"{base_title} ({idx + 1})"
                title = title.strip() or filename
                media_mod.add_media(
                    save_name,
                    original_name=filename,
                    artist_id=artist_id,
                    title=title,
                    discord_url=discord_url,
                    origin_type=origin_type,
                    origin_label=origin_label,
                )
                imported += 1
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)

    invalidate_gallery_cache()
    return web.json_response({"ok": True, "imported": imported, "skipped": skipped})

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

@route("POST", "/api/gallery/media/update", scopes=["tarot:admin"])
async def gallery_media_update(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    item_id = str(body.get("item_id") or "").strip()
    filename = str(body.get("filename") or "").strip()
    title = str(body.get("title") or "").strip()
    artist_id = (body.get("artist_id") or "").strip() or None
    artist_name = str(body.get("artist_name") or "").strip()
    origin_type = str(body.get("origin_type") or "").strip()
    origin_label = str(body.get("origin_label") or "").strip()
    if item_id and item_id.startswith("media:"):
        filename = item_id.split(":", 1)[1]
    if not filename:
        return web.json_response({"ok": False, "error": "filename required"}, status=400)
    try:
        media_mod.add_media(
            filename,
            title=title or None,
            artist_id=artist_id,
            origin_type=origin_type or None,
            origin_label=origin_label or None,
        )
        if artist_id and artist_name:
            artist_mod.upsert_artist(artist_id, artist_name, {})
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    invalidate_gallery_cache()
    return web.json_response({"ok": True, "filename": filename})

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


@route("GET", "/gallery/with.leaf", allow_public=True)
async def get_with_leaf(_req: web.Request):
    path = get_with_leaf_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return web.Response(text=content, content_type="application/json")
    except FileNotFoundError:
        return web.Response(text="[]", content_type="application/json", status=404)


@route("GET", "/with.leaf", allow_public=True)
async def get_with_leaf_root(_req: web.Request):
    path = get_with_leaf_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return web.Response(text=content, content_type="application/json")
    except FileNotFoundError:
        return web.Response(text="[]", content_type="application/json", status=404)
