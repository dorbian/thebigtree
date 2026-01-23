# bigtree/webmods/venues.py
from __future__ import annotations

from aiohttp import web

import bigtree
from bigtree.inc.webserver import route, DynamicWebServer
from bigtree.inc.database import get_database

# Reuse the user resolver from user_area (Bearer user token)
from bigtree.webmods.user_area import _resolve_user


@route("GET", "/venues", allow_public=True)
async def venues_page(_req: web.Request) -> web.Response:
    settings = getattr(bigtree, "settings", None)
    base_url = settings.get("WEB.base_url", "http://localhost:8443") if settings else "http://localhost:8443"
    html = DynamicWebServer.render_template("venues.html", {"base_url": base_url})
    return web.Response(text=html, content_type="text/html")


@route("GET", "/venues/list", allow_public=True)
async def venues_list(_req: web.Request) -> web.Response:
    db = get_database()
    venues = db.list_venues()
    return web.json_response({"ok": True, "venues": venues})


@route("GET", "/venues/me", allow_public=True)
async def venues_me(req: web.Request) -> web.Response:
    user = await _resolve_user(req)
    if isinstance(user, web.Response):
        return user
    db = get_database()
    membership = db.get_user_venue(int(user["id"]))
    return web.json_response({"ok": True, "membership": membership})


@route("POST", "/venues/assign", allow_public=True)
async def venues_assign(req: web.Request) -> web.Response:
    user = await _resolve_user(req)
    if isinstance(user, web.Response):
        return user
    try:
        body = await req.json()
    except Exception:
        body = {}
    try:
        venue_id = int(body.get("venue_id") or 0)
    except Exception:
        venue_id = 0
    if not venue_id:
        return web.json_response({"ok": False, "error": "venue_id required"}, status=400)
    db = get_database()
    venue = db.get_venue(venue_id)
    if not venue:
        return web.json_response({"ok": False, "error": "venue not found"}, status=404)
    db.set_user_venue(int(user["id"]), venue_id, role="member")
    membership = db.get_user_venue(int(user["id"]))
    return web.json_response({"ok": True, "membership": membership})


@route("POST", "/venues/update", allow_public=True)
async def venues_update(req: web.Request) -> web.Response:
    user = await _resolve_user(req)
    if isinstance(user, web.Response):
        return user
    db = get_database()
    membership = db.get_user_venue(int(user["id"]))
    if not membership:
        return web.json_response({"ok": False, "error": "no venue assigned"}, status=400)
    if (membership.get("role") or "").lower() != "admin":
        return web.json_response({"ok": False, "error": "venue admin required"}, status=403)
    try:
        body = await req.json()
    except Exception:
        body = {}

    currency_name = body.get("currency_name")
    background_image = body.get("background_image")
    deck_id = body.get("deck_id")
    minimal_spend = body.get("minimal_spend")

    if currency_name is not None:
        currency_name = str(currency_name).strip() or None
    if background_image is not None:
        background_image = str(background_image).strip() or None
    if minimal_spend is not None:
        try:
            minimal_spend = int(minimal_spend)
        except Exception:
            minimal_spend = None

    if deck_id is not None:
        deck_id = str(deck_id).strip() or None

    ok = db.update_venue(
        int(membership.get("venue_id")),
        currency_name=currency_name,
        minimal_spend=minimal_spend,
        background_image=background_image,
        deck_id=deck_id,
    )
    if not ok:
        return web.json_response({"ok": False, "error": "update failed"}, status=500)
    membership = db.get_user_venue(int(user["id"]))
    return web.json_response({"ok": True, "membership": membership})


@route("GET", "/venues/games", allow_public=True)
async def venues_games(req: web.Request) -> web.Response:
    user = await _resolve_user(req)
    if isinstance(user, web.Response):
        return user
    db = get_database()
    membership = db.get_user_venue(int(user["id"]))
    if not membership:
        return web.json_response({"ok": False, "error": "no venue assigned"}, status=400)
    if (membership.get("role") or "").lower() != "admin":
        return web.json_response({"ok": False, "error": "venue admin required"}, status=403)
    try:
        limit = int(req.query.get("limit") or 200)
    except Exception:
        limit = 200
    if limit < 1:
        limit = 1
    if limit > 500:
        limit = 500
    games = db.list_venue_games(int(membership.get("venue_id")), limit=limit)
    return web.json_response({"ok": True, "venue_id": int(membership.get("venue_id")), "games": games})


# --- Admin helpers (wired into forest management for now) ---

@route("GET", "/admin/venues", scopes=["admin:web"])
async def admin_venues_list(_req: web.Request) -> web.Response:
    db = get_database()
    return web.json_response({"ok": True, "venues": db.list_venues()})


@route("POST", "/admin/venues/delete", scopes=["admin:web"])
async def venues_delete(req: web.Request):
    db = get_database()
    try:
        body = await req.json()
    except Exception:
        body = {}
    venue_id = body.get("venue_id")
    try:
        venue_id = int(venue_id)
    except Exception:
        venue_id = 0
    if not venue_id:
        return web.json_response({"ok": False, "error": "venue_id required"}, status=400)
    ok = db.delete_venue(venue_id)
    if not ok:
        return web.json_response({"ok": False, "error": "not deleted"}, status=400)
    return web.json_response({"ok": True})


@route("POST", "/admin/venues/upsert", scopes=["admin:web"])
async def admin_venues_upsert(req: web.Request) -> web.Response:
    try:
        body = await req.json()
    except Exception:
        body = {}
    name = str(body.get("name") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "name required"}, status=400)
    currency_name = body.get("currency_name")
    background_image = body.get("background_image")
    deck_id = body.get("deck_id")
    minimal_spend = body.get("minimal_spend")
    admin_discord_ids = body.get("admin_discord_ids")
    game_backgrounds = body.get("game_backgrounds")
    if currency_name is not None:
        currency_name = str(currency_name).strip() or None
    if background_image is not None:
        background_image = str(background_image).strip() or None
    if deck_id is not None:
        deck_id = str(deck_id).strip() or None
    if minimal_spend is not None:
        try:
            minimal_spend = int(minimal_spend)
        except Exception:
            minimal_spend = None
    db = get_database()
    metadata = {}
    if admin_discord_ids is not None:
        # Accept a CSV string or list of ids.
        if isinstance(admin_discord_ids, str):
            ids = [x.strip() for x in admin_discord_ids.split(",") if x.strip()]
        elif isinstance(admin_discord_ids, list):
            ids = [str(x).strip() for x in admin_discord_ids if str(x).strip()]
        else:
            ids = []
        metadata["admin_discord_ids"] = ids
    if isinstance(game_backgrounds, dict):
        cleaned = {}
        for key, value in game_backgrounds.items():
            if not key:
                continue
            cleaned[str(key).strip().lower()] = str(value or "").strip()
        metadata["game_backgrounds"] = cleaned

    venue = db.upsert_venue(
        name,
        currency_name=currency_name,
        minimal_spend=minimal_spend,
        background_image=background_image,
        deck_id=deck_id,
        metadata=metadata,
    )
    if not venue:
        return web.json_response({"ok": False, "error": "save failed"}, status=500)
    return web.json_response({"ok": True, "venue": venue})


@route("POST", "/admin/venues/assign-admin", scopes=["admin:web"])
async def admin_venues_assign_admin(req: web.Request) -> web.Response:
    try:
        body = await req.json()
    except Exception:
        body = {}
    try:
        venue_id = int(body.get("venue_id") or 0)
    except Exception:
        venue_id = 0
    username = str(body.get("xiv_username") or "").strip()
    if not venue_id or not username:
        return web.json_response({"ok": False, "error": "venue_id and xiv_username required"}, status=400)
    db = get_database()
    venue = db.get_venue(venue_id)
    if not venue:
        return web.json_response({"ok": False, "error": "venue not found"}, status=404)
    user_id = db.find_user_id_by_xiv_username(username)
    if not user_id:
        return web.json_response({"ok": False, "error": "user not found"}, status=404)
    db.set_user_venue_role(int(user_id), venue_id, role="admin")
    return web.json_response({"ok": True})
