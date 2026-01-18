# bigtree/webmods/admin.py
from __future__ import annotations
from aiohttp import web
from typing import Any, Dict
import json
from pathlib import Path
import time
import os
from tinydb import TinyDB, Query
import bigtree
from bigtree.inc.plogon import get_with_leaf_path
from bigtree.inc.webserver import route
from bigtree.inc import web_tokens
from bigtree.inc.settings import load_settings
from bigtree.inc.database import get_database
from bigtree.inc.jsonutil import to_jsonable
from pathlib import Path
from bigtree.inc.logging import logger, auth_logger, upload_logger, log_path, auth_log_path, upload_log_path
import discord

# ---------- TinyDB for admin clients ----------
def _admin_db_path() -> str:
    contest_dir = getattr(bigtree, "contest_dir", "/data/contest")
    return os.path.join(contest_dir, "admin_clients.json")

def _admin_db() -> TinyDB:
    path = _admin_db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return TinyDB(path)

def _extract_token(req: web.Request) -> str:
    auth = req.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth.split(" ", 1)[1].strip()
    return req.headers.get("X-Bigtree-Key") or req.headers.get("X-API-Key") or ""

def _find_web_token(token: str) -> Dict[str, Any]:
    if not token:
        return {}
    for t in web_tokens.load_tokens():
        if t.get("token") == token:
            return t
    return {}

def _split_scopes(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(s).strip() for s in raw if str(s).strip()]
    if isinstance(raw, str):
        return [s.strip() for s in raw.split(",") if s.strip()]
    if isinstance(raw, dict):
        return [str(s).strip() for s in raw.keys() if str(s).strip()]
    return []

def _resolve_token_scopes(token: str) -> tuple[bool, list[str], str]:
    doc = _find_web_token(token)
    if doc:
        scopes = doc.get("scopes")
        scope_list = _split_scopes(scopes)
        return True, scope_list or ["*"], "web_token"

    api_keys = set()
    scopes_map: Dict[str, Any] = {}
    try:
        if hasattr(bigtree, "settings") and bigtree.settings:
            sec = bigtree.settings.section("WEB")
            if isinstance(sec, dict):
                api_keys = set(sec.get("api_keys", []) or [])
                scopes_map = sec.get("api_key_scopes", {}) or {}
            else:
                api_keys = set(bigtree.settings.get("WEB.api_keys", [], cast="json") or [])
                scopes_map = bigtree.settings.get("WEB.api_key_scopes", {}, cast="json") or {}
    except Exception:
        api_keys = set()
        scopes_map = {}

    if token in api_keys:
        if not scopes_map:
            return True, ["*"], "api_key"
        return True, _split_scopes(scopes_map.get(token)), "api_key"


def _read_log_tail(path: str, max_lines: int = 200, max_bytes: int = 200_000) -> list[str]:
    if not path:
        return []
    if not os.path.exists(path):
        return []
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            if size == 0:
                return []
            read_size = min(size, max_bytes)
            fh.seek(-read_size, os.SEEK_END)
            data = fh.read(read_size)
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if max_lines > 0 and len(lines) > max_lines:
            lines = lines[-max_lines:]
        return lines
    except Exception:
        return []

    return False, [], "unknown"

@route("GET", "/api/auth/me")
async def auth_me(req: web.Request):
    token = _extract_token(req)
    valid, scopes, token_type = _resolve_token_scopes(token)
    if not valid:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    doc = _find_web_token(token)
    return web.json_response({
        "ok": True,
        "user_name": doc.get("user_name") if doc else None,
        "user_id": doc.get("user_id") if doc else None,
        "user_icon": doc.get("user_icon") if doc else None,
        "scopes": scopes,
        "source": token_type,
    })

@route("GET", "/api/auth/permissions", allow_public=True)
async def auth_permissions(req: web.Request):
    token = _extract_token(req)
    if not token:
        return web.json_response({"ok": False, "error": "token required", "token_valid": False, "scopes": []})
    valid, scopes, token_type = _resolve_token_scopes(token)
    if not valid:
        return web.json_response({"ok": False, "error": "invalid token", "token_valid": False, "scopes": []})
    return web.json_response({
        "ok": True,
        "token_valid": True,
        "token_type": token_type,
        "scopes": scopes,
    })

@route("GET", "/api/auth/tokens", scopes=["bingo:admin"])
async def auth_tokens(_req: web.Request):
    tokens = []
    now = int(time.time())
    for t in web_tokens.load_tokens():
        expires = int(t.get("expires_at") or 0)
        tokens.append({
            "token": t.get("token"),
            "user_id": t.get("user_id"),
            "user_name": t.get("user_name"),
            "scopes": t.get("scopes") or [],
            "created_at": t.get("created_at"),
            "expires_at": expires,
            "expires_in": max(0, expires - now),
        })
    return web.json_response({"ok": True, "tokens": tokens})

@route("DELETE", "/api/auth/tokens/{token}", scopes=["bingo:admin"])
async def delete_auth_token(req: web.Request):
    token = req.match_info.get("token") or ""
    tokens = web_tokens.load_tokens()
    kept = [t for t in tokens if t.get("token") != token]
    if len(kept) == len(tokens):
        return web.json_response({"ok": False, "error": "not found"}, status=404)
    web_tokens.save_tokens(kept)
    return web.json_response({"ok": True})

@route("GET", "/discord/channels", scopes=["bingo:admin", "tarot:admin"])
async def discord_channels(req: web.Request):
    bot = getattr(bigtree, "bot", None)
    if not bot:
        return web.json_response({"ok": False, "error": "bot not ready"}, status=503)
    guild_id = req.query.get("guild_id")
    try:
        guild_id = int(guild_id) if guild_id else None
    except Exception:
        return web.json_response({"ok": False, "error": "guild_id must be an integer"}, status=400)
    channels = []
    for guild in bot.guilds or []:
        if guild_id and guild.id != guild_id:
            continue
        for channel in getattr(guild, "channels", []) or []:
            if not isinstance(channel, discord.TextChannel):
                continue
            category = channel.category.name if channel.category else ""
            channels.append({
                "id": str(channel.id),
                "name": channel.name,
                "guild_id": str(guild.id),
                "guild_name": guild.name,
                "category": category,
                "position": channel.position,
            })
    channels.sort(key=lambda c: (c.get("guild_name") or "", c.get("category") or "", c.get("position") or 0, c.get("name") or ""))
    return web.json_response({"ok": True, "channels": channels})

@route("GET", "/discord/roles", scopes=["bingo:admin", "tarot:admin"])
async def discord_roles(req: web.Request):
    bot = getattr(bigtree, "bot", None)
    if not bot:
        return web.json_response({"ok": False, "error": "bot not ready"}, status=503)
    guild_id = req.query.get("guild_id")
    try:
        guild_id = int(guild_id) if guild_id else None
    except Exception:
        return web.json_response({"ok": False, "error": "guild_id must be an integer"}, status=400)
    roles = []
    for guild in bot.guilds or []:
        if guild_id and guild.id != guild_id:
            continue
        for role in getattr(guild, "roles", []) or []:
            roles.append({
                "id": str(role.id),
                "name": role.name,
                "guild_id": str(guild.id),
                "guild_name": guild.name,
                "color": role.color.value if hasattr(role, "color") else 0,
                "position": role.position,
            })
    roles.sort(key=lambda r: (r.get("guild_name") or "", -(r.get("position") or 0), r.get("name") or ""))
    return web.json_response({"ok": True, "roles": roles})

def _settings_path() -> Path:
    try:
        if hasattr(bigtree, "settings") and bigtree.settings:
            return Path(getattr(bigtree.settings, "path", "") or "")
    except Exception:
        pass
    return Path(os.getenv("HOME", "")) / ".config" / "bigtree.ini"

def _update_role_ids(role_ids: list[str]) -> None:
    from configobj import ConfigObj
    path = _settings_path()
    cfg = ConfigObj(str(path), encoding="utf-8")
    cfg.setdefault("BOT", {})
    cfg["BOT"]["elfministrator_role_ids"] = [str(r) for r in role_ids]
    cfg.write()
    try:
        bigtree.settings = load_settings(path)
    except Exception:
        pass

def _normalize_role_scopes(role_scopes: Dict[str, Any]) -> Dict[str, list[str]]:
    if not isinstance(role_scopes, dict):
        return {}
    normalized: Dict[str, list[str]] = {}
    for rid, scopes in role_scopes.items():
        role_id = str(rid).strip()
        if not role_id:
            continue
        scope_list: list[str] = []
        if isinstance(scopes, str):
            val = scopes.strip()
            if val.startswith("[") or val.startswith("{"):
                try:
                    parsed = json.loads(val)
                except Exception:
                    parsed = val
                scopes = parsed
        if isinstance(scopes, (list, tuple, set)):
            scope_list = [str(s).strip() for s in scopes if str(s).strip()]
        elif isinstance(scopes, dict):
            scope_list = [str(s).strip() for s in scopes.keys() if str(s).strip()]
        elif isinstance(scopes, str):
            scope_list = [s.strip() for s in scopes.split(",") if s.strip()]
        if "*" in scope_list:
            scope_list = ["*"]
        normalized[role_id] = scope_list
    return normalized

def _auth_roles_path() -> Path | None:
    try:
        if hasattr(bigtree, "settings") and bigtree.settings:
            base = bigtree.settings.get("BOT.DATA_DIR", None)
        else:
            base = None
    except Exception:
        base = None
    base = base or getattr(bigtree, "datadir", None)
    if not base:
        return None
    return Path(base) / "auth_roles.json"

def _read_auth_roles_file() -> Dict[str, list[str]]:
    path = _auth_roles_path()
    if not path or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text("utf-8"))
    except Exception:
        return {}
    if isinstance(data, dict) and isinstance(data.get("role_scopes"), dict):
        return _normalize_role_scopes(data.get("role_scopes") or {})
    if isinstance(data, dict):
        return _normalize_role_scopes(data)
    return {}

def _write_auth_roles_file(role_scopes: Dict[str, list[str]]) -> bool:
    path = _auth_roles_path()
    if not path:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"role_scopes": role_scopes}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return True

def _update_role_scopes(role_scopes: Dict[str, list[str]]) -> None:
    from configobj import ConfigObj
    path = _settings_path()
    cfg = ConfigObj(str(path), encoding="utf-8")
    cfg.setdefault("BOT", {})
    cfg["BOT"]["auth_role_scopes"] = json.dumps(role_scopes)
    cfg.write()
    try:
        bigtree.settings = load_settings(path)
    except Exception:
        pass

@route("GET", "/api/auth/roles", scopes=["bingo:admin"])
async def auth_roles(_req: web.Request):
    role_ids = []
    try:
        if hasattr(bigtree, "settings") and bigtree.settings:
            role_ids = bigtree.settings.get("BOT.elfministrator_role_ids", [], cast="json") or []
    except Exception:
        role_ids = []
    role_scopes = {}
    role_scopes_configured = False
    try:
        if hasattr(bigtree, "settings") and bigtree.settings:
            sec = bigtree.settings.section("BOT")
            if isinstance(sec, dict) and "auth_role_scopes" in sec:
                role_scopes_configured = True
                role_scopes = sec.get("auth_role_scopes") or {}
            else:
                role_scopes = bigtree.settings.get("BOT.auth_role_scopes", {}, cast="json") or {}
    except Exception:
        role_scopes = {}
    role_scopes = _normalize_role_scopes(role_scopes)
    if not role_scopes:
        role_scopes = _read_auth_roles_file()
    if role_scopes:
        role_scopes_configured = True
    if isinstance(role_ids, (str, int)):
        role_ids = [role_ids]
    role_ids = [str(r) for r in role_ids if str(r).strip()]
    auth_logger.info("[auth] roles list role_ids=%s role_scopes=%s", role_ids, list(role_scopes.keys()))
    return web.json_response({
        "ok": True,
        "role_ids": role_ids,
        "role_scopes": role_scopes,
        "role_scopes_configured": role_scopes_configured,
    })

@route("POST", "/api/auth/roles", scopes=["bingo:admin"])
async def auth_roles_update(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        auth_logger.warning("[auth] roles update invalid json")
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)
    role_scopes = body.get("role_scopes", None)
    if role_scopes is not None:
        role_scopes = _normalize_role_scopes(role_scopes)
        role_ids = list(role_scopes.keys())
        try:
            _update_role_scopes(role_scopes)
            _update_role_ids(role_ids)
            _write_auth_roles_file(role_scopes)
        except Exception as exc:
            auth_logger.error("[auth] roles update failed err=%s", exc)
            if _write_auth_roles_file(role_scopes):
                auth_logger.info("[auth] roles update stored in auth_roles.json fallback")
                return web.json_response({"ok": True, "role_ids": role_ids, "role_scopes": role_scopes, "fallback": True})
            return web.json_response({"ok": False, "error": "save failed"}, status=500)
        auth_logger.info("[auth] roles updated scopes=%s", role_scopes)
        return web.json_response({"ok": True, "role_ids": role_ids, "role_scopes": role_scopes})
    role_ids = body.get("role_ids") or []
    if isinstance(role_ids, (str, int)):
        role_ids = [role_ids]
    role_ids = [str(r) for r in role_ids if str(r).strip()]
    _update_role_ids(role_ids)
    auth_logger.info("[auth] roles updated legacy role_ids=%s", role_ids)
    return web.json_response({"ok": True, "role_ids": role_ids})

# ---------- Send a Discord message ----------
@route("POST", "/message", scopes=["admin:message"])
async def send_message(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    channel_id = body.get("channel_id")
    content = body.get("content")
    if not channel_id or not content:
        return web.json_response({"error": "channel_id and content are required"}, status=400)

    try:
        channel_id = int(channel_id)
    except Exception:
        return web.json_response({"error": "channel_id must be an integer"}, status=400)

    chan = bigtree.bot.get_channel(channel_id)
    if not chan:
        bigtree.logger.warning(f"/message: channel {channel_id} not found or uncached")
        return web.json_response({"error": "channel not found or not cached"}, status=404)

    await chan.send(content)
    bigtree.logger.info(f"Message sent to channel {channel_id} via API")
    return web.json_response({"ok": True})

@route("GET", "/admin/system-config", scopes=["admin:web"])
async def admin_system_config(_req: web.Request):
    db = get_database()
    configs = {
        "xivauth": db.get_system_config("xivauth"),
        "openai": db.get_system_config("openai"),
        "overlay": db.get_system_config("overlay"),
    }
    return web.json_response({"ok": True, "configs": configs})


@route("POST", "/admin/system-config", scopes=["admin:web"])
async def admin_system_config_update(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    name = (body.get("name") or "").strip().lower()
    if name not in {"xivauth", "openai", "overlay"}:
        return web.json_response({"ok": False, "error": "invalid config name"}, status=400)
    data = body.get("data")
    if not isinstance(data, dict):
        data = {}
    db = get_database()
    if not db.update_system_config(name, data):
        return web.json_response({"ok": False, "error": "save failed"}, status=500)
    return web.json_response({"ok": True, "config": db.get_system_config(name)})


@route("GET", "/admin/logs", scopes=["admin:web"])
async def admin_logs(req: web.Request) -> web.Response:
    kind = (req.query.get("kind") or "boot").strip().lower()
    try:
        lines = int(req.query.get("lines") or 200)
    except Exception:
        lines = 200
    if lines < 20:
        lines = 20
    if lines > 1000:
        lines = 1000
    if kind == "auth":
        path = auth_log_path
    elif kind == "upload":
        path = upload_log_path
    else:
        kind = "boot"
        path = log_path
    entries = _read_log_tail(path, max_lines=lines)
    return web.json_response({"ok": True, "kind": kind, "lines": lines, "entries": entries})


@route("GET", "/admin/overlay/stats", scopes=["admin:web"])
async def admin_overlay_stats(_req: web.Request):
    db = get_database()
    def _count(sql):
        row = db._fetchone(sql)
        return int(row.get("value") if row and row.get("value") is not None else 0)
    try:
        guilds = (getattr(bigtree.bot, "guilds") or []) if hasattr(bigtree, "bot") else []
    except Exception:
        guilds = []
    discord_members = sum((getattr(g, "member_count", 0) or 0) for g in guilds)
    stats = {
        "discord_members": discord_members,
        "players_engaged": _count("SELECT COUNT(DISTINCT user_id) AS value FROM user_games"),
        "registered_users": _count("SELECT COUNT(*) AS value FROM users"),
        "api_games": _count("SELECT COUNT(*) AS value FROM games"),
        "venues": _count("SELECT COUNT(*) AS value FROM venues"),
    }
    return web.json_response({"ok": True, "stats": stats})


@route("GET", "/admin/discord/members", scopes=["admin:web", "event:host", "venue:host"])
async def admin_discord_members(_req: web.Request) -> web.Response:
    """List discord members for host selection in the dashboard.

    We keep the payload intentionally small and JSON-safe (join times are ISO).
    """
    members = []
    try:
        bot = getattr(bigtree, "bot", None)
        guilds = (getattr(bot, "guilds", None) or []) if bot else []
        # Prefer the first guild if multiple are connected.
        guild = guilds[0] if guilds else None
        if guild:
            # Ensure cache is populated when privileged intents are enabled.
            try:
                # Discord.py: guild.members exists if member cache is available.
                iter_members = list(getattr(guild, "members", []) or [])
            except Exception:
                iter_members = []
            for m in iter_members:
                try:
                    members.append(
                        {
                            "id": int(getattr(m, "id", 0) or 0),
                            "name": str(getattr(m, "name", "") or ""),
                            "display_name": str(getattr(m, "display_name", "") or ""),
                            "global_name": str(getattr(m, "global_name", "") or ""),
                            "joined_at": getattr(m, "joined_at", None),
                            "bot": bool(getattr(m, "bot", False)),
                        }
                    )
                except Exception:
                    continue
    except Exception:
        members = []

    # Merge stored users so hosts appear even if guild cache is missing.
    try:
        stored = get_database().list_discord_users(limit=5000)
    except Exception:
        stored = []
    merged: Dict[int, Dict[str, Any]] = {}
    for m in members:
        try:
            merged[int(m.get("id") or 0)] = dict(m)
        except Exception:
            continue
    for row in stored or []:
        try:
            did = int(row.get("discord_id") or 0)
        except Exception:
            continue
        if not did:
            continue
        if did in merged:
            entry = merged[did]
            entry["name"] = entry.get("name") or row.get("name") or ""
            entry["display_name"] = entry.get("display_name") or row.get("display_name") or ""
            entry["global_name"] = entry.get("global_name") or row.get("global_name") or ""
        else:
            merged[did] = {
                "id": did,
                "name": row.get("name") or "",
                "display_name": row.get("display_name") or "",
                "global_name": row.get("global_name") or "",
                "joined_at": row.get("updated_at"),
                "bot": False,
            }
    members = list(merged.values())
    # Sort by display name for convenient selection.
    members.sort(key=lambda x: (str(x.get("display_name") or x.get("name") or "").lower(), int(x.get("id") or 0)))
    return web.json_response({"ok": True, "members": to_jsonable(members)})


@route("GET", "/admin/games/list", scopes=["admin:web"])
async def admin_games_list(req: web.Request) -> web.Response:
    """Paginated game listing for the forest dashboard (all modules)."""
    db = get_database()
    q = (req.query.get("q") or "").strip() or None
    module = (req.query.get("module") or "").strip() or None
    player = (req.query.get("player") or "").strip() or None
    try:
        venue_id = int(req.query.get("venue_id") or 0)
    except Exception:
        venue_id = 0
    include_inactive = (req.query.get("include_inactive") or "1").strip() not in {"0", "false", "no"}
    try:
        page = int(req.query.get("page") or 1)
    except Exception:
        page = 1
    try:
        page_size = int(req.query.get("page_size") or 50)
    except Exception:
        page_size = 50

    result = db.list_games(
        q=q,
        module=module,
        player=player,
        venue_id=venue_id or None,
        include_inactive=include_inactive,
        page=page,
        page_size=page_size,
    )
    return web.json_response({"ok": True, **result})

# ---------- FFXIV client announce ----------
@route("POST", "/admin/announce", scopes=["admin:announce"])
async def admin_announce(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    client_id = str(body.get("client_id") or "").strip()
    if not client_id:
        return web.json_response({"ok": False, "error": "client_id required"}, status=400)

    ip = req.headers.get("X-Forwarded-For") or req.remote
    ua = req.headers.get("User-Agent", "")
    now_ms = int(time.time() * 1000)

    doc = {
        "client_id": client_id,
        "app": str(body.get("app") or "unknown"),
        "version": str(body.get("version") or ""),
        "character": str(body.get("character") or ""),
        "world": str(body.get("world") or ""),
        "region": str(body.get("region") or ""),
        "extra": body.get("extra") or {},
        "ip": ip,
        "user_agent": ua,
        "ts": now_ms,
        "last_seen": now_ms,
    }

    db = _admin_db()
    q = Query()
    existing = db.get(q.client_id == client_id)
    if existing:
        doc["ts"] = existing.get("ts") or now_ms
        db.update(doc, q.client_id == client_id)
    else:
        db.insert(doc)

    bigtree.logger.info(
        "[announce] client_id=%s app=%s ver=%s char=%s world=%s ip=%s",
        client_id, doc["app"], doc["version"], doc["character"], doc["world"], ip
    )
    return web.json_response({"ok": True, "client_id": client_id})


@route("POST", "/admin/update_with_leaf", scopes=["bingo:admin"])
async def update_with_leaf(req: web.Request):
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://raw.githubusercontent.com/dorbian/forest_repo/main/plogonmaster.json") as resp:
                if resp.status != 200:
                    return web.json_response({"ok": False, "error": f"Failed to fetch: {resp.status}"}, status=400)
                content = await resp.text()
        path = get_with_leaf_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return web.json_response({"ok": True, "message": "Updated with.leaf"})
    except Exception as ex:
        return web.json_response({"ok": False, "error": str(ex)}, status=500)
