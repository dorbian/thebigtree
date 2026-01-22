# bigtree/webmods/events.py
from __future__ import annotations

from aiohttp import web
from datetime import datetime
import asyncio

import bigtree
from bigtree.inc.webserver import route, DynamicWebServer
from bigtree.inc.database import get_database
from bigtree.inc import web_tokens
from bigtree.modules import cardgames as cardgames_mod

from bigtree.webmods.user_area import _resolve_user


# ---------------- public player flow ----------------


@route("GET", "/events/{code}", allow_public=True)
async def event_join_page(req: web.Request) -> web.Response:
    code = (req.match_info.get("code") or "").strip()
    # Prevent injection into the simple .format() template renderer.
    if code:
        code = "".join([c for c in code if (c.isalnum() or c in {"-", "_"})])
    settings = getattr(bigtree, "settings", None)
    base_url = settings.get("WEB.base_url", "http://localhost:8443") if settings else "http://localhost:8443"
    html = DynamicWebServer.render_template(
        "event_join.html",
        {
            "base_url": base_url,
            "event_code": code,
        },
    )
    return web.Response(text=html, content_type="text/html")


@route("GET", "/api/events/{code}", allow_public=True)
async def event_info(req: web.Request) -> web.Response:
    code = (req.match_info.get("code") or "").strip()
    db = get_database()
    ev = db.get_event_by_code(code)
    if not ev:
        return web.json_response({"ok": False, "error": "event not found"}, status=404)

    user = await _resolve_user(req)
    user_id = None
    if isinstance(user, dict):
        user_id = int(user.get("id") or 0)

    joined = False
    wallet_balance = None
    if user_id:
        row = db._fetchone(
            "SELECT 1 AS ok FROM event_players WHERE event_id = %s AND user_id = %s LIMIT 1",
            (int(ev["id"]), user_id),
        )
        joined = bool(row)
        if ev.get("wallet_enabled"):
            w = db._fetchone(
                "SELECT balance FROM event_wallets WHERE event_id = %s AND user_id = %s LIMIT 1",
                (int(ev["id"]), user_id),
            )
            if w:
                try:
                    wallet_balance = int(w.get("balance") or 0)
                except Exception:
                    wallet_balance = 0

    return web.json_response(
        {
            "ok": True,
            "event": ev,
            "joined": joined,
            "wallet_balance": wallet_balance,
            "requires_login": not bool(user_id),
        }
    )


@route("POST", "/api/events/{code}/join", allow_public=True)
async def event_join(req: web.Request) -> web.Response:
    code = (req.match_info.get("code") or "").strip()
    user = await _resolve_user(req)
    if isinstance(user, web.Response):
        return user
    db = get_database()
    ev = db.get_event_by_code(code)
    if not ev:
        return web.json_response({"ok": False, "error": "event not found"}, status=404)
    if ev.get("status") == "ended":
        return web.json_response({"ok": False, "error": "event ended"}, status=409)

    db.join_event(int(ev["id"]), int(user["id"]))
    return web.json_response({"ok": True, "event": ev})


@route("GET", "/api/events/{code}/games", allow_public=True)
async def event_games(req: web.Request) -> web.Response:
    code = (req.match_info.get("code") or "").strip()
    db = get_database()
    ev = db.get_event_by_code(code)
    if not ev:
        return web.json_response({"ok": False, "error": "event not found"}, status=404)
    games = db.list_event_games(int(ev["id"]), include_inactive=False, limit=500)
    enabled = ev.get("metadata") or {}
    enabled_games = enabled.get("enabled_games") or enabled.get("games") or []
    enabled_set = set()
    if isinstance(enabled_games, str):
        enabled_set = {g.strip().lower() for g in enabled_games.split(",") if g.strip()}
    elif isinstance(enabled_games, list):
        enabled_set = {str(g).strip().lower() for g in enabled_games if str(g).strip()}

    out = []
    for g in games:
        module = (g.get("module") or "").lower()
        payload = g.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        game_type = str(payload.get("game_id") or payload.get("gameId") or module or "game").lower()
        if enabled_set:
            always_open = False
            meta = g.get("metadata") or {}
            try:
                always_open = bool(meta.get("always_open"))
            except Exception:
                always_open = False
            if not always_open and module not in enabled_set and game_type not in enabled_set:
                continue
        join_code = g.get("join_code")
        join_url = ""
        if module == "cardgames" and join_code:
            game_id = payload.get("game_id") or payload.get("gameId")
            if game_id:
                join_url = f"/cardgames/{game_id}/session/{join_code}"
        elif module == "tarot" and join_code:
            join_url = f"/tarot/session/{join_code}"
        elif module == "bingo" and join_code:
            join_url = f"/bingo/owner?token={join_code}"
        out.append({
            "game_id": g.get("game_id"),
            "title": g.get("title"),
            "module": module,
            "type": game_type,
            "join_code": join_code,
            "join_url": join_url,
            "currency": g.get("currency"),
            "active": bool(g.get("active")),
        })
    return web.json_response({"ok": True, "event": ev, "games": out})


def _find_event_house_game(db, event_id: int, game_id: str):
    try:
        event_id = int(event_id)
    except Exception:
        return None
    row = db._fetchone(
        """
        SELECT *
        FROM games
        WHERE event_id = %s
          AND module = 'cardgames'
          AND lower(payload->>'game_id') = lower(%s)
          AND (metadata->>'always_open') = 'true'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (event_id, str(game_id)),
    )
    if not row:
        return None
    game = db._format_game_row(dict(row))
    db._attach_game_summary(game)
    return game


def _ensure_event_house_session(db, ev: dict, game_id: str, created_by: int | None):
    if not ev or (ev.get("status") or "active") != "active":
        return None
    event_id = int(ev.get("id") or 0)
    if not event_id:
        return None
    venue_id = ev.get("venue_id")
    venue = db.get_venue(int(venue_id)) if venue_id else None
    currency = ev.get("currency_name") or (venue.get("currency_name") if venue else None)
    try:
        pot = int((venue.get("minimal_spend") if venue else 0) or 0)
    except Exception:
        pot = 0
    meta = ev.get("metadata") or {}
    background_url = meta.get("background_url") or meta.get("background") or (venue.get("background_image") if venue else None)
    deck_id = (venue.get("deck_id") if venue else None)

    existing = _find_event_house_game(db, event_id, game_id)
    session = None
    if existing:
        payload = existing.get("payload") or {}
        session_id = payload.get("session_id")
        join_code = payload.get("join_code")
        if session_id:
            session = cardgames_mod.get_session_by_id(str(session_id))
        if not session and join_code:
            session = cardgames_mod.get_session_by_join_code(str(join_code))
        if session and session.get("status") != "live":
            try:
                cardgames_mod.start_session(session.get("session_id"), session.get("priestess_token") or "")
                session = cardgames_mod.get_session_by_id(session.get("session_id")) or session
            except Exception:
                pass
        if not session:
            existing = None

    if not existing:
        session = cardgames_mod.create_session(
            game_id,
            pot=pot,
            deck_id=deck_id,
            background_url=background_url,
            currency=currency,
            status="created",
        )
        try:
            cardgames_mod.start_session(session.get("session_id"), session.get("priestess_token") or "")
            session = cardgames_mod.get_session_by_id(session.get("session_id")) or session
        except Exception:
            pass

    if not session:
        return None

    payload = dict(session or {})
    metadata = {
        "currency": currency or payload.get("currency"),
        "pot": int(pot or payload.get("pot") or 0),
        "event_code": ev.get("event_code"),
        "always_open": True,
        "single_player": True,
        "join_code": payload.get("join_code"),
    }
    db.upsert_game(
        game_id=str(payload.get("session_id") or payload.get("join_code") or ""),
        module="cardgames",
        payload=payload,
        title=payload.get("game_id"),
        created_by=created_by or ev.get("created_by"),
        venue_id=venue_id or None,
        created_at=db._as_datetime(payload.get("created_at")),
        ended_at=db._as_datetime(payload.get("updated_at")),
        status=payload.get("status") or "live",
        active=True,
        metadata=metadata,
        run_source="event",
    )
    return payload


def _close_event_house_sessions(db, event_id: int):
    if not event_id:
        return
    rows = db._execute(
        """
        SELECT *
        FROM games
        WHERE event_id = %s
          AND module = 'cardgames'
          AND (metadata->>'always_open') = 'true'
        """,
        (int(event_id),),
        fetch=True,
    ) or []
    for row in rows:
        game = db._format_game_row(dict(row))
        payload = game.get("payload") or {}
        session_id = payload.get("session_id")
        join_code = payload.get("join_code")
        session = None
        if session_id:
            session = cardgames_mod.get_session_by_id(str(session_id))
        if not session and join_code:
            session = cardgames_mod.get_session_by_join_code(str(join_code))
        if session and session.get("status") != "finished":
            try:
                cardgames_mod.finish_session(session.get("session_id"), session.get("priestess_token") or "")
                session = cardgames_mod.get_session_by_id(session.get("session_id")) or session
            except Exception:
                pass
        payload = dict(session or payload)
        db.upsert_game(
            game_id=str(payload.get("session_id") or payload.get("join_code") or game.get("game_id") or ""),
            module="cardgames",
            payload=payload,
            title=payload.get("game_id") or game.get("title"),
            created_by=game.get("created_by"),
            venue_id=game.get("venue_id"),
            created_at=db._as_datetime(payload.get("created_at")) or db._as_datetime(game.get("created_at")),
            ended_at=datetime.utcnow(),
            status=payload.get("status") or "ended",
            active=False,
            metadata=game.get("metadata") or {},
            run_source="event",
        )


# ---------------- admin/host management ----------------


@route("GET", "/admin/events", scopes=["admin:web", "event:host"])
async def admin_events_list(req: web.Request) -> web.Response:
    db = get_database()
    q = (req.query.get("q") or "").strip() or None
    try:
        venue_id = int(req.query.get("venue_id") or 0)
    except Exception:
        venue_id = 0
    include_ended = (req.query.get("include_ended") or "1").strip().lower() not in {"0", "false", "no"}
    events = db.list_events(q=q, venue_id=venue_id or None, include_ended=include_ended, limit=500)
    return web.json_response({"ok": True, "events": events})


@route("POST", "/admin/events/upsert", scopes=["admin:web", "event:host"])
async def admin_events_upsert(req: web.Request) -> web.Response:
    try:
        body = await req.json()
    except Exception:
        body = {}

    title = (body.get("title") or "").strip() or None
    try:
        event_id = int(body.get("id") or 0)
    except Exception:
        event_id = 0
    event_code = (body.get("event_code") or "").strip() or None
    try:
        venue_id = int(body.get("venue_id") or 0)
    except Exception:
        venue_id = 0
    currency_name = (body.get("currency_name") or "").strip() or None
    wallet_enabled = bool(body.get("wallet_enabled") or False)
    carry_over = bool(body.get("carry_over") or body.get("carryover") or False)

    background_url = str(body.get("background_url") or body.get("background") or "").strip()
    enabled_games = body.get("enabled_games") or body.get("enabledGames")
    if isinstance(enabled_games, str):
        enabled_games = [x.strip() for x in enabled_games.split(",") if x.strip()]
    if isinstance(enabled_games, list):
        enabled_games = [str(x).strip().lower() for x in enabled_games if str(x).strip()]
    else:
        enabled_games = []

    db = get_database()
    created_by = _resolve_admin_user_id(req)
    # Default currency from venue when not explicitly set on the event
    if (not venue_id) and created_by:
        membership = db.get_discord_venue(int(created_by))
        if membership and membership.get("venue_id"):
            try:
                venue_id = int(membership.get("venue_id") or 0)
            except Exception:
                venue_id = 0
    if not venue_id and not event_id and not event_code:
        return web.json_response({"ok": False, "error": "venue required"}, status=400)
    if (not currency_name) and venue_id:
        v = db.get_venue(int(venue_id))
        if v and v.get("currency_name"):
            currency_name = str(v.get("currency_name"))
    ev = db.upsert_event(
        event_id=event_id or None,
        event_code=event_code,
        title=title,
        venue_id=venue_id or None,
        currency_name=currency_name,
        wallet_enabled=wallet_enabled,
        created_by=created_by,
        metadata={
            "carry_over": carry_over,
            "background_url": background_url or None,
            "enabled_games": enabled_games,
        },
    )
    if not ev:
        return web.json_response({"ok": False, "error": "save failed"}, status=500)
    try:
        await asyncio.to_thread(_ensure_event_house_session, db, ev, "slots", created_by)
        await asyncio.to_thread(_ensure_event_house_session, db, ev, "blackjack", created_by)
    except Exception:
        pass
    return web.json_response({"ok": True, "event": ev})


@route("POST", "/admin/events/end", scopes=["admin:web", "event:host"])
async def admin_events_end(req: web.Request) -> web.Response:
    try:
        body = await req.json()
    except Exception:
        body = {}
    try:
        event_id = int(body.get("event_id") or body.get("id") or 0)
    except Exception:
        event_id = 0
    if not event_id:
        return web.json_response({"ok": False, "error": "event_id required"}, status=400)
    db = get_database()
    if not db.end_event(event_id):
        return web.json_response({"ok": False, "error": "event not found or already ended"}, status=404)
    try:
        await asyncio.to_thread(_close_event_house_sessions, db, int(event_id))
    except Exception:
        pass
    return web.json_response({"ok": True})


@route("GET", "/admin/events/{event_id}/players", scopes=["admin:web", "event:host"])
async def admin_event_players(req: web.Request) -> web.Response:
    try:
        event_id = int(req.match_info.get("event_id") or 0)
    except Exception:
        event_id = 0
    if not event_id:
        return web.json_response({"ok": False, "error": "event_id required"}, status=400)
    db = get_database()
    ev = db._fetchone("SELECT id FROM events WHERE id = %s", (int(event_id),))
    if not ev:
        return web.json_response({"ok": False, "error": "event not found"}, status=404)
    players = db.get_event_players(int(event_id), limit=5000)
    # Only expose minimal fields.
    minimal = [{"xiv_username": p.get("xiv_username"), "joined_at": p.get("joined_at")} for p in players]
    return web.json_response({"ok": True, "event_id": event_id, "players": minimal})

@route("GET", "/admin/events/{event_id}/summary", scopes=["admin:web", "event:host"])
async def admin_event_summary(req: web.Request) -> web.Response:
    try:
        event_id = int(req.match_info.get("event_id") or 0)
    except Exception:
        event_id = 0
    if not event_id:
        return web.json_response({"ok": False, "error": "event_id required"}, status=400)
    db = get_database()
    ev = db._fetchone("SELECT id, currency_name FROM events WHERE id = %s", (int(event_id),))
    if not ev:
        return web.json_response({"ok": False, "error": "event not found"}, status=404)
    totals = db.get_event_house_total(int(event_id))
    return web.json_response(
        {
            "ok": True,
            "event_id": event_id,
            "currency_name": ev.get("currency_name"),
            "totals": totals,
        }
    )


@route("POST", "/admin/events/{event_id}/wallets/set", scopes=["admin:web", "event:host"])
async def admin_event_wallet_set(req: web.Request) -> web.Response:
    try:
        event_id = int(req.match_info.get("event_id") or 0)
    except Exception:
        event_id = 0
    if not event_id:
        return web.json_response({"ok": False, "error": "event_id required"}, status=400)
    try:
        body = await req.json()
    except Exception:
        body = {}
    user_id = body.get("user_id")
    xiv_username = (body.get("xiv_username") or "").strip()
    host_name = (body.get("host_name") or body.get("host") or "").strip()
    comment = (body.get("comment") or "").strip()
    try:
        delta = int(body.get("delta") or body.get("amount") or 0)
    except Exception:
        return web.json_response({"ok": False, "error": "amount must be a number"}, status=400)
    if not comment:
        return web.json_response({"ok": False, "error": "comment is required"}, status=400)

    db = get_database()
    ev = db._fetchone("SELECT wallet_enabled FROM events WHERE id = %s", (int(event_id),))
    if not ev:
        return web.json_response({"ok": False, "error": "event not found"}, status=404)
    if not bool(ev.get("wallet_enabled")):
        return web.json_response({"ok": False, "error": "wallet not enabled for event"}, status=409)

    if user_id:
        try:
            user_id = int(user_id)
        except Exception:
            user_id = 0
    if not user_id and xiv_username:
        user_id = db.find_user_id_by_xiv_username(xiv_username)
    if not user_id:
        return web.json_response({"ok": False, "error": "user not found"}, status=404)

    ok, balance, status = db.add_event_wallet_balance(
        int(event_id),
        int(user_id),
        int(delta),
        host_name=host_name,
        comment=comment,
    )
    if not ok:
        return web.json_response({"ok": False, "error": status or "update failed"}, status=400)
    return web.json_response(
        {"ok": True, "event_id": event_id, "user_id": int(user_id), "balance": int(balance)}
    )
# ---- Admin auth helpers (web token) ----
def _extract_token(req: web.Request) -> str:
    auth = req.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth.split(" ", 1)[1].strip()
    return req.headers.get("X-Bigtree-Key") or req.headers.get("X-API-Key") or ""


def _resolve_admin_user_id(req: web.Request) -> Optional[int]:
    token = _extract_token(req)
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
