from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import aiohttp
from aiohttp import web

import bigtree
from bigtree.inc.database import get_database
from bigtree.inc.logging import logger
from bigtree.inc.webserver import route

USER_TOKEN_HEADER = "X-Bigtree-User-Token"


async def _call_xivauth(token: str, username: Optional[str], world: Optional[str]) -> Dict[str, Any]:
    settings = getattr(bigtree, "settings", None)
    section = settings.section("XIVAUTH") if settings else {}
    verify_url = (section.get("verify_url") or "").strip()
    if not verify_url:
        return {"xiv_username": username or section.get("default_username") or "xivplayer"}
    params: Dict[str, Any] = {"token": token}
    if username:
        params["username"] = username
    if world:
        params["world"] = world
    headers: Dict[str, str] = {}
    api_key = section.get("api_key")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    timeout = section.get("timeout_seconds", 6)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(verify_url, params=params, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise ValueError(f"xivauth failure: {resp.status} {text}")
                return await resp.json()
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
    xiv_username = auth_data.get("xiv_username") or username or "xivplayer"
    xiv_id = auth_data.get("xiv_id") or auth_data.get("character_id")
    metadata = auth_data.get("metadata") or {}
    if world:
        metadata["world"] = world
    db = get_database()
    user = db.upsert_user(xiv_username, xiv_id, metadata)
    if not user:
        return web.json_response({"ok": False, "error": "user record could not be created"}, status=500)
    db.link_user_to_matches(user["id"], user["xiv_username"])
    session_token = db.create_user_session(user["id"])
    response = {
        "ok": True,
        "token": session_token,
        "user": {
            "id": user["id"],
            "xiv_username": user["xiv_username"],
            "xiv_id": user.get("xiv_id"),
            "metadata": user.get("metadata"),
        },
    }
    return web.json_response(response)


@route("GET", "/user-area/me", allow_public=True)
async def current_user(request: web.Request) -> web.Response:
    user = await _resolve_user(request)
    if isinstance(user, web.Response):
        return user
    return web.json_response({"ok": True, "user": user})


@route("GET", "/user-area/games", allow_public=True)
async def user_games(request: web.Request) -> web.Response:
    user = await _resolve_user(request)
    if isinstance(user, web.Response):
        return user
    db = get_database()
    games = db.list_user_games(user["id"])
    return web.json_response({"ok": True, "games": games})
