from __future__ import annotations

import asyncio
import json
import base64
import hashlib
import hmac
import secrets
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import aiohttp
from aiohttp import web

import bigtree
from bigtree.inc.database import get_database
from bigtree.inc.logging import logger
from bigtree.inc.webserver import DynamicWebServer, route

USER_TOKEN_HEADER = "X-Bigtree-User-Token"
OAUTH_STATES: Dict[str, float] = {}
OAUTH_STATE_TTL = 300


def _load_xivauth_config() -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    settings = getattr(bigtree, "settings", None)
    if settings:
        try:
            section = settings.section("XIVAUTH")
            if isinstance(section, dict):
                for key, value in section.items():
                    if isinstance(key, str):
                        merged[key.lower()] = value
        except Exception:
            pass
    try:
        db = get_database()
        db_config = db.get_system_config("xivauth") or {}
        for key, value in db_config.items():
            if isinstance(key, str) and value is not None:
                merged[key.lower()] = value
    except Exception:
        pass
    return merged


def _get_xivauth_value(config: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = config.get(key)
        if value not in (None, ""):
            return value
    return default


def _get_state_secret() -> str:
    config = _load_xivauth_config()
    secret = str(_get_xivauth_value(config, "state_secret") or "").strip()
    if secret:
        return secret
    settings = getattr(bigtree, "settings", None)
    if settings:
        return str(settings.get("WEB.jwt_secret", "") or "").strip()
    return ""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _build_state_token(secret: str) -> str:
    ts = int(time.time())
    nonce = secrets.token_urlsafe(8)
    payload = f"{ts}:{nonce}".encode("ascii")
    sig = hmac.new(secret.encode("ascii"), payload, hashlib.sha256).digest()
    return f"{_b64url(payload)}.{_b64url(sig)}"


def _verify_state_token(token: str, secret: str) -> bool:
    if not token or "." not in token:
        return False
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload = base64.urlsafe_b64decode(payload_b64 + "==")
        sig = base64.urlsafe_b64decode(sig_b64 + "==")
    except Exception:
        return False
    expected = hmac.new(secret.encode("ascii"), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        ts_raw = payload.decode("ascii").split(":", 1)[0]
        ts = int(ts_raw)
    except Exception:
        return False
    return time.time() - ts <= OAUTH_STATE_TTL


def _prune_oauth_states() -> None:
    now = time.time()
    stale = [key for key, ts in OAUTH_STATES.items() if now - ts > OAUTH_STATE_TTL]
    for key in stale:
        OAUTH_STATES.pop(key, None)


def _create_user_session(auth_data: Dict[str, Any], username: Optional[str], world: Optional[str]) -> Dict[str, Any]:
    xiv_username = auth_data.get("xiv_username") or username or "xivplayer"
    xiv_id = auth_data.get("xiv_id") or auth_data.get("character_id")
    metadata = auth_data.get("metadata") or {}
    if not world:
        world = auth_data.get("home_world") or auth_data.get("world")
    if world:
        metadata["world"] = world
    db = get_database()
    user = db.upsert_user(xiv_username, xiv_id, metadata)
    if not user:
        raise ValueError("user record could not be created")
    db.link_user_to_matches(user["id"], user["xiv_username"])
    session_token = db.create_user_session(user["id"])
    return {
        "token": session_token,
        "user": {
            "id": user["id"],
            "xiv_username": user["xiv_username"],
            "xiv_id": user.get("xiv_id"),
            "metadata": user.get("metadata"),
        },
    }


def _seed_game_from_join_code(join_code: str) -> bool:
    code = (join_code or "").strip()
    if not code:
        return False
    db = get_database()
    try:
        from bigtree.modules import cardgames as cardgames_mod
    except Exception:
        cardgames_mod = None
    if cardgames_mod:
        try:
            session = cardgames_mod.get_session_by_join_code(code)
        except Exception:
            session = None
        if session:
            payload = dict(session)
            state_json = payload.get("state_json")
            if isinstance(state_json, str):
                try:
                    payload["state_json_parsed"] = json.loads(state_json)
                except Exception:
                    pass
            status = payload.get("status") or payload.get("stage") or "unknown"
            active = str(status).lower() not in ("finished", "ended", "complete", "closed")
            game_id = payload.get("session_id") or payload.get("game_id") or payload.get("join_code")
            metadata = {
                "currency": payload.get("currency"),
                "pot": payload.get("pot"),
                "status": status,
            }
            players = db._extract_cardgame_players(payload)
            return db.upsert_game(
                game_id=str(game_id),
                module="cardgames",
                payload=payload,
                title=payload.get("game_id"),
                created_at=db._as_datetime(payload.get("created_at")),
                ended_at=db._as_datetime(payload.get("updated_at")),
                status=status,
                active=active,
                metadata=metadata,
                run_source="api",
                players=players,
            )
    try:
        from bigtree.modules import tarot as tarot_mod
    except Exception:
        tarot_mod = None
    if tarot_mod:
        try:
            session = tarot_mod.get_session_by_join_code(code)
        except Exception:
            session = None
        if session:
            status = session.get("status") or ("active" if session.get("active") else "ended")
            active = bool(session.get("active")) or str(status).lower() == "active"
            metadata = {
                "deck_id": session.get("deck_id"),
                "spread_id": session.get("spread_id"),
                "status": status,
            }
            players = db._extract_tarot_players(session)
            return db.upsert_game(
                game_id=str(session.get("session_id") or session.get("id") or session.get("join_code")),
                module="tarot",
                payload=session,
                title=session.get("title") or session.get("name") or "Tarot",
                created_at=db._as_datetime(session.get("created_at") or session.get("started_at")),
                ended_at=db._as_datetime(session.get("ended_at")),
                status=status,
                active=active,
                metadata=metadata,
                run_source="api",
                players=players,
            )
    try:
        from bigtree.modules import bingo as bingo_mod
    except Exception:
        bingo_mod = None
    if bingo_mod:
        try:
            game = bingo_mod.get_game(code)
        except Exception:
            game = None
        if game:
            active = bool(game.get("active"))
            status = "active" if active else "ended"
            metadata = {
                "currency": game.get("currency"),
                "stage": game.get("stage"),
                "price": game.get("price"),
                "pot": game.get("pot"),
            }
            players = []
            try:
                for owner in bingo_mod.list_owners(game.get("game_id") or code):
                    name = owner.get("owner_name") if isinstance(owner, dict) else None
                    if name:
                        players.append(name)
            except Exception:
                players = []
            return db.upsert_game(
                game_id=str(game.get("game_id") or code),
                module="bingo",
                payload=game,
                title=game.get("title") or game.get("header") or "Bingo",
                created_at=db._as_datetime(game.get("created_at")),
                ended_at=db._as_datetime(game.get("ended_at")),
                status=status,
                active=active,
                metadata=metadata,
                run_source="api",
                players=players,
            )
    return False


async def _call_xivauth(token: str, username: Optional[str], world: Optional[str]) -> Dict[str, Any]:
    section = _load_xivauth_config()
    verify_url = str(section.get("verify_url") or "").strip()
    if not verify_url:
        return {"xiv_username": username or section.get("default_username") or "xivplayer"}
    token_header = str(section.get("token_header") or "").strip()
    token_prefix = str(section.get("token_prefix") or "Bearer").strip()
    params: Dict[str, Any] = {}
    if not token_header:
        params["token"] = token
    if username:
        params["username"] = username
    if world:
        params["world"] = world
    headers: Dict[str, str] = {}
    if token_header:
        if token_header.lower() == "authorization":
            headers["Authorization"] = f"{token_prefix} {token}"
        else:
            headers[token_header] = token
    api_key = section.get("api_key")
    if api_key:
        api_key_header = str(section.get("api_key_header") or "").strip()
        if api_key_header:
            if api_key_header.lower() == "authorization":
                headers["Authorization"] = f"{token_prefix} {api_key}"
            else:
                headers[api_key_header] = str(api_key)
        elif "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {api_key}"
    timeout = section.get("timeout_seconds") or section.get("timeout") or 6
    try:
        timeout = float(timeout)
    except Exception:
        timeout = 6
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(verify_url, params=params, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise ValueError(f"xivauth failure: {resp.status} {text}")
                data = await resp.json()
                if isinstance(data, list):
                    data = data[0] if data else {}
                if isinstance(data, dict) and "name" in data and "xiv_username" not in data:
                    metadata = {
                        "home_world": data.get("home_world"),
                        "data_center": data.get("data_center"),
                        "avatar_url": data.get("avatar_url"),
                        "portrait_url": data.get("portrait_url"),
                    }
                    return {
                        "xiv_username": data.get("name"),
                        "xiv_id": data.get("persistent_key") or data.get("lodestone_id"),
                        "metadata": {k: v for k, v in metadata.items() if v},
                    }
                return data if isinstance(data, dict) else {}
    except asyncio.TimeoutError:
        raise ValueError("xivauth timeout")
    except aiohttp.ClientError as exc:
        raise ValueError(f"xivauth unreachable ({exc})")


def _extract_user_token(request: web.Request) -> Optional[str]:
    token = request.headers.get(USER_TOKEN_HEADER)
    if token:
        return token.strip()
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None


async def _resolve_user(request: web.Request) -> Any:
    token = _extract_user_token(request)
    if not token:
        return web.json_response({"ok": False, "error": "user token required"}, status=401)
    db = get_database()
    user = db.get_user_by_session(token)
    if not user:
        return web.json_response({"ok": False, "error": "invalid or expired token"}, status=401)
    return user


@route("POST", "/user-area/login", allow_public=True)
async def login_user(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)
    token = payload.get("xiv_auth_token") or payload.get("token")
    username = payload.get("xiv_username") or payload.get("xiv_name")
    world = payload.get("xiv_world")
    if not token:
        return web.json_response({"ok": False, "error": "xiv_auth_token is required"}, status=400)
    try:
        auth_data = await _call_xivauth(token, username, world)
    except ValueError as exc:
        logger.warning("[user-area] xivauth denied login: %s", exc)
        return web.json_response({"ok": False, "error": str(exc)}, status=401)
    try:
        session = _create_user_session(auth_data, username, world)
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)
    response = {
        "ok": True,
        "token": session["token"],
        "user": session["user"],
    }
    return web.json_response(response)


@route("GET", "/user-area/oauth/start", allow_public=True)
async def xivauth_oauth_start(_request: web.Request) -> web.Response:
    config = _load_xivauth_config()
    client_id = str(_get_xivauth_value(config, "client_id", "oauth_client_id") or "").strip()
    if not client_id:
        return web.Response(text="XivAuth client_id is not configured.", status=500)
    authorize_url = str(
        _get_xivauth_value(config, "authorize_url", "oauth_authorize_url", default="https://xivauth.net/oauth/authorize")
    ).strip()
    scope = str(_get_xivauth_value(config, "scope", "scopes", default="user character")).strip()
    redirect_url = str(_get_xivauth_value(config, "redirect_url", "oauth_redirect_url") or "").strip()
    settings = getattr(bigtree, "settings", None)
    if not redirect_url:
        base_url = settings.get("WEB.base_url", "http://localhost:8443") if settings else "http://localhost:8443"
        redirect_url = f"{base_url.rstrip('/')}/user-area/oauth/callback"
    secret = _get_state_secret()
    if secret:
        state = _build_state_token(secret)
    else:
        state = secrets.token_urlsafe(24)
        _prune_oauth_states()
        OAUTH_STATES[state] = time.time()
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_url,
        "scope": scope,
        "state": state,
    }
    url = f"{authorize_url}{'&' if '?' in authorize_url else '?'}{urlencode(params)}"
    raise web.HTTPFound(url)


@route("GET", "/user-area/oauth/callback", allow_public=True)
async def xivauth_oauth_callback(request: web.Request) -> web.Response:
    code = request.query.get("code")
    state = request.query.get("state")
    if not code or not state:
        return web.Response(text="Invalid OAuth state.", status=400)
    issued = OAUTH_STATES.pop(state, 0)
    if issued and time.time() - issued <= OAUTH_STATE_TTL:
        pass
    else:
        secret = _get_state_secret()
        if not secret or not _verify_state_token(state, secret):
            return web.Response(text="Invalid OAuth state.", status=400)
    config = _load_xivauth_config()
    client_id = str(_get_xivauth_value(config, "client_id", "oauth_client_id") or "").strip()
    client_secret = str(_get_xivauth_value(config, "client_secret", "oauth_client_secret") or "").strip()
    if not client_id or not client_secret:
        return web.Response(text="XivAuth OAuth client credentials are not configured.", status=500)
    token_url = str(
        _get_xivauth_value(config, "token_url", "oauth_token_url", default="https://xivauth.net/oauth/token")
    ).strip()
    redirect_url = str(_get_xivauth_value(config, "redirect_url", "oauth_redirect_url") or "").strip()
    settings = getattr(bigtree, "settings", None)
    if not redirect_url:
        base_url = settings.get("WEB.base_url", "http://localhost:8443") if settings else "http://localhost:8443"
        redirect_url = f"{base_url.rstrip('/')}/user-area/oauth/callback"
    payload = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_url,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, data=payload) as resp:
                data = await resp.json()
                if resp.status != 200:
                    raise ValueError(f"xivauth token error: {resp.status} {data}")
    except Exception as exc:
        logger.warning("[user-area] xivauth token exchange failed: %s", exc)
        return web.Response(text="XivAuth token exchange failed.", status=502)
    access_token = data.get("access_token") or data.get("token")
    if not access_token:
        return web.Response(text="XivAuth token missing.", status=502)
    try:
        auth_data = await _call_xivauth(access_token, None, None)
        session_data = _create_user_session(auth_data, None, None)
    except ValueError as exc:
        logger.warning("[user-area] xivauth login failed: %s", exc)
        return web.Response(text="XivAuth login failed.", status=401)
    return web.HTTPFound(f"/user-area?user_token={session_data['token']}")


@route("GET", "/user-area/me", allow_public=True)
async def current_user(request: web.Request) -> web.Response:
    user = await _resolve_user(request)
    if isinstance(user, web.Response):
        return user
    payload = {}
    if isinstance(user, dict):
        payload = dict(user)
        for key, value in payload.items():
            if hasattr(value, "isoformat"):
                payload[key] = value.isoformat()
    return web.json_response({"ok": True, "user": payload})


@route("GET", "/user-area/games", allow_public=True)
async def user_games(request: web.Request) -> web.Response:
    user = await _resolve_user(request)
    if isinstance(user, web.Response):
        return user
    db = get_database()
    include_all = str(request.query.get("all") or "").strip().lower() in {"1", "true", "yes"}
    games = db.list_user_games(user["id"], only_active=not include_all)
    try:
        from bigtree.modules import bingo as bingo_mod
    except Exception:
        bingo_mod = None
    if bingo_mod:
        for game in games:
            if game.get("module") != "bingo":
                continue

            game_id = str(game.get("game_id") or "").strip()
            if not game_id:
                continue

            # Determine expected owner name (best effort)
            owner_name = (user.get("xiv_username") or game.get("claimed_username") or "").strip()
            if not owner_name:
                players = game.get("players") or []
                for player in players:
                    role = str(player.get("role") or "").lower()
                    if role in {"owner", "host", "dealer", "caller"}:
                        owner_name = (player.get("name") or "").strip()
                        break

            join_code = (game.get("join_code") or "").strip()
            valid = False
            if join_code:
                try:
                    info = bingo_mod.resolve_owner_token(join_code)
                    valid = bool(info and str(info.get("game_id") or "") == game_id)
                except Exception:
                    valid = False

            if not join_code or not valid:
                try:
                    token = bingo_mod.get_owner_token_for_user(game_id, int(user.get("id")), fallback_owner_name=owner_name)
                except Exception:
                    token = ""
                if token:
                    join_code = token
                    game["join_code"] = join_code
                    try:
                        db.set_game_join_code(game_id, join_code)
                    except Exception:
                        pass

    return web.json_response({"ok": True, "games": games})


@route("GET", "/user-area/events", allow_public=True)
async def user_events(request: web.Request) -> web.Response:
    user = await _resolve_user(request)
    if isinstance(user, web.Response):
        return user
    db = get_database()
    include_ended = (request.query.get("all") or request.query.get("include_ended") or "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    events = db.list_user_events(int(user["id"]), include_ended=include_ended, limit=500)
    return web.json_response({"ok": True, "events": events})


@route("GET", "/user-area/events/{code}", allow_public=True)
async def user_event_detail(request: web.Request) -> web.Response:
    code = (request.match_info.get("code") or "").strip()
    if code:
        code = "".join([c for c in code if (c.isalnum() or c in {"-", "_"})])
    user = await _resolve_user(request)
    if isinstance(user, web.Response):
        return user
    db = get_database()
    detail = db.get_user_event_detail(int(user["id"]), code)
    if not detail:
        return web.json_response({"ok": False, "error": "event not found or not joined"}, status=404)
    return web.json_response({"ok": True, **detail})


@route("POST", "/user-area/claim", allow_public=True)
async def claim_game(request: web.Request) -> web.Response:
    user = await _resolve_user(request)
    if isinstance(user, web.Response):
        return user
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)
    game_id = (payload.get("game_id") or "").strip()
    if not game_id:
        return web.json_response({"ok": False, "error": "game_id is required"}, status=400)
    db = get_database()
    if not db.claim_game_for_user(game_id, user["id"]):
        return web.json_response({"ok": False, "error": "game not found or not claimable"}, status=404)
    return web.json_response({"ok": True, "game_id": game_id})


@route("POST", "/user-area/claim-join", allow_public=True)
async def claim_game_by_join(request: web.Request) -> web.Response:
    user = await _resolve_user(request)
    if isinstance(user, web.Response):
        return user
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)
    join_code = (payload.get("join_code") or payload.get("code") or "").strip()
    if not join_code:
        return web.json_response({"ok": False, "error": "join_code is required"}, status=400)
    db = get_database()
    ok, game, status = db.claim_game_by_join_code(join_code, user["id"])
    seed_code = join_code
    if not ok and status == "join code not found":
        try:
            from bigtree.modules import bingo as bingo_mod
            info = bingo_mod.resolve_owner_token(join_code)
        except Exception:
            info = None
        if info and info.get("game_id"):
            seed_code = str(info.get("game_id"))
            ok, game, status = db.claim_game_by_join_code(seed_code, user["id"])
        if not ok and status == "join code not found":
            if _seed_game_from_join_code(seed_code):
                ok, game, status = db.claim_game_by_join_code(seed_code, user["id"])
    if not ok:
        if status == "already claimed":
            return web.json_response({"ok": False, "error": "already claimed", "game": game}, status=409)
        if status == "join code not found":
            return web.json_response({"ok": False, "error": "join code not found"}, status=404)
        return web.json_response({"ok": False, "error": status or "claim failed"}, status=400)
    try:
        if game and game.get("module") == "bingo":
            db.set_game_join_code(game.get("game_id") or "", join_code)
    except Exception:
        pass
    return web.json_response({"ok": True, "status": status, "game": game})


@route("GET", "/user-area/join-status", allow_public=True)
async def user_join_status(request: web.Request) -> web.Response:
    join_code = (request.query.get("join_code") or request.query.get("code") or "").strip()
    if not join_code:
        return web.json_response({"ok": False, "error": "join_code is required"}, status=400)
    db = get_database()
    game = db.get_game_by_join_code(join_code)
    return web.json_response({"ok": True, "game": game})


@route("GET", "/user-area", allow_public=True)
async def user_area_page(_req: web.Request) -> web.Response:
    settings = getattr(bigtree, "settings", None)
    base_url = settings.get("WEB.base_url", "http://localhost:8443") if settings else "http://localhost:8443"
    html = DynamicWebServer.render_template("user_area.html", {"base_url": base_url})
    return web.Response(text=html, content_type="text/html")


@route("GET", "/user-area/manage", allow_public=True)
async def user_area_manage_page(_req: web.Request) -> web.Response:
    settings = getattr(bigtree, "settings", None)
    base_url = settings.get("WEB.base_url", "http://localhost:8443") if settings else "http://localhost:8443"
    html = DynamicWebServer.render_template("user_area_manage.html", {"base_url": base_url})
    return web.Response(text=html, content_type="text/html")


@route("GET", "/user-area/manage/games", scopes=["admin:web"])
async def manage_games(request: web.Request) -> web.Response:
    db = get_database()
    games = db.list_api_games(include_inactive=True, limit=500)
    return web.json_response({"ok": True, "games": games})


@route("GET", "/user-area/manage/claims", scopes=["admin:web"])
async def manage_claims(request: web.Request) -> web.Response:
    """List all registered XivAuth users/characters (admin view)."""
    db = get_database()
    try:
        limit = int(request.query.get("limit") or 2000)
    except Exception:
        limit = 2000
    users = db.list_users(limit=limit)
    return web.json_response({"ok": True, "users": users})
