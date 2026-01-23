from __future__ import annotations
from aiohttp import web, WSMsgType
from typing import Dict, Any
import asyncio
import json
from bigtree.inc.webserver import route, get_server
from bigtree.modules import cardgames as cg
from bigtree.inc.database import get_database
from bigtree.inc import web_tokens
from bigtree.modules import tarot
from bigtree.webmods.user_area import _resolve_user

async def _run_blocking(func, *args):
    return await asyncio.to_thread(func, *args)

def _get_view(req: web.Request) -> str:
    view = str(req.query.get("view") or "player").strip().lower()
    return view if view in ("player", "priestess") else "player"

def _get_token(req: web.Request, body: Dict[str, Any]) -> str:
    return (req.headers.get("X-Cardgame-Token") or str(body.get("token") or "")).strip()

def _extract_admin_token(req: web.Request) -> str:
    auth = req.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth.split(" ", 1)[1].strip()
    return req.headers.get("X-Bigtree-Key") or req.headers.get("X-API-Key") or ""

async def _send_ws_state(ws: web.WebSocketResponse, session: Dict[str, Any], view: str, token: str):
    state = cg.get_state(session, view=view, token=token)
    await ws.send_json({"type": "STATE", "state": state})

@route("GET", "/ws/cardgames/{game_id}/sessions/{join_code}", allow_public=True)
async def ws_stream(req: web.Request):
    join_code = req.match_info["join_code"]
    view = _get_view(req)
    token = str(req.query.get("token") or "").strip()
    ws = web.WebSocketResponse(heartbeat=30.0)
    await ws.prepare(req)
    session = await _run_blocking(cg.get_session_by_join_code, join_code)
    if not session:
        await ws.send_json({"type": "SESSION_GONE", "redirect": "/gallery"})
        await ws.close()
        return ws
    session_id = session["session_id"]
    last_seq = 0
    last_seen = asyncio.get_event_loop().time()
    await _send_ws_state(ws, session, view, token)

    while not ws.closed:
        now = asyncio.get_event_loop().time()
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=1.0)
        except asyncio.TimeoutError:
            msg = None
        if msg is not None:
            if msg.type == WSMsgType.TEXT:
                last_seen = now
                try:
                    payload = json.loads(msg.data or "{}")
                except Exception:
                    payload = {}
                if isinstance(payload, dict):
                    if payload.get("type") == "auth":
                        token = str(payload.get("token") or "").strip()
                        await _send_ws_state(ws, session, view, token)
                    elif payload.get("type") == "resume":
                        await _send_ws_state(ws, session, view, token)
            elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.ERROR):
                break
        if now - last_seen > 300:
            await ws.close(message=b"idle")
            break
        current = await _run_blocking(cg.get_session_by_id, session_id)
        if not current:
            await ws.send_json({"type": "SESSION_GONE", "redirect": "/gallery"})
            await ws.close()
            break
        events = await _run_blocking(cg.list_events, session_id, last_seq)
        if events:
            last_seq = int(events[-1].get("seq", last_seq))
            for ev in events:
                await ws.send_json({"type": ev.get("type"), "data": ev.get("data"), "seq": ev.get("seq")})
    return ws

def _resolve_admin_user_id(req: web.Request) -> int | None:
    token = _extract_admin_token(req)
    if not token:
        return None
    doc = web_tokens.find_token(token) or {}
    raw = doc.get("user_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except Exception:
        return None

def _normalize_currency(value: Any) -> str:
    return str(value or "").strip().lower()

def _sync_game_record(db, payload: Dict[str, Any]) -> None:
    if not payload:
        return
    status_val = payload.get("status") or "created"
    active = str(status_val).lower() not in ("finished", "ended", "complete", "closed")
    metadata = {
        "currency": payload.get("currency"),
        "pot": payload.get("pot"),
        "status": status_val,
    }
    db.upsert_game(
        game_id=str(payload.get("session_id") or payload.get("join_code") or ""),
        module="cardgames",
        payload=payload,
        title=payload.get("game_id"),
        created_by=None,
        created_at=db._as_datetime(payload.get("created_at")),
        ended_at=db._as_datetime(payload.get("updated_at")),
        status=status_val,
        active=active,
        metadata=metadata,
        run_source=payload.get("run_source") or "api",
    )

async def _finish_for_zero_balance(db, ctx: Dict[str, Any], user_id: int, session: Dict[str, Any]) -> bool:
    if not ctx or not session:
        return False
    game_id = str(session.get("game_id") or "").strip().lower()
    if game_id not in ("slots", "blackjack", "poker", "highlow"):
        return False
    try:
        event_id = int(ctx.get("event_id") or 0)
    except Exception:
        event_id = 0
    if event_id <= 0 or user_id <= 0:
        return False
    balance = db.get_event_wallet_balance(event_id, int(user_id))
    if balance > 0:
        return False
    token = session.get("priestess_token") or ""
    try:
        await _run_blocking(cg.finish_session, session.get("session_id"), token)
    except Exception:
        return False
    try:
        updated = await _run_blocking(cg.get_session_by_id, session.get("session_id"))
    except Exception:
        updated = None
    _sync_game_record(db, dict(updated or session))
    return True

async def _ensure_wallet_balance(req: web.Request, join_code: str, session: Dict[str, Any]) -> web.Response | Dict[str, Any] | None:
    db = get_database()
    ctx = db.get_game_wallet_context(join_code=join_code, game_id=session.get("session_id"))
    if not ctx:
        return None
    if not ctx.get("wallet_enabled"):
        return None
    currency = _normalize_currency(ctx.get("currency"))
    if not currency or currency == "gil":
        return None
    pot = int(ctx.get("pot") or 0)
    if pot <= 0:
        return None
    user = await _resolve_user(req)
    if isinstance(user, web.Response):
        return user
    event_id = int(ctx.get("event_id") or 0)
    game_id = ctx.get("game_id") or session.get("session_id")
    if db.has_wallet_history_entry(event_id=event_id, user_id=int(user["id"]), reason="game_join", game_id=game_id):
        db.add_user_game(int(user["id"]), str(game_id), role="player")
        return {"user": user}
    ok, balance, status = db.apply_game_wallet_delta(
        event_id=event_id,
        user_id=int(user["id"]),
        delta=-pot,
        reason="game_join",
        metadata={"game_id": str(game_id), "join_code": join_code, "currency": currency, "amount": pot},
        allow_negative=False,
    )
    if not ok:
        return web.json_response(
            {
                "ok": False,
                "error": "insufficient balance",
                "required": pot,
                "balance": balance,
            },
            status=409,
        )
    db.add_user_game(int(user["id"]), str(game_id), role="player")
    return {"user": user, "balance": balance}

_TEMPLATES = {
    ("blackjack", "player"): "cardgames_blackjack_player.html",
    ("blackjack", "priestess"): "cardgames_blackjack_priestess.html",
    ("poker", "player"): "cardgames_poker_player.html",
    ("poker", "priestess"): "cardgames_poker_priestess.html",
    ("highlow", "player"): "cardgames_highlow_player.html",
    ("highlow", "priestess"): "cardgames_highlow_priestess.html",
    ("slots", "player"): "cardgames_slots_player.html",
    ("slots", "priestess"): "cardgames_slots_priestess.html",
    ("crapslite", "player"): "cardgames_crapslite_player.html",
    ("crapslite", "priestess"): "cardgames_crapslite_priestess.html",
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
        return web.Response(status=404, text="Session not found.")
    tpl = _TEMPLATES.get((game_id, view))
    if not tpl:
        return web.Response(status=404, text="Not found")
    html = _render_template(tpl, {"JOIN": join_code, "GAME": game_id})
    return web.Response(text=html, content_type="text/html")

@route("GET", "/cardgames/join", allow_public=True)
async def join_any_game(req: web.Request):
    join_code = str(req.query.get("code") or "").strip()
    if not join_code:
        return web.Response(status=404, text="Join code is required.")
    s = await _run_blocking(cg.get_session_by_join_code, join_code)
    if s and s.get("game_id"):
        raise web.HTTPFound(f"/cardgames/{s['game_id']}/session/{join_code}")
    t = await _run_blocking(tarot.get_session_by_join_code, join_code)
    if t:
        raise web.HTTPFound(f"/tarot/session/{join_code}")
    return web.Response(status=404, text="Session not found.")

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
    background_artist_id = str(body.get("background_artist_id") or "").strip() or None
    background_artist_name = str(body.get("background_artist_name") or "").strip() or None
    currency = str(body.get("currency") or "").strip() or None
    status = str(body.get("status") or "").strip().lower()
    if not status and body.get("draft"):
        status = "draft"
    try:
        s = await _run_blocking(
            cg.create_session,
            game_id,
            pot,
            deck_id,
            background_url,
            background_artist_id,
            background_artist_name,
            currency,
            status or None,
        )
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    try:
        db = get_database()
        creator = await _resolve_user(req)
        created_by = None
        if not isinstance(creator, web.Response) and isinstance(creator, dict):
            created_by = creator.get("discord_id") or creator.get("discordId") or creator.get("discord")
            try:
                created_by = int(created_by) if created_by is not None else None
            except Exception:
                created_by = None
        if created_by is None:
            created_by = _resolve_admin_user_id(req)
        payload = dict(s or {})
        status_val = payload.get("status") or "created"
        active = str(status_val).lower() not in ("finished", "ended", "complete", "closed")
        metadata = {
            "currency": payload.get("currency"),
            "pot": payload.get("pot"),
            "status": status_val,
        }
        players = db._extract_cardgame_players(payload)
        db.upsert_game(
            game_id=str(payload.get("session_id") or payload.get("join_code") or ""),
            module="cardgames",
            payload=payload,
            title=payload.get("game_id"),
            created_by=created_by,
            created_at=db._as_datetime(payload.get("created_at")),
            ended_at=db._as_datetime(payload.get("updated_at")),
            status=status_val,
            active=active,
            metadata=metadata,
            run_source="api",
            players=players,
        )
    except Exception:
        pass
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
    s = await _run_blocking(cg.get_session_by_join_code, join_code)
    if not s:
        return web.json_response({"ok": False, "error": "not found", "redirect": "/gallery"}, status=404)
    # Slots + crapslite place/charge bets during actions, not on join.
    if str(s.get("game_id") or "").lower() not in ("slots", "crapslite"):
        wallet_resp = await _ensure_wallet_balance(req, join_code, s)
        if isinstance(wallet_resp, web.Response):
            return wallet_resp
    player_meta = None
    try:
        u = await _resolve_user(req)
        if not isinstance(u, web.Response) and isinstance(u, dict):
            player_meta = u
    except Exception:
        player_meta = None
    try:
        payload = await _run_blocking(cg.join_session, join_code, player_meta)
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc), "redirect": "/gallery"}, status=400)
    return web.json_response({"ok": True, **payload})

@route("GET", "/api/cardgames/{game_id}/sessions/{join_code}/state", allow_public=True)
async def get_state(req: web.Request):
    join_code = req.match_info["join_code"]
    view = _get_view(req)
    s = await _run_blocking(cg.get_session_by_join_code, join_code)
    if not s:
        return web.json_response({"ok": False, "error": "not found", "redirect": "/gallery"}, status=404)
    token = req.headers.get("X-Cardgame-Token") or ""
    state = cg.get_state(s, view=view, token=token)
    try:
        db = get_database()
        ctx = db.get_game_wallet_context(join_code=s.get("join_code"), game_id=s.get("session_id"))
        wallet_enabled = bool(ctx and ctx.get("wallet_enabled"))
        wallet_currency = _normalize_currency(ctx.get("currency")) if ctx else ""
        needs_wallet = wallet_enabled and wallet_currency and wallet_currency != "gil"
        if needs_wallet:
            user = await _resolve_user(req)
            if not isinstance(user, web.Response) and isinstance(user, dict):
                event_id = int(ctx.get("event_id") or 0)
                if event_id > 0:
                    balance = db.get_event_wallet_balance(event_id, int(user.get("id") or 0))
                    state["wallet_balance"] = balance
                    state["wallet_currency"] = wallet_currency
    except Exception:
        pass
    return web.json_response({"ok": True, "state": state})

@route("GET", "/api/cardgames/{game_id}/sessions/{join_code}/stream", allow_public=True)
async def stream_events(req: web.Request):
    join_code = req.match_info["join_code"]
    view = _get_view(req)
    s = await _run_blocking(cg.get_session_by_join_code, join_code)
    if not s:
        return web.json_response({"ok": False, "error": "not found", "redirect": "/gallery"}, status=404)

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
    token = req.headers.get("X-Cardgame-Token") or ""
    initial = {"type": "STATE", "state": cg.get_state(s, view=view, token=token)}
    await resp.write(f"data: {json.dumps(initial)}\n\n".encode("utf-8"))
    session_id = s["session_id"]
    try:
        while True:
            await asyncio.sleep(1.0)
            current = await _run_blocking(cg.get_session_by_id, session_id)
            if not current:
                payload = {"type": "SESSION_GONE", "redirect": "/gallery"}
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
    # Load session to support wallet-backed bet/debit flows.
    s0 = await _run_blocking(cg.get_session_by_id, session_id)
    if not s0:
        return web.json_response({"ok": False, "error": "not found"}, status=404)
    game_id = str(s0.get("game_id") or "").strip().lower()

    # Wallet handling for bet-per-action games (slots / crapslite).
    db = get_database()
    ctx = None
    try:
        ctx = db.get_game_wallet_context(join_code=s0.get("join_code"), game_id=s0.get("session_id"))
    except Exception:
        ctx = None
    wallet_enabled = bool(ctx and ctx.get("wallet_enabled"))
    wallet_currency = _normalize_currency(ctx.get("currency")) if ctx else ""
    needs_wallet = wallet_enabled and wallet_currency and wallet_currency != "gil"

    # For wallet-enabled sessions, these actions must have a logged-in user.
    user = None
    if needs_wallet and game_id in ("slots", "crapslite", "blackjack", "poker", "highlow"):
        u = await _resolve_user(req)
        if isinstance(u, web.Response):
            return u
        user = u
    # If wallet is required and balance is empty, end single-player sessions early.
    if needs_wallet and user and game_id in ("slots", "crapslite", "blackjack", "poker", "highlow"):
        try:
            event_id = int(ctx.get("event_id") or 0)
        except Exception:
            event_id = 0
        if event_id > 0:
            bal = db.get_event_wallet_balance(event_id, int(user.get("id") or 0))
            if bal <= 0:
                await _finish_for_zero_balance(db, ctx, int(user.get("id") or 0), s0)
                return web.json_response(
                    {"ok": False, "error": "no balance", "redirect": "/gallery", "balance": bal},
                    status=409,
                )
    # If we need to debit a bet, do so BEFORE the game reducer runs.
    if needs_wallet and user and game_id == "crapslite" and action == "bet":
        try:
            bet_amount = int(payload.get("amount") or payload.get("bet") or 0)
        except Exception:
            bet_amount = 0
        if bet_amount <= 0:
            return web.json_response({"ok": False, "error": "invalid bet"}, status=400)
        nonce = str(payload.get("nonce") or "").strip()
        if not nonce:
            return web.json_response({"ok": False, "error": "missing nonce"}, status=400)
        reason = f"craps_bet_{nonce}"
        if db.has_wallet_history_entry(
            event_id=int(ctx.get("event_id") or 0),
            user_id=int(user["id"]),
            reason=reason,
            game_id=str(s0.get("session_id")),
        ):
            return web.json_response({"ok": False, "error": "duplicate bet"}, status=409)
        ok, balance, status = db.apply_game_wallet_delta(
            event_id=int(ctx.get("event_id") or 0),
            user_id=int(user["id"]),
            delta=-bet_amount,
            reason=reason,
            metadata={
                "game_id": str(s0.get("session_id")),
                "join_code": s0.get("join_code"),
                "currency": wallet_currency,
                "amount": bet_amount,
                "nonce": nonce,
                "kind": "crapslite_bet",
            },
            allow_negative=False,
        )
        if not ok:
            return web.json_response(
                {"ok": False, "error": "insufficient balance", "required": bet_amount, "balance": balance},
                status=409,
            )
        db.add_user_game(int(user["id"]), str(s0.get("session_id")), role="player")

    if needs_wallet and user and game_id == "slots" and action == "spin":
        # Slots: debit per spin, keyed by a client-provided nonce.
        try:
            bet_amount = int(payload.get("bet") or payload.get("amount") or s0.get("pot") or 0)
        except Exception:
            bet_amount = int(s0.get("pot") or 0)
        if bet_amount <= 0:
            return web.json_response({"ok": False, "error": "invalid bet"}, status=400)
        nonce = str(payload.get("nonce") or "").strip()
        if not nonce:
            return web.json_response({"ok": False, "error": "missing nonce"}, status=400)
        reason = f"slots_spin_bet_{nonce}"
        if db.has_wallet_history_entry(
            event_id=int(ctx.get("event_id") or 0),
            user_id=int(user["id"]),
            reason=reason,
            game_id=str(s0.get("session_id")),
        ):
            return web.json_response({"ok": False, "error": "duplicate spin"}, status=409)
        ok, balance, status = db.apply_game_wallet_delta(
            event_id=int(ctx.get("event_id") or 0),
            user_id=int(user["id"]),
            delta=-bet_amount,
            reason=reason,
            metadata={
                "game_id": str(s0.get("session_id")),
                "join_code": s0.get("join_code"),
                "currency": wallet_currency,
                "amount": bet_amount,
                "nonce": nonce,
                "kind": "slots_spin_bet",
            },
            allow_negative=False,
        )
        if not ok:
            return web.json_response(
                {"ok": False, "error": "insufficient balance", "required": bet_amount, "balance": balance},
                status=409,
            )
        db.add_user_game(int(user["id"]), str(s0.get("session_id")), role="player")

    try:
        s = await _run_blocking(cg.player_action, session_id, token, action, payload)
    except PermissionError:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=403)
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    # Slots: after a successful spin, pay out if needed.
    if needs_wallet and user and game_id == "slots" and action == "spin":
        try:
            st = (s or {}).get("state") or {}
            last_spin = st.get("last_spin") or {}
            payout = int(last_spin.get("payout") or 0)
            nonce = str(last_spin.get("nonce") or payload.get("nonce") or "").strip()
        except Exception:
            payout = 0
            nonce = str(payload.get("nonce") or "").strip()
        if payout > 0 and nonce:
            reason = f"slots_spin_pay_{nonce}"
            if not db.has_wallet_history_entry(
                event_id=int(ctx.get("event_id") or 0),
                user_id=int(user["id"]),
                reason=reason,
                game_id=str(s0.get("session_id")),
            ):
                db.apply_game_wallet_delta(
                    event_id=int(ctx.get("event_id") or 0),
                    user_id=int(user["id"]),
                    delta=payout,
                    reason=reason,
                    metadata={
                        "game_id": str(s0.get("session_id")),
                        "currency": wallet_currency,
                        "amount": payout,
                        "nonce": nonce,
                        "kind": "slots_spin_payout",
                    },
                    allow_negative=True,
                )
    if s and str(s.get("status") or "").lower() == "finished":
        try:
            _sync_game_record(db, dict(s))
        except Exception:
            pass
    balance = None
    if needs_wallet and user:
        try:
            event_id = int(ctx.get("event_id") or 0)
        except Exception:
            event_id = 0
        if event_id > 0:
            balance = db.get_event_wallet_balance(event_id, int(user.get("id") or 0))
    if balance is not None and balance <= 0:
        try:
            if game_id in ("slots", "blackjack", "poker", "highlow"):
                await _finish_for_zero_balance(db, ctx, int(user.get("id") or 0), s or s0)
        except Exception:
            pass
        return web.json_response({"ok": True, "session": s, "redirect": "/gallery", "balance": balance})
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
    if s and str(s.get("status") or "").lower() == "finished":
        try:
            db = get_database()
            _sync_game_record(db, dict(s))
        except Exception:
            pass
    # If this was a crapslite roll, distribute payouts to all joined players.
    try:
        game_id = str((s or {}).get("game_id") or "").strip().lower()
        if game_id == "crapslite" and action == "roll":
            db = get_database()
            ctx = db.get_game_wallet_context(join_code=(s or {}).get("join_code"), game_id=(s or {}).get("session_id"))
            wallet_enabled = bool(ctx and ctx.get("wallet_enabled"))
            wallet_currency = _normalize_currency(ctx.get("currency")) if ctx else ""
            needs_wallet = wallet_enabled and wallet_currency and wallet_currency != "gil"
            if needs_wallet:
                raw = await _run_blocking(cg.get_session_by_id, session_id)
                st = (raw or {}).get("state") or {}
                lr = st.get("last_resolution") or {}
                round_no = int((lr or {}).get("round") or 0)
                per_player = (lr or {}).get("per_player") or {}
                players = st.get("players") or {}
                for ptoken, res in per_player.items():
                    p = players.get(ptoken) if isinstance(players, dict) else None
                    if not isinstance(p, dict):
                        continue
                    uid = p.get("user_id")
                    try:
                        uid_int = int(uid) if uid is not None else 0
                    except Exception:
                        uid_int = 0
                    if uid_int <= 0:
                        continue
                    try:
                        payout = int((res or {}).get("payout") or 0)
                    except Exception:
                        payout = 0
                    # Deduplicate by round per user.
                    reason = f"craps_roll_{round_no}"
                    if payout > 0 and not db.has_wallet_history_entry(
                        event_id=int(ctx.get("event_id") or 0),
                        user_id=uid_int,
                        reason=reason,
                        game_id=str(session_id),
                    ):
                        db.apply_game_wallet_delta(
                            event_id=int(ctx.get("event_id") or 0),
                            user_id=uid_int,
                            delta=payout,
                            reason=reason,
                            metadata={
                                "game_id": str(session_id),
                                "currency": wallet_currency,
                                "amount": payout,
                                "round": round_no,
                                "kind": "crapslite_payout",
                            },
                            allow_negative=True,
                        )
    except Exception:
        pass
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
    try:
        s = await _run_blocking(cg.get_session_by_id, session_id)
        if s:
            db = get_database()
            payload = dict(s or {})
            status_val = payload.get("status") or "finished"
            active = str(status_val).lower() not in ("finished", "ended", "complete", "closed")
            metadata = {
                "currency": payload.get("currency"),
                "pot": payload.get("pot"),
                "status": status_val,
            }
            db.upsert_game(
                game_id=str(payload.get("session_id") or ""),
                module="cardgames",
                payload=payload,
                title=payload.get("game_id"),
                created_at=db._as_datetime(payload.get("created_at")),
                ended_at=db._as_datetime(payload.get("updated_at")),
                status=status_val,
                active=active,
                metadata=metadata,
                run_source="api",
                players=db._extract_cardgame_players(payload),
            )
            ctx = db.get_game_wallet_context(game_id=str(payload.get("session_id") or ""))
            if ctx and ctx.get("wallet_enabled"):
                currency = _normalize_currency(ctx.get("currency"))
                winnings = int(ctx.get("winnings") or 0)
                if currency and currency != "gil" and winnings > 0:
                    user_id = db.get_primary_game_user(str(payload.get("session_id") or ""), role="player")
                    if user_id and not db.has_wallet_history_entry(
                        event_id=int(ctx.get("event_id") or 0),
                        user_id=int(user_id),
                        reason="game_win",
                        game_id=str(payload.get("session_id") or ""),
                    ):
                        db.apply_game_wallet_delta(
                            event_id=int(ctx.get("event_id") or 0),
                            user_id=int(user_id),
                            delta=winnings,
                            reason="game_win",
                            metadata={
                                "game_id": str(payload.get("session_id") or ""),
                                "currency": currency,
                                "amount": winnings,
                            },
                            allow_negative=True,
                        )
    except Exception:
        pass
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
            s.get("background_artist_id"),
            s.get("background_artist_name"),
            s.get("currency"),
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
    s0 = await _run_blocking(cg.get_session_by_id, session_id)
    try:
        await _run_blocking(cg.delete_session, session_id, token)
    except PermissionError:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=403)
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    try:
        if s0:
            db = get_database()
            payload = dict(s0 or {})
            payload["status"] = "deleted"
            payload["updated_at"] = db.now()
            _sync_game_record(db, payload)
    except Exception:
        pass
    return web.json_response({"ok": True})
