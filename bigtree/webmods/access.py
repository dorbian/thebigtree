from __future__ import annotations

from aiohttp import web

import bigtree
from bigtree.inc import access_control
from bigtree.inc.webserver import route


def _guild():
    guild_id = str(getattr(bigtree, "guildid", "") or "").strip()
    for guild in getattr(bigtree.bot, "guilds", []) or []:
        if guild_id and str(getattr(guild, "id", "")) == guild_id:
            return guild
    guilds = list(getattr(bigtree.bot, "guilds", []) or [])
    return guilds[0] if guilds else None


@route("GET", "/admin/access/catalog", scopes=["admin:web", "system.permissions"])
async def access_catalog(_req: web.Request) -> web.Response:
    """Inspectable phase-1 IAM catalogue; contains no credentials/secrets."""
    try:
        payload = access_control.catalog_snapshot()
        return web.json_response({"ok": True, **payload})
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


@route("POST", "/admin/access/evaluate", scopes=["admin:web", "system.permissions"])
async def access_evaluate(req: web.Request) -> web.Response:
    """Explain one Discord-member permission decision without changing state."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    capability = access_control.normalize_capability(body.get("capability"))
    discord_user_id = str(body.get("discord_user_id") or "").strip()
    if not capability or not discord_user_id.isdigit():
        return web.json_response(
            {"ok": False, "error": "discord_user_id and capability are required"},
            status=400,
        )

    guild = _guild()
    if guild is None:
        return web.json_response({"ok": False, "error": "Discord guild unavailable"}, status=503)
    member = guild.get_member(int(discord_user_id))
    if member is None:
        return web.json_response(
            {"ok": False, "error": "Discord member is not available in the guild cache"},
            status=404,
        )

    ancestors = body.get("ancestors") if isinstance(body.get("ancestors"), list) else []
    decision = access_control.evaluate_discord_member(
        member,
        capability,
        resource_type=str(body.get("resource_type") or ""),
        resource_id=str(body.get("resource_id") or ""),
        ancestors=ancestors,
    )
    return web.json_response(
        {
            "ok": True,
            "member": {
                "id": str(member.id),
                "name": getattr(member, "display_name", None) or getattr(member, "name", None),
                "discord_roles": [
                    {"id": str(getattr(role, "id", "")), "name": str(getattr(role, "name", ""))}
                    for role in getattr(member, "roles", [])
                ],
            },
            "decision": decision.as_dict(),
        }
    )
