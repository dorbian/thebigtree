from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from aiohttp import web

import bigtree
from bigtree.inc import ai, discord_knowledge, language_memory
from bigtree.inc.database import get_database
from bigtree.inc.webserver import frontend_route, get_server, route


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def _int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def _float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def _channel_ids(value: Any) -> List[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = value.split(",")
    else:
        items = []
    out: List[str] = []
    seen = set()
    for item in items:
        channel_id = str(item or "").strip()
        if not channel_id or not channel_id.isdigit() or channel_id in seen:
            continue
        seen.add(channel_id)
        out.append(channel_id)
        if len(out) >= 20:
            break
    return out


def _titles(value: Any) -> List[str]:
    if isinstance(value, str):
        items = value.splitlines()
    elif isinstance(value, list):
        items = value
    else:
        items = []
    out: List[str] = []
    seen = set()
    for item in items:
        title = str(item or "").strip()[:80]
        if not title or title.casefold() in seen:
            continue
        seen.add(title.casefold())
        out.append(title)
        if len(out) >= 24:
            break
    return out


def _render_language_page() -> str:
    server = get_server()
    if server is None:
        return "<h1>Language Services</h1>"
    return server.render_template("language.html", {})


async def _language_status() -> Dict[str, Any]:
    try:
        memories = await asyncio.to_thread(language_memory.memory_stats)
    except Exception as exc:
        memories = {"total": 0, "pinned": 0, "conversation": 0, "users": 0, "content_bytes": 0, "error": str(exc)}
    status = ai.get_language_status()
    status["memory_stats"] = memories
    return status


@frontend_route("GET", "/admin/language", allow_public=True)
async def language_services_page(_req: web.Request) -> web.Response:
    return web.Response(text=_render_language_page(), content_type="text/html")


@route("GET", "/admin/language/status", scopes=["admin:web"])
async def language_status(_req: web.Request) -> web.Response:
    return web.json_response({"ok": True, "language": await _language_status()})


@route("POST", "/admin/language/config", scopes=["admin:web"])
async def update_language_config(req: web.Request) -> web.Response:
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "body must be an object"}, status=400)

    provider = str(body.get("provider") or "openai").strip().lower()
    if provider not in ai.PROVIDERS:
        return web.json_response({"ok": False, "error": "provider must be openai or minimax"}, status=400)

    db = get_database()
    config = await asyncio.to_thread(db.get_system_config, "language") or {}
    config = dict(config)
    config["provider"] = provider

    provider_keys = config.get("provider_keys")
    if not isinstance(provider_keys, dict):
        provider_keys = {}
    provider_keys = dict(provider_keys)
    if _bool(body.get("clear_api_key"), False):
        provider_keys.pop(provider, None)
    else:
        api_key = str(body.get("api_key") or "").strip()
        if api_key:
            if len(api_key) < 16:
                return web.json_response({"ok": False, "error": "API key looks too short"}, status=400)
            provider_keys[provider] = api_key[:512]
    config["provider_keys"] = provider_keys

    if "model" in body:
        model = str(body.get("model") or "").strip()
        if not model:
            return web.json_response({"ok": False, "error": "model is required"}, status=400)
        provider_models = config.get("provider_models")
        if not isinstance(provider_models, dict):
            provider_models = {}
        provider_models = dict(provider_models)
        provider_models[provider] = model[:120]
        config["provider_models"] = provider_models

    if "temperature" in body:
        config["temperature"] = _float(body.get("temperature"), 0.7, 0.0, 2.0)
    if "max_output_tokens" in body:
        config["max_output_tokens"] = _int(body.get("max_output_tokens"), 1200, 64, 16384)
    if "reasoning_mode" in body:
        mode = str(body.get("reasoning_mode") or "automatic").strip().lower()
        if mode not in {"automatic", "disabled"}:
            return web.json_response({"ok": False, "error": "invalid reasoning mode"}, status=400)
        config["reasoning_mode"] = mode
    if "enable_priest_chat" in body:
        config["enable_priest_chat"] = _bool(body.get("enable_priest_chat"), True)
    if "memory_enabled" in body:
        config["memory_enabled"] = _bool(body.get("memory_enabled"), True)
    if "memory_turns" in body:
        config["memory_turns"] = _int(body.get("memory_turns"), 6, 1, 20)
    if "memory_retention_days" in body:
        config["memory_retention_days"] = _int(body.get("memory_retention_days"), 90, 1, 365)
    if "memory_global_row_cap" in body:
        config["memory_global_row_cap"] = _int(body.get("memory_global_row_cap"), 5000, 100, 20000)
    if "discord_context_enabled" in body:
        config["discord_context_enabled"] = _bool(body.get("discord_context_enabled"), False)
    if "discord_context_channel_ids" in body:
        config["discord_context_channel_ids"] = _channel_ids(body.get("discord_context_channel_ids"))
    if "system_prompt" in body:
        system_prompt = str(body.get("system_prompt") or "").strip()
        config["system_prompt"] = system_prompt[:16000]

    if "reverence" in body:
        incoming = body.get("reverence")
        if not isinstance(incoming, dict):
            return web.json_response({"ok": False, "error": "reverence must be an object"}, status=400)
        reverence = config.get("reverence")
        if not isinstance(reverence, dict):
            reverence = {}
        reverence = dict(reverence)
        if "enabled" in incoming:
            reverence["enabled"] = _bool(incoming.get("enabled"), True)
        if "strictness" in incoming:
            strictness = str(incoming.get("strictness") or "moderate").strip().lower()
            if strictness not in {"gentle", "moderate", "ceremonial"}:
                return web.json_response({"ok": False, "error": "invalid reverence strictness"}, status=400)
            reverence["strictness"] = strictness
        if "require_proper_address" in incoming:
            reverence["require_proper_address"] = _bool(incoming.get("require_proper_address"), True)
        if "casual_policy" in incoming:
            policy = str(incoming.get("casual_policy") or "correct_only").strip().lower()
            if policy not in {"correct_only", "correct_then_answer"}:
                return web.json_response({"ok": False, "error": "invalid casual address policy"}, status=400)
            reverence["casual_policy"] = policy
        if "priest_familiarity" in incoming:
            reverence["priest_familiarity"] = _bool(incoming.get("priest_familiarity"), True)
        if "emergency_override" in incoming:
            reverence["emergency_override"] = _bool(incoming.get("emergency_override"), True)
        if "accepted_titles" in incoming:
            titles = _titles(incoming.get("accepted_titles"))
            reverence["accepted_titles"] = titles or list(ai.REVERENCE_DEFAULT_TITLES)
        config["reverence"] = reverence

    await asyncio.to_thread(db.update_system_config, "language", config)
    ai.reset_client_cache()
    return web.json_response({"ok": True, "language": await _language_status()})


@route("POST", "/admin/language/test", scopes=["admin:web"])
async def test_language_provider(req: web.Request) -> web.Response:
    try:
        body = await req.json()
    except Exception:
        body = {}
    prompt = str((body or {}).get("prompt") or "Reply with a short confirmation that the roots are listening.").strip()
    try:
        reply = await ai.ask(user_id=0, prompt=prompt[:1000], persona="plain")
    except Exception as exc:
        return web.json_response(
            {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:500]}", "language": await _language_status()},
            status=502,
        )
    return web.json_response({"ok": True, "reply": reply, "language": await _language_status()})


@route("GET", "/admin/language/quota", scopes=["admin:web"])
async def language_provider_quota(_req: web.Request) -> web.Response:
    try:
        quota = await ai.get_provider_quota()
    except Exception as exc:
        return web.json_response({"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:500]}"}, status=502)
    return web.json_response({"ok": True, **quota})


@route("GET", "/admin/language/memories", scopes=["admin:web"])
async def list_language_memories(req: web.Request) -> web.Response:
    scope_type = (req.query.get("scope_type") or "").strip().lower() or None
    scope_id = req.query.get("scope_id")
    kind = (req.query.get("kind") or "").strip().lower() or None
    limit = _int(req.query.get("limit"), 100, 1, 500)
    try:
        memories = await asyncio.to_thread(
            language_memory.list_memories,
            scope_type=scope_type,
            scope_id=scope_id,
            kind=kind,
            limit=limit,
        )
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)
    return web.json_response({"ok": True, "memories": memories, "count": len(memories)})


@route("POST", "/admin/language/memories", scopes=["admin:web"])
async def create_language_memory(req: web.Request) -> web.Response:
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)
    try:
        memory = await asyncio.to_thread(
            language_memory.add_memory,
            content=str(body.get("content") or ""),
            scope_type=str(body.get("scope_type") or "global"),
            scope_id=str(body.get("scope_id") or ""),
            kind=str(body.get("kind") or "note"),
            role="system",
            source="operator",
            pinned=_bool(body.get("pinned"), True),
        )
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)
    return web.json_response({"ok": True, "memory": memory})


@route("DELETE", "/admin/language/memories/{memory_id}", scopes=["admin:web"])
async def delete_language_memory(req: web.Request) -> web.Response:
    try:
        memory_id = int(req.match_info.get("memory_id") or 0)
    except Exception:
        memory_id = 0
    if memory_id <= 0:
        return web.json_response({"ok": False, "error": "invalid memory id"}, status=400)
    deleted = await asyncio.to_thread(language_memory.delete_memory, memory_id)
    if not deleted:
        return web.json_response({"ok": False, "error": "memory not found"}, status=404)
    return web.json_response({"ok": True})


@route("POST", "/admin/language/memories/clear-conversations", scopes=["admin:web"])
async def clear_language_conversations(req: web.Request) -> web.Response:
    try:
        body = await req.json()
    except Exception:
        body = {}
    user_id = (body or {}).get("user_id")
    if user_id in (None, ""):
        parsed_user_id = None
    else:
        try:
            parsed_user_id = int(user_id)
        except Exception:
            return web.json_response({"ok": False, "error": "user_id must be an integer"}, status=400)
    deleted = await asyncio.to_thread(language_memory.clear_conversation_memory, parsed_user_id)
    return web.json_response({"ok": True, "deleted": deleted})


@route("POST", "/admin/language/memories/prune", scopes=["admin:web"])
async def prune_language_conversations(_req: web.Request) -> web.Response:
    cfg = ai.get_language_config()
    deleted = await asyncio.to_thread(
        language_memory.prune_conversation_memory,
        retention_days=int(cfg.get("memory_retention_days", 90)),
        global_row_cap=int(cfg.get("memory_global_row_cap", 5000)),
    )
    return web.json_response({"ok": True, "deleted": deleted, "language": await _language_status()})


@route("GET", "/admin/language/discord/channels", scopes=["admin:web"])
async def language_discord_channels(_req: web.Request) -> web.Response:
    bot = getattr(bigtree, "bot", None)
    if bot is None:
        return web.json_response({"ok": False, "error": "Discord bot is not ready"}, status=503)
    channels = discord_knowledge.list_readable_channels(bot)
    return web.json_response({
        "ok": True,
        "channels": channels,
        "message_content_intent": bool(getattr(getattr(bot, "intents", None), "message_content", False)),
    })


@route("GET", "/admin/language/discord/search", scopes=["admin:web"])
async def language_discord_search(req: web.Request) -> web.Response:
    bot = getattr(bigtree, "bot", None)
    if bot is None:
        return web.json_response({"ok": False, "error": "Discord bot is not ready"}, status=503)
    query = str(req.query.get("q") or "").strip()
    if len(query) < 2:
        return web.json_response({"ok": False, "error": "Search query must be at least 2 characters"}, status=400)
    channel_id = str(req.query.get("channel_id") or "").strip()
    limit = _int(req.query.get("limit"), 30, 1, 100)
    channel_ids = [channel_id] if channel_id else None
    rows = await discord_knowledge.search_discord(
        bot,
        query,
        channel_ids=channel_ids,
        limit=limit,
        per_channel=500 if channel_id else 120,
        max_channels=1 if channel_id else 20,
        include_bots=False,
    )
    return web.json_response({"ok": True, "query": query, "results": rows, "count": len(rows)})
