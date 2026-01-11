from __future__ import annotations
from aiohttp import web
from typing import Dict, Any
import asyncio
import json
from bigtree.inc.webserver import route, get_server
from bigtree.modules import cardgames as cg

async def _run_blocking(func, *args):
    return await asyncio.to_thread(func, *args)

def _get_view(req: web.Request) -> str:
    view = str(req.query.get("view") or "player").strip().lower()
    return view if view in ("player", "priestess") else "player"

def _get_token(req: web.Request, body: Dict[str, Any]) -> str:
    return (req.headers.get("X-Cardgame-Token") or str(body.get("token") or "")).strip()

_TEMPLATES = {
    ("blackjack", "player"): "cardgames_blackjack_player.html",
    ("blackjack", "priestess"): "cardgames_blackjack_priestess.html",
    ("poker", "player"): "cardgames_poker_player.html",
    ("poker", "priestess"): "cardgames_poker_priestess.html",
    ("highlow", "player"): "cardgames_highlow_player.html",
    ("highlow", "priestess"): "cardgames_highlow_priestess.html",
}

def _render_template(name: str, mapping: Dict[str, str]) -> str:
    srv = get_server()
    if srv:
        return srv.render_template(name, mapping)
    return "<h1>Cardgames</h1>"

@route("GET", "/cardgames/{game_id}/session/{join_code}", allow_public=True)
async def cardgame_session_page(req: web.Request):
    game_id = str(req.match_info["game_id"] or "").strip().lower()
    join_code = req.match_info["join_code"]
    view = _get_view(req)
    s = await _run_blocking(cg.get_session_by_join_code, join_code)
    if not s or s.get("game_id") != game_id:
        raise web.HTTPFound("/tarot/gallery")
    tpl = _TEMPLATES.get((game_id, view))
    if not tpl:
        return web.Response(status=404, text="Not found")
    html = _render_template(tpl, {"JOIN": join_code, "GAME": game_id})
    return web.Response(text=html, content_type="text/html")

@route("POST", "/api/cardgames/{game_id}/sessions", scopes=["tarot:admin", "cardgames:admin"])
async def create_session(req: web.Request):
    game_id = str(req.match_info["game_id"] or "").strip().lower()
    try:
        body = await req.json()
    except Exception:
        body = {}
    pot = int(body.get("pot") or 0)
    deck_id = str(body.get("deck_id") or "").strip() or None
    background_url = str(body.get("background_url") or "").strip() or None
    try:
        s = await _run_blocking(cg.create_session, game_id, pot, deck_id, background_url)
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response({"ok": True, "session": s})

@route("GET", "/api/cardgames/{game_id}/sessions", scopes=["tarot:admin", "cardgames:admin"])
async def list_sessions(req: web.Request):
    game_id = str(req.match_info["game_id"] or "").strip().lower()
    sessions = await _run_blocking(cg.list_sessions, game_id)
    return web.json_response({"ok": True, "sessions": sessions})

@route("GET", "/api/cardgames/sessions", scopes=["tarot:admin", "cardgames:admin"])
async def list_all_sessions(req: web.Request):
    sessions = await _run_blocking(cg.list_sessions, None)
    return web.json_response({"ok": True, "sessions": sessions})

@route("POST", "/api/cardgames/{game_id}/sessions/{join_code}/join", allow_public=True)
async def join_session(req: web.Request):
    join_code = req.match_info["join_code"]
    try:
        payload = await _run_blocking(cg.join_session, join_code)
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc), "redirect": "/tarot/gallery"}, status=400)
    return web.json_response({"ok": True, **payload})

@route("GET", "/api/cardgames/{game_id}/sessions/{join_code}/state", allow_public=True)
async def get_state(req: web.Request):
    join_code = req.match_info["join_code"]
    view = _get_view(req)
    s = await _run_blocking(cg.get_session_by_join_code, join_code)
    if not s:
        return web.json_response({"ok": False, "error": "not found", "redirect": "/tarot/gallery"}, status=404)
    return web.json_response({"ok": True, "state": cg.get_state(s, view=view)})

@route("GET", "/api/cardgames/{game_id}/sessions/{join_code}/stream", allow_public=True)
async def stream_events(req: web.Request):
    join_code = req.match_info["join_code"]
    view = _get_view(req)
    s = await _run_blocking(cg.get_session_by_join_code, join_code)
    if not s:
        return web.json_response({"ok": False, "error": "not found", "redirect": "/tarot/gallery"}, status=404)

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
    initial = {"type": "STATE", "state": cg.get_state(s, view=view)}
    await resp.write(f"data: {json.dumps(initial)}\n\n".encode("utf-8"))
    session_id = s["session_id"]
    try:
        while True:
            await asyncio.sleep(1.0)
            current = await _run_blocking(cg.get_session_by_id, session_id)
            if not current:
                payload = {"type": "SESSION_GONE", "redirect": "/tarot/gallery"}
                await resp.write(f"data: {json.dumps(payload)}\n\n".encode("utf-8"))
                break
            events = await _run_blocking(cg.list_events, session_id, last_seq)
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

@route("POST", "/api/cardgames/{game_id}/sessions/{session_id}/start", allow_public=True)
async def start_session(req: web.Request):
    session_id = req.match_info["session_id"]
    try:
        body = await req.json()
    except Exception:
        body = {}
    token = _get_token(req, body)
    try:
        await _run_blocking(cg.start_session, session_id, token)
    except PermissionError:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=403)
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response({"ok": True})

@route("POST", "/api/cardgames/{game_id}/sessions/{session_id}/action", allow_public=True)
async def player_action(req: web.Request):
    session_id = req.match_info["session_id"]
    try:
        body = await req.json()
    except Exception:
        body = {}
    token = _get_token(req, body)
    action = str(body.get("action") or "").strip().lower()
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    try:
        s = await _run_blocking(cg.player_action, session_id, token, action, payload)
    except PermissionError:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=403)
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response({"ok": True, "session": s})

@route("POST", "/api/cardgames/{game_id}/sessions/{session_id}/host-action", allow_public=True)
async def host_action(req: web.Request):
    session_id = req.match_info["session_id"]
    try:
        body = await req.json()
    except Exception:
        body = {}
    token = _get_token(req, body)
    action = str(body.get("action") or "").strip().lower()
    try:
        s = await _run_blocking(cg.host_action, session_id, token, action)
    except PermissionError:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=403)
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response({"ok": True, "session": s})

@route("POST", "/api/cardgames/{game_id}/sessions/{session_id}/finish", allow_public=True)
async def finish_session(req: web.Request):
    session_id = req.match_info["session_id"]
    try:
        body = await req.json()
    except Exception:
        body = {}
    token = _get_token(req, body)
    try:
        await _run_blocking(cg.finish_session, session_id, token)
    except PermissionError:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=403)
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response({"ok": True})

@route("POST", "/api/cardgames/{game_id}/sessions/{session_id}/clone", allow_public=True)
async def clone_session(req: web.Request):
    session_id = req.match_info["session_id"]
    try:
        body = await req.json()
    except Exception:
        body = {}
    token = _get_token(req, body)
    s = await _run_blocking(cg.get_session_by_id, session_id)
    if not s:
        return web.json_response({"ok": False, "error": "not found"}, status=404)
    if token != s.get("priestess_token"):
        return web.json_response({"ok": False, "error": "unauthorized"}, status=403)
    try:
        new_session = await _run_blocking(
            cg.create_session,
            s.get("game_id"),
            int(s.get("pot") or 0),
            s.get("deck_id"),
            s.get("background_url"),
        )
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response({"ok": True, "session": new_session})

@route("POST", "/api/cardgames/{game_id}/sessions/{session_id}/delete", allow_public=True)
async def delete_session(req: web.Request):
    session_id = req.match_info["session_id"]
    try:
        body = await req.json()
    except Exception:
        body = {}
    token = _get_token(req, body)
    try:
        await _run_blocking(cg.delete_session, session_id, token)
    except PermissionError:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=403)
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response({"ok": True})
