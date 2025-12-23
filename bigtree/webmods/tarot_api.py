# bigtree/webmods/tarot_api.py
from __future__ import annotations
import asyncio
import json
import logging
from aiohttp import web
import os
import uuid
import json as _json
import imghdr
from pathlib import Path
import bigtree
from bigtree.inc.webserver import route, get_server, DynamicWebServer
from bigtree.modules import tarot as tar

log = getattr(bigtree, "logger", logging.getLogger("bigtree"))

def _json_error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "error": message}, status=status)

def _get_token(req: web.Request, body: dict) -> str:
    return (req.headers.get("X-Tarot-Token") or str(body.get("token") or "")).strip()

def _get_view(req: web.Request) -> str:
    view = (req.query.get("view") or "player").strip().lower()
    if view not in ("priestess", "player", "overlay"):
        return "player"
    return view

def _data_dir() -> str:
    try:
        import bigtree
        settings = getattr(bigtree, "settings", None)
        if settings:
            base = settings.get("BOT.DATA_DIR", None)
            if base:
                return base
    except Exception:
        pass
    return os.getenv("BIGTREE__BOT__DATA_DIR") or os.getenv("BIGTREE_DATA_DIR") or "/data"

def _cards_dir() -> str:
    base = _data_dir()
    path = os.path.join(base, "tarot", "cards")
    os.makedirs(path, exist_ok=True)
    return path

def _backs_dir() -> str:
    base = _data_dir()
    path = os.path.join(base, "tarot", "backs")
    os.makedirs(path, exist_ok=True)
    return path

def _safe_name(name: str) -> str:
    keep = []
    for ch in (name or ""):
        if ch.isalnum() or ch in ("-", "_"):
            keep.append(ch)
    return "".join(keep)

_HOUSES_CACHE: dict | None = None
_HOUSES_WARNED = False

def _read_json(path: Path) -> dict | None:
    try:
        return _json.loads(path.read_text("utf-8"))
    except Exception:
        return None

def _load_houses() -> dict:
    global _HOUSES_CACHE
    global _HOUSES_WARNED
    if _HOUSES_CACHE is not None:
        return _HOUSES_CACHE
    candidates: list[Path] = []
    env_path = os.getenv("BIGTREE_TAROT_HOUSES")
    if env_path:
        candidates.append(Path(env_path))
    data_dir = Path(_data_dir())
    candidates.extend([
        data_dir / "tarot" / "houses.json",
        data_dir / "tarot" / "tarrot_help.json",
        data_dir / "tarrot_help.json",
    ])
    try:
        repo_root = Path(__file__).resolve().parents[2]
        candidates.extend([
            repo_root / "tarrot_help.json",
            repo_root / "defaults" / "tarrot_help.json",
        ])
    except Exception:
        pass
    candidates.append(Path(__file__).resolve().parent / "tarrot_help.json")
    for path in candidates:
        if path.exists():
            data = _read_json(path)
            if data:
                _HOUSES_CACHE = data
                return _HOUSES_CACHE
    if not _HOUSES_WARNED:
        _HOUSES_WARNED = True
        log.warning("[tarot] houses file not found; checked: %s", ", ".join(str(p) for p in candidates))
    _HOUSES_CACHE = {"houses": []}
    return _HOUSES_CACHE

def _dummy_cards(deck_id: str, per_house: int, crown_count: int) -> list[dict]:
    houses = _load_houses().get("houses", [])
    cards = []
    for house in houses:
        hid = house.get("id") or ""
        hname = house.get("name") or hid
        keywords = ", ".join(house.get("keywords") or [])
        count = crown_count if hid == "crown" else per_house
        for idx in range(max(0, int(count))):
            title = f"{hname} - Echo {idx + 1}"
            card = {
                "card_id": f"{hid}_dummy_{idx + 1}",
                "name": title,
                "house": hid,
                "upright": f"Upright: {keywords}.",
                "reversed": f"Reversed: blocked or twisted {keywords}.",
                "tags": house.get("keywords") or [],
                "image": "",
                "artist_links": {},
            }
            cards.append(card)
    return cards

# ---- Pages ----
@route("GET", "/tarot/session/{join_code}", allow_public=True)
async def tarot_session_page(req: web.Request):
    join_code = req.match_info["join_code"]
    view = _get_view(req)
    srv: DynamicWebServer | None = get_server()
    tpl = "tarot_priestess.html" if view == "priestess" else "tarot_player.html"
    html = srv.render_template(tpl, {"JOIN": join_code}) if srv else "<h1>Tarot</h1>"
    return web.Response(text=html, content_type="text/html")

@route("GET", "/", allow_public=True)
async def tarot_gallery_root(_req: web.Request):
    srv: DynamicWebServer | None = get_server()
    html = srv.render_template("tarot_gallery.html", {}) if srv else "<h1>Tarot</h1>"
    return web.Response(text=html, content_type="text/html")

@route("GET", "/tarot/gallery", allow_public=True)
async def tarot_gallery_page(_req: web.Request):
    srv: DynamicWebServer | None = get_server()
    html = srv.render_template("tarot_gallery.html", {}) if srv else "<h1>Tarot</h1>"
    return web.Response(text=html, content_type="text/html")

@route("GET", "/tarot/admin", allow_public=True)
async def tarot_admin_page(_req: web.Request):
    srv: DynamicWebServer | None = get_server()
    html = srv.render_template("tarot_admin.html", {}) if srv else "<h1>Tarot Admin</h1>"
    return web.Response(text=html, content_type="text/html")

@route("GET", "/tarot/cards/{filename}", allow_public=True)
async def tarot_card_file(req: web.Request):
    filename = req.match_info["filename"]
    base = _cards_dir()
    path = os.path.join(base, filename)
    if not os.path.exists(path):
        return web.Response(status=404)
    return web.FileResponse(path)

@route("GET", "/tarot/backs/{filename}", allow_public=True)
async def tarot_back_file(req: web.Request):
    filename = req.match_info["filename"]
    base = _backs_dir()
    path = os.path.join(base, filename)
    if not os.path.exists(path):
        return web.Response(status=404)
    return web.FileResponse(path)

@route("GET", "/api/tarot/houses", allow_public=True)
async def tarot_houses(_req: web.Request):
    return web.json_response({"ok": True, "houses": _load_houses().get("houses", [])})

@route("GET", "/overlay/session/{join_code}", allow_public=True)
async def tarot_overlay_page(req: web.Request):
    join_code = req.match_info["join_code"]
    srv: DynamicWebServer | None = get_server()
    html = srv.render_template("tarot_overlay.html", {"JOIN": join_code}) if srv else "<h1>Tarot Overlay</h1>"
    return web.Response(text=html, content_type="text/html")

# ---- Sessions ----
@route("POST", "/api/tarot/sessions", scopes=["tarot:admin"])
async def create_session(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        return _json_error("invalid json")
    deck_id = str(body.get("deck_id") or body.get("deck") or "elf-classic")
    spread_id = str(body.get("spread_id") or body.get("spread") or "single")
    priestess_id = int(body.get("priestess_id") or body.get("owner_id") or 0)
    s = tar.create_session(priestess_id, deck_id, spread_id)
    return web.json_response({
        "ok": True,
        "sessionId": s["session_id"],
        "joinCode": s["join_code"],
        "priestessToken": s["priestess_token"],
    })

@route("GET", "/api/tarot/sessions", scopes=["tarot:admin"])
async def list_sessions(req: web.Request):
    sessions = []
    for s in tar.list_sessions():
        sessions.append({
            "session_id": s.get("session_id"),
            "join_code": s.get("join_code"),
            "priestess_token": s.get("priestess_token"),
            "deck_id": s.get("deck_id"),
            "spread_id": s.get("spread_id"),
            "status": s.get("status"),
            "created_at": s.get("created_at"),
        })
    return web.json_response({"ok": True, "sessions": sessions})

@route("POST", "/api/tarot/sessions/{join_code}/join", allow_public=True)
async def join_session(req: web.Request):
    join_code = req.match_info["join_code"]
    try:
        body = await req.json()
    except Exception:
        body = {}
    viewer_id = body.get("viewer_id")
    try:
        joined = tar.join_session(join_code, viewer_id=viewer_id)
    except Exception:
        return _json_error("not found", status=404)
    return web.json_response({
        "ok": True,
        "viewerToken": joined["viewer_token"],
    })

@route("GET", "/api/tarot/sessions/{join_code}/state", allow_public=True)
async def get_state(req: web.Request):
    join_code = req.match_info["join_code"]
    view = _get_view(req)
    s = tar.get_session_by_join_code(join_code)
    if not s:
        return _json_error("not found", status=404)
    return web.json_response({"ok": True, "state": tar.get_state(s, view=view)})

@route("GET", "/api/tarot/sessions/{join_code}/stream", allow_public=True)
async def stream_events(req: web.Request):
    join_code = req.match_info["join_code"]
    view = _get_view(req)
    s = tar.get_session_by_join_code(join_code)
    if not s:
        return _json_error("not found", status=404)

    resp = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await resp.prepare(req)

    last_seq = 0
    initial = {"type": "STATE", "state": tar.get_state(s, view=view)}
    await resp.write(f"data: {json.dumps(initial)}\n\n".encode("utf-8"))

    try:
        while True:
            await asyncio.sleep(1.0)
            events = tar.list_events(s["session_id"], last_seq)
            if events:
                last_seq = int(events[-1].get("seq", last_seq))
                for ev in events:
                    payload = {"type": ev.get("type"), "data": ev.get("data"), "seq": ev.get("seq")}
                    await resp.write(f"data: {json.dumps(payload)}\n\n".encode("utf-8"))
    except asyncio.CancelledError:
        pass
    except Exception:
        pass
    return resp

# ---- Priestess controls ----
@route("POST", "/api/tarot/sessions/{session_id}/start", scopes=["tarot:control"])
async def start_session(req: web.Request):
    session_id = req.match_info["session_id"]
    body = await req.json()
    token = _get_token(req, body)
    try:
        tar.start_session(session_id, token)
    except PermissionError:
        return _json_error("unauthorized", status=403)
    except Exception:
        return _json_error("not found", status=404)
    return web.json_response({"ok": True})

@route("POST", "/api/tarot/sessions/{session_id}/shuffle", scopes=["tarot:control"])
async def shuffle_session(req: web.Request):
    session_id = req.match_info["session_id"]
    body = await req.json()
    token = _get_token(req, body)
    try:
        tar.shuffle_session(session_id, token)
    except PermissionError:
        return _json_error("unauthorized", status=403)
    except Exception:
        return _json_error("not found", status=404)
    return web.json_response({"ok": True})

@route("POST", "/api/tarot/sessions/{session_id}/draw", scopes=["tarot:control"])
async def draw_cards(req: web.Request):
    session_id = req.match_info["session_id"]
    body = await req.json()
    token = _get_token(req, body)
    try:
        tar.draw_cards(
            session_id,
            token,
            count=int(body.get("count") or 1),
            position_id=body.get("position_id"),
        )
    except PermissionError:
        return _json_error("unauthorized", status=403)
    except Exception as ex:
        return _json_error(str(ex), status=400)
    return web.json_response({"ok": True})

@route("POST", "/api/tarot/sessions/{session_id}/reveal", scopes=["tarot:control"])
async def reveal_card(req: web.Request):
    session_id = req.match_info["session_id"]
    body = await req.json()
    token = _get_token(req, body)
    mode = str(body.get("mode") or "next")
    position_id = body.get("position_id")
    try:
        tar.reveal(session_id, token, mode="position" if position_id else mode, position_id=position_id)
    except PermissionError:
        return _json_error("unauthorized", status=403)
    except Exception as ex:
        return _json_error(str(ex), status=400)
    return web.json_response({"ok": True})

@route("POST", "/api/tarot/sessions/{session_id}/narrate", scopes=["tarot:control"])
async def narrate(req: web.Request):
    session_id = req.match_info["session_id"]
    body = await req.json()
    token = _get_token(req, body)
    text = str(body.get("text") or "")
    style = body.get("style")
    try:
        tar.add_narration(session_id, token, text=text, style=style)
    except PermissionError:
        return _json_error("unauthorized", status=403)
    except Exception as ex:
        return _json_error(str(ex), status=400)
    return web.json_response({"ok": True})

@route("POST", "/api/tarot/sessions/{session_id}/finish", scopes=["tarot:control"])
async def finish(req: web.Request):
    session_id = req.match_info["session_id"]
    body = await req.json()
    token = _get_token(req, body)
    try:
        tar.finish_session(session_id, token)
    except PermissionError:
        return _json_error("unauthorized", status=403)
    except Exception:
        return _json_error("not found", status=404)
    return web.json_response({"ok": True})

# ---- Deck endpoints ----
@route("POST", "/api/tarot/decks", scopes=["tarot:admin"])
async def create_deck(req: web.Request):
    body = await req.json()
    deck_id = str(body.get("deck_id") or body.get("id") or "elf-classic")
    name = body.get("name")
    deck = tar.create_deck(deck_id, name=name)
    return web.json_response({"ok": True, "deck": deck})

@route("GET", "/api/tarot/decks", scopes=["tarot:admin"])
async def list_decks(req: web.Request):
    decks = tar.list_decks()
    return web.json_response({"ok": True, "decks": decks})

@route("GET", "/api/tarot/decks/{deck_id}", scopes=["tarot:admin"])
async def get_deck(req: web.Request):
    deck_id = req.match_info["deck_id"]
    deck = tar.get_deck(deck_id)
    if not deck:
        return _json_error("not found", status=404)
    cards = tar.list_cards(deck_id)
    return web.json_response({"ok": True, "deck": deck, "cards": cards})

@route("GET", "/api/tarot/decks/{deck_id}/public", allow_public=True)
async def get_deck_public(req: web.Request):
    deck_id = req.match_info["deck_id"]
    deck = tar.get_deck(deck_id)
    if not deck:
        return _json_error("not found", status=404)
    cards = []
    for c in tar.list_cards(deck_id):
        cards.append({
            "card_id": c.get("card_id"),
            "name": c.get("name"),
            "house": c.get("house"),
            "tags": c.get("tags", []),
            "image": c.get("image"),
            "artist_links": c.get("artist_links", {}),
        })
    return web.json_response({"ok": True, "deck": deck, "cards": cards})

@route("POST", "/api/tarot/decks/{deck_id}/cards", scopes=["tarot:admin"])
async def add_card(req: web.Request):
    deck_id = req.match_info["deck_id"]
    body = await req.json()
    try:
        card = tar.add_or_update_card(deck_id, body)
    except Exception as ex:
        return _json_error(str(ex), status=400)
    return web.json_response({"ok": True, "card": card})

@route("POST", "/api/tarot/decks/{deck_id}/seed", scopes=["tarot:admin"])
async def seed_deck(req: web.Request):
    deck_id = req.match_info["deck_id"]
    try:
        body = await req.json()
    except Exception:
        body = {}
    per_house = int(body.get("per_house") or 4)
    crown_count = int(body.get("crown_count") or 1)
    tar.create_deck(deck_id, name=body.get("name"))
    created = []
    for card in _dummy_cards(deck_id, per_house, crown_count):
        try:
            created.append(tar.add_or_update_card(deck_id, card))
        except Exception:
            continue
    return web.json_response({"ok": True, "created": len(created)})

@route("PUT", "/api/tarot/decks/{deck_id}/back", scopes=["tarot:admin"])
async def set_back(req: web.Request):
    deck_id = req.match_info["deck_id"]
    body = await req.json()
    back = str(body.get("back_image") or body.get("url") or "")
    if not back:
        return _json_error("back_image required")
    ok = tar.set_deck_back(deck_id, back)
    if not ok:
        return _json_error("not found", status=404)
    return web.json_response({"ok": True})

@route("POST", "/api/tarot/upload-card-image", scopes=["tarot:admin"])
async def upload_card_image(req: web.Request):
    reader = await req.multipart()
    file_part = None
    card_id = ""
    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "file":
            file_part = part
        elif part.name == "card_id":
            card_id = (await part.text()).strip()
    if file_part is None:
        return _json_error("file required")

    safe_id = _safe_name(card_id) or uuid.uuid4().hex
    filename = f"{safe_id}.png"
    dest = os.path.join(_cards_dir(), filename)

    data = bytearray()
    while True:
        chunk = await file_part.read_chunk()
        if not chunk:
            break
        data.extend(chunk)

    saved = False
    try:
        from PIL import Image
        from io import BytesIO
        with Image.open(BytesIO(data)) as img:
            img = img.convert("RGBA")
            target_ratio = 3.0 / 4.2
            w, h = img.size
            ratio = w / h if h else target_ratio
            if ratio > target_ratio:
                new_w = int(h * target_ratio)
                left = (w - new_w) // 2
                img = img.crop((left, 0, left + new_w, h))
            elif ratio < target_ratio:
                new_h = int(w / target_ratio) if target_ratio else h
                top = (h - new_h) // 2
                img = img.crop((0, top, w, top + new_h))
            img.save(dest, format="PNG")
            saved = True
    except Exception:
        saved = False

    if not saved:
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
            raw_name = getattr(file_part, "filename", "") or ""
            raw_ext = Path(raw_name).suffix.lower()
            alias = {".jpeg": ".jpg", ".jfif": ".jpg"}
            raw_ext = alias.get(raw_ext, raw_ext)
            if raw_ext in {".png", ".jpg", ".gif", ".bmp", ".webp"}:
                ext = raw_ext
        if not ext:
            return _json_error("unsupported image format")
        filename = f"{safe_id}{ext}"
        dest = os.path.join(_cards_dir(), filename)
        with open(dest, "wb") as f:
            f.write(data)

    url = f"/tarot/cards/{filename}"
    return web.json_response({"ok": True, "url": url})

@route("POST", "/api/tarot/upload-back-image", scopes=["tarot:admin"])
async def upload_back_image(req: web.Request):
    reader = await req.multipart()
    file_part = None
    deck_id = ""
    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "file":
            file_part = part
        elif part.name == "deck_id":
            deck_id = (await part.text()).strip()
    if file_part is None:
        return _json_error("file required")
    if not deck_id:
        return _json_error("deck_id required")

    safe_id = _safe_name(deck_id) or uuid.uuid4().hex
    unique = uuid.uuid4().hex[:8]
    filename = f"{safe_id}_back_{unique}.png"
    dest = os.path.join(_backs_dir(), filename)

    data = bytearray()
    while True:
        chunk = await file_part.read_chunk()
        if not chunk:
            break
        data.extend(chunk)

    saved = False
    try:
        from PIL import Image
        from io import BytesIO
        with Image.open(BytesIO(data)) as img:
            img = img.convert("RGBA")
            target_ratio = 3.0 / 4.2
            w, h = img.size
            ratio = w / h if h else target_ratio
            if ratio > target_ratio:
                new_w = int(h * target_ratio)
                left = (w - new_w) // 2
                img = img.crop((left, 0, left + new_w, h))
            elif ratio < target_ratio:
                new_h = int(w / target_ratio) if target_ratio else h
                top = (h - new_h) // 2
                img = img.crop((0, top, w, top + new_h))
            img.save(dest, format="PNG")
            saved = True
    except Exception:
        saved = False

    if not saved:
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
            raw_name = getattr(file_part, "filename", "") or ""
            raw_ext = Path(raw_name).suffix.lower()
            alias = {".jpeg": ".jpg", ".jfif": ".jpg"}
            raw_ext = alias.get(raw_ext, raw_ext)
            if raw_ext in {".png", ".jpg", ".gif", ".bmp", ".webp"}:
                ext = raw_ext
        if not ext:
            return _json_error("unsupported image format")
        filename = f"{safe_id}_back_{unique}{ext}"
        dest = os.path.join(_backs_dir(), filename)
        with open(dest, "wb") as f:
            f.write(data)

    url = f"/tarot/backs/{filename}"
    tar.set_deck_back(deck_id, url)
    return web.json_response({"ok": True, "url": url})
