from __future__ import annotations

import asyncio
import os
from aiohttp import web

import bigtree
from bigtree.inc.database import get_database
from bigtree.inc.webserver import route


def _build_info():
    sha = str(os.getenv("BIGTREE_BUILD_SHA") or "unknown").strip() or "unknown"
    return {"sha": sha}


@route("GET", "/healthz", allow_public=True)
async def health(_req: web.Request):
    """Liveness probe: the aiohttp process can answer requests."""
    return web.json_response({"ok": True, "build": _build_info()})


@route("GET", "/readyz", allow_public=True)
async def readiness(_req: web.Request):
    """Readiness probe used before an auto-replaced container receives traffic."""
    bot = getattr(bigtree, "bot", None)
    discord_ready = bool(bot and bot.is_ready())
    database_ready = await asyncio.to_thread(get_database().ping)
    ok = discord_ready and database_ready
    return web.json_response(
        {
            "ok": ok,
            "discord": discord_ready,
            "database": database_ready,
            "build": _build_info(),
        },
        status=200 if ok else 503,
    )


@route("GET", "/bot", allow_public=True)
async def bot_info(_req: web.Request):
    bot = bigtree.bot
    guild = bot.get_guild(bigtree.guildid)
    return web.json_response(
        {
            "user": str(bot.user) if bot.user else None,
            "latency_sec": getattr(bot, "latency", None),
            "guild": {
                "id": bigtree.guildid,
                "name": getattr(guild, "name", None),
                "member_count": getattr(guild, "member_count", None),
            },
            "build": _build_info(),
        }
    )
