"""Elfministration configuration and diagnostics for Verdant Conclave."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import discord
from aiohttp import web

import bigtree
from bigtree.games.conclave import engine, server_config
from bigtree.games.conclave.store import ConclaveStore
from bigtree.inc.logging import logger
from bigtree.inc.webserver import frontend_route, get_server, route


def _render() -> str:
    server = get_server()
    if server is None:
        return "<h1>Verdant Conclave</h1>"
    return server.render_template("conclave_settings.html", {})


def _guild() -> Optional[discord.Guild]:
    bot = getattr(bigtree, "bot", None)
    if bot is None:
        return None
    guild_id = int(getattr(bigtree, "guildid", 0) or 0)
    guild = bot.get_guild(guild_id) if guild_id else None
    if guild is not None:
        return guild
    guilds = list(getattr(bot, "guilds", []) or [])
    return guilds[0] if guilds else None


def _store() -> ConclaveStore:
    return ConclaveStore()


async def _config() -> Dict[str, Any]:
    return await asyncio.to_thread(server_config.get_config)


async def _resolve_hub_channel(config: Dict[str, Any]) -> Optional[discord.TextChannel]:
    channel_id = int(config.get("parent_channel_id") or 0)
    if not channel_id:
        return None
    bot = getattr(bigtree, "bot", None)
    channel = bot.get_channel(channel_id) if bot else None
    if channel is None and bot is not None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
    return channel if isinstance(channel, discord.TextChannel) else None


async def _find_webhook(
    channel: discord.TextChannel,
    webhook_id: Any = None,
) -> Optional[discord.Webhook]:
    try:
        wanted = int(webhook_id or 0)
    except Exception:
        wanted = 0
    try:
        hooks = await channel.webhooks()
    except (discord.Forbidden, discord.HTTPException):
        return None
    if wanted:
        for hook in hooks:
            if int(hook.id) == wanted:
                return hook
    for hook in hooks:
        if hook.name == server_config.WEBHOOK_NAME:
            return hook
    return None


async def _server_status() -> Dict[str, Any]:
    config = await _config()
    guild = _guild()
    channel = await _resolve_hub_channel(config)
    bot = getattr(bigtree, "bot", None)
    message_content = bool(getattr(getattr(bot, "intents", None), "message_content", False))
    permissions: Dict[str, bool] = {}
    webhook = None
    if guild is not None and channel is not None:
        member = guild.me
        if member is not None:
            perms = channel.permissions_for(member)
            permissions = {
                "view_channel": bool(perms.view_channel),
                "send_messages": bool(perms.send_messages),
                "read_message_history": bool(perms.read_message_history),
                "manage_messages": bool(perms.manage_messages),
                "manage_webhooks": bool(perms.manage_webhooks),
                "create_private_threads": bool(perms.create_private_threads),
                "manage_threads": bool(perms.manage_threads),
            }
        webhook = await _find_webhook(channel, config.get("webhook_id"))
        if webhook is not None and int(config.get("webhook_id") or 0) != int(webhook.id):
            config["webhook_id"] = int(webhook.id)
            await asyncio.to_thread(server_config.save_config, config)

    required = (
        "view_channel",
        "send_messages",
        "read_message_history",
        "manage_webhooks",
        "create_private_threads",
        "manage_threads",
    )
    permission_ready = all(permissions.get(key, False) for key in required)
    immersive_ready = (
        permission_ready
        and permissions.get("manage_messages", False)
        and message_content
    )
    active = await asyncio.to_thread(_store().list_active, 500)
    if guild is not None:
        active = [
            item for item in active
            if int(item.get("guild_id") or 0) == int(guild.id)
        ]
    return {
        "config": config,
        "guild": {
            "id": int(guild.id) if guild else None,
            "name": guild.name if guild else None,
        },
        "channel": {
            "id": int(channel.id) if channel else None,
            "name": channel.name if channel else None,
        },
        "webhook": {
            "configured": webhook is not None,
            "id": int(webhook.id) if webhook else None,
            "name": webhook.name if webhook else None,
        },
        "permissions": permissions,
        "message_content_intent": message_content,
        "ready": permission_ready,
        "hub_webhook_ready": webhook is not None,
        "immersive_alias_ready": immersive_ready,
        "sealed_alias_ready": permission_ready,
        "active_games": len(active),
        "max_concurrent_games": int(config.get("max_concurrent_games") or 4),
    }


def _cog():
    bot = getattr(bigtree, "bot", None)
    return bot.get_cog("VerdantConclave") if bot else None


@frontend_route("GET", "/admin/verdant", allow_public=True)
async def verdant_settings_page(_req: web.Request) -> web.Response:
    return web.Response(text=_render(), content_type="text/html")


@route("GET", "/admin/verdant/status", scopes=["admin:web"])
async def verdant_status(_req: web.Request) -> web.Response:
    return web.json_response({"ok": True, **(await _server_status())})


@route("GET", "/admin/verdant/channels", scopes=["admin:web"])
async def verdant_channels(_req: web.Request) -> web.Response:
    guild = _guild()
    channels = []
    if guild is not None:
        for channel in guild.text_channels:
            channels.append({
                "id": str(channel.id),
                "name": channel.name,
                "category": channel.category.name if channel.category else "",
            })
    return web.json_response({"ok": True, "channels": channels})


@route("POST", "/admin/verdant/config", scopes=["admin:web"])
async def update_verdant_config(req: web.Request) -> web.Response:
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "body must be an object"}, status=400)

    config = await _config()
    if "enabled" in body:
        config["enabled"] = server_config.as_bool(body.get("enabled"), True)
    if "parent_channel_id" in body:
        value = str(body.get("parent_channel_id") or "").strip()
        if value and not value.isdigit():
            return web.json_response(
                {"ok": False, "error": "hub channel id must be numeric"},
                status=400,
            )
        new_id = int(value) if value else None
        if new_id != config.get("parent_channel_id"):
            config["webhook_id"] = None
        config["parent_channel_id"] = new_id
    if "aliases_enabled" in body:
        config["aliases_enabled"] = server_config.as_bool(body.get("aliases_enabled"), True)
    if "alias_mode" in body:
        mode = str(body.get("alias_mode") or "immersive").strip().lower()
        if mode not in {"immersive", "sealed"}:
            return web.json_response(
                {"ok": False, "error": "alias mode must be immersive or sealed"},
                status=400,
            )
        config["alias_mode"] = mode
    if "alias_choice" in body:
        choice = str(body.get("alias_choice") or "both").strip().lower()
        if choice not in {"generated", "custom", "both"}:
            return web.json_response({"ok": False, "error": "invalid alias choice"}, status=400)
        config["alias_choice"] = choice
    if "dm_delivery" in body:
        delivery = str(body.get("dm_delivery") or "optional").strip().lower()
        if delivery not in {"off", "optional", "on"}:
            return web.json_response({"ok": False, "error": "invalid DM delivery policy"}, status=400)
        config["dm_delivery"] = delivery
    if "max_concurrent_games" in body:
        config["max_concurrent_games"] = server_config.bounded_int(
            body.get("max_concurrent_games"), 4, 1, 20
        )
    if "auto_manage_webhook" in body:
        config["auto_manage_webhook"] = server_config.as_bool(
            body.get("auto_manage_webhook"), True
        )
    await asyncio.to_thread(server_config.save_config, config)
    return web.json_response({"ok": True, **(await _server_status())})


@route("POST", "/admin/verdant/webhook", scopes=["admin:web"])
async def ensure_hub_webhook(_req: web.Request) -> web.Response:
    config = await _config()
    channel = await _resolve_hub_channel(config)
    if channel is None:
        return web.json_response(
            {"ok": False, "error": "Choose a valid Discord hub text channel first."},
            status=409,
        )
    hook = await _find_webhook(channel, config.get("webhook_id"))
    if hook is None:
        try:
            hook = await channel.create_webhook(
                name=server_config.WEBHOOK_NAME,
                reason="Verdant Conclave server identity relay",
            )
        except discord.Forbidden:
            return web.json_response(
                {"ok": False, "error": "The bot does not have Manage Webhooks in that channel."},
                status=403,
            )
        except discord.HTTPException as exc:
            return web.json_response(
                {"ok": False, "error": f"Discord rejected webhook creation: {exc}"},
                status=502,
            )
    config["webhook_id"] = int(hook.id)
    await asyncio.to_thread(server_config.save_config, config)
    return web.json_response({"ok": True, **(await _server_status())})


@route("DELETE", "/admin/verdant/webhook", scopes=["admin:web"])
async def delete_hub_webhook(_req: web.Request) -> web.Response:
    config = await _config()
    channel = await _resolve_hub_channel(config)
    hook = await _find_webhook(channel, config.get("webhook_id")) if channel else None
    if hook is not None:
        try:
            await hook.delete(reason="Verdant Conclave hub webhook removed from Elfministration")
        except (discord.Forbidden, discord.HTTPException) as exc:
            return web.json_response(
                {"ok": False, "error": f"Could not delete webhook: {exc}"},
                status=502,
            )
    config["webhook_id"] = None
    await asyncio.to_thread(server_config.save_config, config)
    return web.json_response({"ok": True, **(await _server_status())})


@route("GET", "/admin/verdant/games", scopes=["admin:web"])
async def verdant_games(_req: web.Request) -> web.Response:
    states = await asyncio.to_thread(_store().list_active, 100)
    guild = _guild()
    if guild is not None:
        states = [
            state for state in states
            if int(state.get("guild_id") or 0) == int(guild.id)
        ]
    cog = _cog()
    games = []
    for state in states:
        if cog and hasattr(cog, "inspect_game_health"):
            try:
                games.append(await cog.inspect_game_health(str(state.get("game_id") or "")))
                continue
            except Exception as exc:
                logger.warning(
                    "[conclave] health inspection failed game=%s: %s",
                    state.get("game_id"),
                    exc,
                )
        games.append({
            "game_id": state.get("game_id"),
            "title": state.get("title"),
            "phase": state.get("phase"),
            "channel_id": state.get("channel_id"),
            "healthy": False,
            "error": "Discord Conclave controller unavailable",
        })
    return web.json_response({"ok": True, "games": games})


@route("POST", "/admin/verdant/games/{game_id}/repair", scopes=["admin:web"])
async def repair_verdant_game(req: web.Request) -> web.Response:
    game_id = str(req.match_info.get("game_id") or "")
    cog = _cog()
    if not cog or not hasattr(cog, "repair_game_foundation"):
        return web.json_response(
            {"ok": False, "error": "Discord Conclave controller unavailable"},
            status=503,
        )
    try:
        health = await cog.repair_game_foundation(game_id)
    except engine.GameError as exc:
        return web.json_response(
            {"ok": False, "error": str(exc), "code": exc.code},
            status=409,
        )
    auth = req.get("bt_auth") or {}
    logger.info(
        "[conclave] admin repair game=%s requester=%s",
        game_id,
        auth.get("user_id") or "unknown",
    )
    return web.json_response({"ok": True, "game": health})


@route("GET", "/admin/verdant/games/{game_id}/identities", scopes=["admin:web"])
async def resolve_verdant_identities(req: web.Request) -> web.Response:
    """Moderator-only identity resolution; deliberately excludes secret roles."""
    game_id = str(req.match_info.get("game_id") or "")
    state = await asyncio.to_thread(_store().get, game_id)
    if not state:
        return web.json_response({"ok": False, "error": "not found"}, status=404)
    identities = []
    for player_obj in (state.get("players") or {}).values():
        identities.append({
            "forest_name": player_obj.get("forest_name"),
            "discord_user_id": player_obj.get("user_id"),
            "discord_display_name": player_obj.get("display_name"),
            "alive": bool(player_obj.get("alive", True)),
            "synthetic": bool(player_obj.get("synthetic")),
        })
    identities.sort(
        key=lambda item: str(
            item.get("forest_name") or item.get("discord_display_name") or ""
        ).casefold()
    )
    auth = req.get("bt_auth") or {}
    logger.warning(
        "[conclave] moderator identity map viewed game=%s requester=%s count=%s",
        game_id,
        auth.get("user_id") or "unknown",
        len(identities),
    )
    return web.json_response({
        "ok": True,
        "game_id": game_id,
        "identities": identities,
        "audit": "Identity resolution was written to the server log.",
    })
