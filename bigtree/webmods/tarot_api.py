# bigtree/webmods/tarot_api.py
from __future__ import annotations
import asyncio
import json
from aiohttp import web
from bigtree.inc.webserver import route, get_server, DynamicWebServer
from bigtree.modules import tarot as tar

def _json_error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "error": message}, status=status)

def _get_token(req: web.Request, body: dict) -> str:
    return (req.headers.get("X-Tarot-Token") or str(body.get("token") or "")).strip()

def _get_view(req: web.Request) -> str:
    view = (req.query.get("view") or "player").strip().lower()
    if view not in ("priestess", "player", "overlay"):
        return "player"
    return view

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
