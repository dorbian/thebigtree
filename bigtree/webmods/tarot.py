# bigtree/webmods/tarot.py
from aiohttp import web
from typing import Any, Dict, List
from bigtree.inc.webserver import route, get_server, ensure_webserver, DynamicWebServer
from bigtree.modules import tarot as tar


def _json_error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "error": message}, status=status)


async def _broadcast_state(sid: str, session: Dict[str, Any] | None = None) -> None:
    srv = get_server()
    if not srv:
        return
    s = session or tar.get_session(sid)
    if not s:
        return
    await srv.broadcast({"type": "tarot_state", "sid": sid, "state": s.get("state", {})})

@route("GET", "/api/tarot/session/{sid}", allow_public=True)
async def get_state(request: web.Request):
    sid = request.match_info["sid"]
    s = tar.get_session(sid)
    if not s:
        return _json_error("not found", status=404)
    return web.json_response({"ok": True, "session": s})


@route("GET", "/api/tarot/deck/{deck}/cards", scopes=["tarot:admin"])
async def deck_cards(request: web.Request):
    deck = request.match_info["deck"]
    cards = tar.list_cards(deck)
    return web.json_response({"ok": True, "deck": deck, "cards": cards})


@route("POST", "/api/tarot/deck/{deck}/cards", scopes=["tarot:admin"])
async def deck_add_card(request: web.Request):
    deck = request.match_info["deck"]
    try:
        body = await request.json()
    except Exception:
        return _json_error("invalid json")
    title = str(body.get("title") or "").strip()
    if not title:
        return _json_error("title required")
    meaning = str(body.get("meaning") or "").strip()
    image_url = str(body.get("image_url") or body.get("image") or "").strip()
    tags = body.get("tags") or []
    if not isinstance(tags, list):
        return _json_error("tags must be a list")
    card_id = tar.add_card(deck=deck, title=title, meaning=meaning, image_url=image_url, tags=tags)
    return web.json_response({"ok": True, "card_id": card_id})


@route("POST", "/api/tarot/session", scopes=["tarot:admin"])
async def session_create(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return _json_error("invalid json")
    owner_id = int(body.get("owner_id") or 0)
    deck = str(body.get("deck") or "elf-classic").strip() or "elf-classic"
    spread = str(body.get("spread") or "single").strip() or "single"
    sid = tar.new_session(owner_id=owner_id, deck=deck, spread=spread)
    s = tar.get_session(sid)
    return web.json_response({"ok": True, "session_id": sid, "session": s})

@route("GET", "/tarot/session/{sid}", allow_public=True)
async def viewer(request: web.Request):
    sid = request.match_info["sid"]
    view = request.query.get("view","follower")
    srv: DynamicWebServer | None = get_server()
    html = (srv.render_template("tarot.html", {"SID": sid, "VIEW": view}) if srv
            else "<h1>Tarrot</h1><p>Server not initialized</p>")
    return web.Response(text=html, content_type="text/html")

@route("WS", "/ws/tarot/{sid}", allow_public=True)
async def ws_handler(_request: web.Request, _ws, _msg_text: str):
    # viewer sockets don't send control; Discord commands drive updates
    return

@route("POST", "/api/tarot/session/{sid}/draw", scopes=["tarot:control"])
async def session_draw(request: web.Request):
    sid = request.match_info["sid"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    count = int(body.get("count") or 1)
    cards = tar.draw_cards(sid, count=count)
    s = tar.get_session(sid)
    if not s:
        return _json_error("not found", status=404)
    await _broadcast_state(sid, s)
    return web.json_response({"ok": True, "drawn": cards, "session": s})


@route("POST", "/api/tarot/session/{sid}/flip", scopes=["tarot:control"])
async def session_flip(request: web.Request):
    sid = request.match_info["sid"]
    try:
        body = await request.json()
    except Exception:
        return _json_error("invalid json")
    index = body.get("index")
    if index is None:
        return _json_error("index required")
    s = tar.flip_card(sid, int(index))
    if not s:
        return _json_error("not found", status=404)
    await _broadcast_state(sid, s)
    return web.json_response({"ok": True, "session": s})


@route("POST", "/api/tarot/session/{sid}/end", scopes=["tarot:control"])
async def session_end(request: web.Request):
    sid = request.match_info["sid"]
    s = tar.get_session(sid)
    if not s:
        return _json_error("not found", status=404)
    tar.end_session(sid)
    await _broadcast_state(sid, {"state": {"drawn": [], "flipped": []}})
    return web.json_response({"ok": True})


@route("POST", "/api/tarot/push/{sid}", scopes=["tarot:control"])
async def push_state(request: web.Request):
    sid = request.match_info["sid"]
    s = tar.get_session(sid)
    if not s:
        return _json_error("not found", status=404)
    await _broadcast_state(sid, s)
    return web.json_response({"ok": True})
