"""Host API for Verdant Conclave.

This API intentionally exposes only public/host-operational state. Living role
identities and private night choices never leave the Discord game engine.
"""
from __future__ import annotations

import asyncio
from typing import Callable

from aiohttp import web

import bigtree
from bigtree.games.conclave import engine
from bigtree.games.conclave.store import ConclaveStore
from bigtree.inc.webserver import route


async def _store_call(fn: Callable, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


def _store() -> ConclaveStore:
    return ConclaveStore()


async def _refresh_panel(game_id: str, state: dict) -> None:
    bot = getattr(bigtree, "bot", None)
    cog = bot.get_cog("VerdantConclave") if bot else None
    if cog and hasattr(cog, "refresh_game_panel"):
        try:
            await cog.refresh_game_panel(game_id, state)
        except Exception:
            pass


@route("GET", "/admin/conclave/sessions", scopes=["game.conclave.host"])
async def list_sessions(req: web.Request) -> web.Response:
    include_ended = str(req.query.get("include_ended") or "0").lower() in {"1", "true", "yes"}
    store = _store()
    if include_ended:
        rows = await _store_call(
            store.db._fetchall,
            """
            SELECT payload FROM games
            WHERE module = %s
            ORDER BY created_at DESC NULLS LAST, id DESC
            LIMIT 100
            """,
            (engine.MODULE,),
        )
        states = [dict(row.get("payload") or {}) for row in rows or []]
    else:
        states = await _store_call(store.list_active, 100)
    return web.json_response({"ok": True, "sessions": [engine.public_state(s) for s in states]})


@route("GET", "/admin/conclave/{game_id}", scopes=["game.conclave.host"])
async def get_session(req: web.Request) -> web.Response:
    game_id = req.match_info.get("game_id") or ""
    state = await _store_call(_store().get, game_id)
    if not state:
        return web.json_response({"ok": False, "error": "not found"}, status=404)
    return web.json_response({"ok": True, "session": engine.public_state(state)})


@route("POST", "/admin/conclave/{game_id}/join-self", scopes=["game.conclave.host"])
async def join_self(req: web.Request) -> web.Response:
    """Join the authenticated Discord-backed Elfministration user as a real player."""
    game_id = req.match_info.get("game_id") or ""
    auth = req.get("bt_auth") or {}
    try:
        user_id = int(auth.get("user_id") or 0)
    except Exception:
        user_id = 0
    if not user_id:
        return web.json_response(
            {
                "ok": False,
                "error": "This Elfministration credential is not linked to a Discord user. Open Elfministration through /auth and try again.",
            },
            status=409,
        )

    state = await _store_call(_store().get, game_id)
    if not state:
        return web.json_response({"ok": False, "error": "not found"}, status=404)

    display_name = str(auth.get("user_name") or f"Discord user {user_id}")[:80]
    bot = getattr(bigtree, "bot", None)
    guild = bot.get_guild(int(state.get("guild_id") or 0)) if bot else None
    if guild is not None:
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except Exception:
                member = None
        if member is not None:
            display_name = str(member.display_name or member.name or display_name)[:80]

    try:
        state = await _store_call(
            _store().mutate,
            game_id,
            lambda current: engine.add_player(current, user_id, display_name),
        )
    except engine.GameError as exc:
        return web.json_response({"ok": False, "error": str(exc), "code": exc.code}, status=409)
    await _refresh_panel(game_id, state)
    refreshed = await _store_call(_store().get, game_id) or state
    return web.json_response({
        "ok": True,
        "joined_user_id": user_id,
        "session": engine.public_state(refreshed),
    })


async def _mutate(req: web.Request, action: str) -> web.Response:
    game_id = req.match_info.get("game_id") or ""
    store = _store()
    try:
        if action == "start":
            mutator = engine.start_game
        elif action == "advance":
            mutator = engine.advance_phase
        elif action == "end":
            mutator = engine.end_game
        else:
            return web.json_response({"ok": False, "error": "invalid action"}, status=400)
        state = await _store_call(store.mutate, game_id, mutator)
    except engine.GameError as exc:
        return web.json_response({"ok": False, "error": str(exc), "code": exc.code}, status=409)
    await _refresh_panel(game_id, state)
    return web.json_response({"ok": True, "session": engine.public_state(state)})


@route("POST", "/admin/conclave/{game_id}/panel", scopes=["game.conclave.host"])
async def recreate_panel(req: web.Request) -> web.Response:
    game_id = req.match_info.get("game_id") or ""
    bot = getattr(bigtree, "bot", None)
    cog = bot.get_cog("VerdantConclave") if bot else None
    if not cog or not hasattr(cog, "recreate_game_panel"):
        return web.json_response({"ok": False, "error": "Discord Conclave controller unavailable"}, status=503)
    try:
        state = await cog.recreate_game_panel(game_id)
    except engine.GameError as exc:
        return web.json_response({"ok": False, "error": str(exc), "code": exc.code}, status=409)
    return web.json_response({"ok": True, "session": engine.public_state(state)})


@route("POST", "/admin/conclave/{game_id}/start", scopes=["game.conclave.host"])
async def start_session(req: web.Request) -> web.Response:
    return await _mutate(req, "start")


@route("POST", "/admin/conclave/{game_id}/advance", scopes=["game.conclave.host"])
async def advance_session(req: web.Request) -> web.Response:
    return await _mutate(req, "advance")


@route("POST", "/admin/conclave/{game_id}/end", scopes=["game.conclave.host"])
async def end_session(req: web.Request) -> web.Response:
    return await _mutate(req, "end")


@route("POST", "/admin/conclave/{game_id}/test-players", scopes=["game.conclave.host"])
async def add_test_players(req: web.Request) -> web.Response:
    """Add synthetic lobby players for host testing only.

    Test players are stored inside the game payload in PostgreSQL. They are not
    Discord users and never receive private role/action messages.
    """
    game_id = req.match_info.get("game_id") or ""
    try:
        body = await req.json()
    except Exception:
        body = {}
    try:
        count = int(body.get("count") or 1)
    except Exception:
        count = 1
    target_total = body.get("target_total")
    try:
        target_total = int(target_total) if target_total is not None else None
    except Exception:
        target_total = None
    try:
        state = await _store_call(
            _store().mutate,
            game_id,
            lambda s: engine.add_test_players(s, count, target_total=target_total),
        )
    except engine.GameError as exc:
        return web.json_response({"ok": False, "error": str(exc), "code": exc.code}, status=409)
    await _refresh_panel(game_id, state)
    return web.json_response({"ok": True, "session": engine.public_state(state)})


@route("DELETE", "/admin/conclave/{game_id}/test-players", scopes=["game.conclave.host"])
async def clear_test_players(req: web.Request) -> web.Response:
    game_id = req.match_info.get("game_id") or ""
    try:
        state = await _store_call(_store().mutate, game_id, engine.remove_test_players)
    except engine.GameError as exc:
        return web.json_response({"ok": False, "error": str(exc), "code": exc.code}, status=409)
    await _refresh_panel(game_id, state)
    return web.json_response({"ok": True, "session": engine.public_state(state)})


@route("POST", "/admin/conclave/{game_id}/test-act", scopes=["game.conclave.host"])
async def simulate_test_players(req: web.Request) -> web.Response:
    game_id = req.match_info.get("game_id") or ""
    before = await _store_call(_store().get, game_id)
    if not before:
        return web.json_response({"ok": False, "error": "not found"}, status=404)
    phase = str(before.get("phase") or "")
    try:
        state = await _store_call(_store().mutate, game_id, engine.simulate_test_players)
    except engine.GameError as exc:
        return web.json_response({"ok": False, "error": str(exc), "code": exc.code}, status=409)
    simulation = dict(state.get("test_last_simulation") or {})
    await _refresh_panel(game_id, state)
    return web.json_response({
        "ok": True,
        "phase": phase,
        "simulation": simulation,
        "session": engine.public_state(state),
    })
