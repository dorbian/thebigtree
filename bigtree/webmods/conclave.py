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


@route("GET", "/admin/conclave/sessions", scopes=["conclave:admin"])
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


@route("GET", "/admin/conclave/{game_id}", scopes=["conclave:admin"])
async def get_session(req: web.Request) -> web.Response:
    game_id = req.match_info.get("game_id") or ""
    state = await _store_call(_store().get, game_id)
    if not state:
        return web.json_response({"ok": False, "error": "not found"}, status=404)
    return web.json_response({"ok": True, "session": engine.public_state(state)})


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


@route("POST", "/admin/conclave/{game_id}/start", scopes=["conclave:admin"])
async def start_session(req: web.Request) -> web.Response:
    return await _mutate(req, "start")


@route("POST", "/admin/conclave/{game_id}/advance", scopes=["conclave:admin"])
async def advance_session(req: web.Request) -> web.Response:
    return await _mutate(req, "advance")


@route("POST", "/admin/conclave/{game_id}/end", scopes=["conclave:admin"])
async def end_session(req: web.Request) -> web.Response:
    return await _mutate(req, "end")
