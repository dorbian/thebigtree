# bigtree/webmods/events.py
from __future__ import annotations

from aiohttp import web

import bigtree
from bigtree.inc.webserver import route, DynamicWebServer
from bigtree.inc.database import get_database

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
            if module not in enabled_set and game_type not in enabled_set:
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
    # Default currency from venue when not explicitly set on the event
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
        metadata={
            "carry_over": carry_over,
            "background_url": background_url or None,
            "enabled_games": enabled_games,
        },
    )
    if not ev:
        return web.json_response({"ok": False, "error": "save failed"}, status=500)
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
