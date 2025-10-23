# bigtree/webmods/health.py
from __future__ import annotations
from aiohttp import web
import bigtree
from bigtree.inc.webserver import route

@route("GET", "/healthz", allow_public=True)
async def health(_req: web.Request):
    return web.json_response({"ok": True})

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
        }
    )
