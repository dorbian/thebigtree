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
from bigtree.inc.auth import TOKEN_COOKIE_NAME
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
    token = req.headers.get("X-Bigtree-Key") or req.headers.get("X-API-Key") or ""
    if token:
        return token
    return (req.cookies.get(TOKEN_COOKIE_NAME) if req.cookies else None) or ""

def _find_web_token(token: str) -> Dict[str, Any]:
    if not token:
        return {}
    doc = web_tokens.find_token(token)
    return doc or {}

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
    return False, [], "unknown"


def _admin_venue_scopes() -> list[str]:
    return ["admin:web", "bingo:admin", "tarot:admin", "cardgames:admin", "event:host"]


def _read_log_tail(path: str, max_lines: int = 200, max_bytes: int = 200_000) -> list[str]:
    """
    Read the tail of a log file efficiently.
    
    Args:
        path: Path to log file
        max_lines: Maximum number of lines to return (0 = no limit)
        max_bytes: Maximum bytes to read from file end
    
    Returns:
        List of log lines, or empty list if file not found/readable
    """
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
    except (OSError, IOError) as e:
        logger.warning("[admin] failed to read log file %s: %s", path, e)
        return []
    except UnicodeDecodeError as e:
        logger.error("[admin] log file encoding error %s: %s", path, e)
        return []

@route("GET", "/api/auth/me")
async def auth_me(req: web.Request):
    token = _extract_token(req)
    valid, scopes, token_type = _resolve_token_scopes(token)
    if not valid:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    doc = _find_web_token(token)
    venue = None
    try:
        db = get_database()
        raw_id = None
        if doc:
            meta = doc.get("metadata") or {}
            raw_id = meta.get("discord_id") or doc.get("user_id")
        if raw_id is not None:
            venue = db.get_discord_venue(int(raw_id))
    except Exception:
        venue = None
    if venue:
        venue = to_jsonable(venue)
    return web.json_response({
        "ok": True,
        "user_name": doc.get("user_name") if doc else None,
        "user_id": doc.get("user_id") if doc else None,
        "user_icon": doc.get("user_icon") if doc else None,
        "venue": venue,
        "scopes": scopes,
        "source": token_type,
    })


@route("GET", "/admin/venues/list", scopes=_admin_venue_scopes())
async def admin_venues_list_scoped(_req: web.Request) -> web.Response:
    db = get_database()
    return web.json_response({"ok": True, "venues": db.list_venues()})


@route("GET", "/admin/venue/me", scopes=_admin_venue_scopes())
async def admin_venue_me(req: web.Request) -> web.Response:
    token = _extract_token(req)
    doc = _find_web_token(token)
    if not doc:
        return web.json_response({"ok": False, "error": "user_id required"}, status=400)
    raw_id = None
    meta = doc.get("metadata") or {}
    raw_id = meta.get("discord_id") or doc.get("user_id")
    if not raw_id:
        return web.json_response({"ok": False, "error": "user_id required"}, status=400)
    db = get_database()
    membership = db.get_discord_venue(int(raw_id))
    if not membership:
        try:
            venue_id = db._find_venue_for_discord_admin(int(raw_id))
        except Exception:
            venue_id = None
        if venue_id:
            venue = db.get_venue(int(venue_id))
            if venue:
                membership = {
                    "venue_id": int(venue.get("id")),
                    "role": "admin",
                    "membership_metadata": None,
                    "id": int(venue.get("id")),
                    "name": venue.get("name"),
                    "currency_name": venue.get("currency_name"),
                    "minimal_spend": venue.get("minimal_spend"),
                    "background_image": venue.get("background_image"),
                    "deck_id": venue.get("deck_id"),
                    "metadata": venue.get("metadata"),
                    "created_at": venue.get("created_at"),
                    "updated_at": venue.get("updated_at"),
                }
    if membership:
        membership = to_jsonable(membership)
    return web.json_response({"ok": True, "membership": membership})


@route("POST", "/admin/venue/assign", scopes=_admin_venue_scopes())
async def admin_venue_assign(req: web.Request) -> web.Response:
    token = _extract_token(req)
    doc = _find_web_token(token)
    if not doc:
        return web.json_response({"ok": False, "error": "user_id required"}, status=400)
    meta = doc.get("metadata") or {}
    raw_id = meta.get("discord_id") or doc.get("user_id")
    if not raw_id:
        return web.json_response({"ok": False, "error": "user_id required"}, status=400)
    try:
        body = await req.json()
    except Exception:
        body = {}
    try:
        venue_id = int(body.get("venue_id") or 0)
    except Exception:
        venue_id = 0
    if not venue_id:
        return web.json_response({"ok": False, "error": "venue_id required"}, status=400)
    db = get_database()
    venue = db.get_venue(venue_id)
    if not venue:
        return web.json_response({"ok": False, "error": "venue not found"}, status=404)
    db.set_discord_venue(int(raw_id), venue_id, role="admin")
    membership = db.get_discord_venue(int(raw_id))
    if membership:
        membership = to_jsonable(membership)
    return web.json_response({"ok": True, "membership": membership})


@route("POST", "/admin/venues/create", scopes=_admin_venue_scopes())
async def admin_venues_create(req: web.Request) -> web.Response:
    token = _extract_token(req)
    doc = _find_web_token(token)
    if not doc or not doc.get("user_id"):
        return web.json_response({"ok": False, "error": "user_id required"}, status=400)
    try:
        body = await req.json()
    except Exception:
        body = {}
    name = str(body.get("name") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "name required"}, status=400)
    db = get_database()
    metadata = {"admin_discord_ids": [str(doc.get("user_id"))]}
    venue = db.upsert_venue(name, metadata=metadata)
    if not venue:
        return web.json_response({"ok": False, "error": "save failed"}, status=500)
    db.set_discord_venue(int(doc.get("user_id")), int(venue.get("id")), role="admin")
    membership = db.get_discord_venue(int(doc.get("user_id")))
    if membership:
        membership = to_jsonable(membership)
    return web.json_response({"ok": True, "venue": venue, "membership": membership})

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

@route("POST", "/discord/channels", scopes=["bingo:admin", "tarot:admin"])
async def discord_create_channel(req: web.Request) -> web.Response:
    """Create a text channel. Only available to admins via API key auth (not Pegas)."""
    # Gate: require API key auth, reject Pegas auth (Pegas is read-only identity)
    from bigtree.inc.auth import _extract_token, _cfg
    token = _extract_token(req)
    cfg = _cfg()
    if not token or token not in cfg.api_keys:
        return web.json_response({"ok": False, "error": "admin API key required"}, status=401)

    bot = getattr(bigtree, "bot", None)
    if not bot:
        return web.json_response({"ok": False, "error": "bot not ready"}, status=503)

    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)

    name = str(body.get("name", "")).strip()
    category_id = body.get("category_id")
    guild_id = body.get("guild_id")

    if not name:
        return web.json_response({"ok": False, "error": "name required"}, status=400)
    if len(name) > 100:
        return web.json_response({"ok": False, "error": "name too long (max 100)"}, status=400)
    # disallow @everyone mention in name
    if "@everyone" in name or "@here" in name:
        return web.json_response({"ok": False, "error": "invalid channel name"}, status=400)

    guild = None
    for g in bot.guilds or []:
        if str(g.id) == str(guild_id):
            guild = g
            break
    if not guild:
        return web.json_response({"ok": False, "error": "guild not found"}, status=404)

    overwrites = []
    try:
        category = None
        if category_id:
            cat_id_str = str(category_id)
            for c in guild.categories:
                if str(c.id) == cat_id_str:
                    category = c
                    break

        new_channel = await guild.create_text_channel(
            name=name,
            category=category,
        )
        return web.json_response({
            "ok": True,
            "channel": {
                "id": str(new_channel.id),
                "name": new_channel.name,
                "guild_id": str(guild.id),
                "category": category.name if category else "",
            }
        })
    except discord.Forbidden:
        return web.json_response({"ok": False, "error": "bot lacks permission to create channels"}, status=403)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

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

@route("POST", "/discord/roles", scopes=["bingo:admin", "tarot:admin"])
async def discord_create_role(req: web.Request) -> web.Response:
    """Create a role in a guild. Requires admin API key auth."""
    from bigtree.inc.auth import _extract_token, _cfg
    token = _extract_token(req)
    cfg = _cfg()
    if not token or token not in cfg.api_keys:
        return web.json_response({"ok": False, "error": "admin API key required"}, status=401)

    bot = getattr(bigtree, "bot", None)
    if not bot:
        return web.json_response({"ok": False, "error": "bot not ready"}, status=503)

    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)

    name = str(body.get("name", "")).strip()
    guild_id = body.get("guild_id")
    color_hex = body.get("color")  # "#08e201" or "08e201"
    hoist = bool(body.get("hoist", False))  # show separately in online list

    if not name:
        return web.json_response({"ok": False, "error": "name required"}, status=400)
    if len(name) > 100:
        return web.json_response({"ok": False, "error": "name too long (max 100)"}, status=400)

    guild = None
    for g in bot.guilds or []:
        if str(g.id) == str(guild_id):
            guild = g
            break
    if not guild:
        return web.json_response({"ok": False, "error": "guild not found"}, status=404)

    try:
        color_value = 0
        if color_hex:
            hex_str = color_hex.lstrip("#")
            color_value = int(hex_str, 16)
            color = discord.Color(color_value)
        else:
            color = discord.Color.default()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid color"}, status=400)

    try:
        new_role = await guild.create_role(
            name=name,
            color=color,
            hoist=hoist,
        )
        return web.json_response({
            "ok": True,
            "role": {
                "id": str(new_role.id),
                "name": new_role.name,
                "guild_id": str(guild.id),
                "color": new_role.color.value if hasattr(new_role, "color") else 0,
                "position": new_role.position,
                "hoist": new_role.hoist,
            }
        })
    except discord.Forbidden:
        return web.json_response({"ok": False, "error": "bot lacks permission to create roles"}, status=403)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

@route("PATCH", "/discord/roles/{role_id}", scopes=["bingo:admin", "tarot:admin"])
async def discord_update_role(req: web.Request) -> web.Response:
    """Update a role's color and/or name."""
    from bigtree.inc.auth import _extract_token, _cfg
    token = _extract_token(req)
    cfg = _cfg()
    if not token or token not in cfg.api_keys:
        return web.json_response({"ok": False, "error": "admin API key required"}, status=401)

    bot = getattr(bigtree, "bot", None)
    if not bot:
        return web.json_response({"ok": False, "error": "bot not ready"}, status=503)

    role_id = req.match_info.get("role_id")
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)

    guild_id = body.get("guild_id")
    if not guild_id:
        return web.json_response({"ok": False, "error": "guild_id required"}, status=400)

    guild = None
    for g in bot.guilds or []:
        if str(g.id) == str(guild_id):
            guild = g
            break
    if not guild:
        return web.json_response({"ok": False, "error": "guild not found"}, status=404)

    role = next((r for r in getattr(guild, "roles", []) or [] if str(r.id) == str(role_id)), None)
    if not role:
        return web.json_response({"ok": False, "error": "role not found"}, status=404)

    try:
        kwargs = {}
        if "name" in body:
            kwargs["name"] = str(body["name"]).strip()
        if "color" in body:
            hex_str = str(body["color"]).lstrip("#")
            kwargs["color"] = discord.Color(int(hex_str, 16))
        if kwargs:
            await role.edit(**kwargs)
        return web.json_response({
            "ok": True,
            "role": {
                "id": str(role.id),
                "name": role.name,
                "guild_id": str(guild.id),
                "color": role.color.value if hasattr(role, "color") else 0,
                "position": role.position,
            }
        })
    except discord.Forbidden:
        return web.json_response({"ok": False, "error": "bot lacks permission"}, status=403)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)

@route("POST", "/discord/roles/reorder", scopes=["bingo:admin", "tarot:admin"])
async def discord_reorder_roles(req: web.Request) -> web.Response:
    """
    Reorder roles by passing a list of role IDs in desired position order (highest first).
    Discord role positions are relative — roles are moved to just above the previous role in the list.
    Pass a single role ID to move it to the top of its category.
    """
    from bigtree.inc.auth import _extract_token, _cfg
    token = _extract_token(req)
    cfg = _cfg()
    if not token or token not in cfg.api_keys:
        return web.json_response({"ok": False, "error": "admin API key required"}, status=401)

    bot = getattr(bigtree, "bot", None)
    if not bot:
        return web.json_response({"ok": False, "error": "bot not ready"}, status=503)

    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)

    role_ids = body.get("role_ids", [])
    guild_id = body.get("guild_id")
    if not role_ids:
        return web.json_response({"ok": False, "error": "role_ids required"}, status=400)
    if not guild_id:
        return web.json_response({"ok": False, "error": "guild_id required"}, status=400)

    guild = None
    for g in bot.guilds or []:
        if str(g.id) == str(guild_id):
            guild = g
            break
    if not guild:
        return web.json_response({"ok": False, "error": "guild not found"}, status=404)

    role_map = {str(r.id): r for r in getattr(guild, "roles", []) or []}

    # Position the first role at the very top, then chain each subsequent role just above the previous
    try:
        for i in range(len(role_ids) - 1, -1, -1):
            rid = role_ids[i]
            role = role_map.get(str(rid))
            if not role:
                return web.json_response({"ok": False, "error": f"role {rid} not found in guild"}, status=404)
            if i == len(role_ids) - 1:
                target_pos = 7  # bottom role: just above MovieNights
            else:
                prev_role = role_map.get(str(role_ids[i + 1]))
                target_pos = prev_role.position + 1
            await role.edit(position=target_pos)
        return web.json_response({"ok": True, "reordered": role_ids})
    except discord.Forbidden:
        return web.json_response({"ok": False, "error": "bot lacks permission to manage roles"}, status=403)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


@route("POST", "/gpose/leaderboard", scopes=["bingo:admin", "tarot:admin"])
async def gpose_leaderboard_update(req: web.Request) -> web.Response:
    """Trigger a leaderboard refresh — fetches treeheart counts and updates the leaderboard message."""
    from bigtree.inc.auth import _extract_token, _cfg
    token = _extract_token(req)
    cfg = _cfg()
    if not token or token not in cfg.api_keys:
        return web.json_response({"ok": False, "error": "admin API key required"}, status=401)

    bot = getattr(bigtree, "bot", None)
    if not bot:
        return web.json_response({"ok": False, "error": "bot not ready"}, status=503)

    try:
        from bigtree.modules.gpose_leaderboard import run_leaderboard_check
        result = await run_leaderboard_check(bot)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


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

    role_scopes: Dict[str, list[str]] = {}
    role_scopes_configured = False

    # Source of truth: Postgres
    try:
        db = get_database()
        role_scopes = db.get_auth_roles() or {}
        role_scopes = _normalize_role_scopes(role_scopes)
        if role_scopes:
            role_scopes_configured = True
    except Exception:
        role_scopes = {}

    # Fallback: config value, then legacy file
    if not role_scopes:
        try:
            if hasattr(bigtree, "settings") and bigtree.settings:
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
    return web.json_response(
        {
            "ok": True,
            "role_ids": role_ids,
            "role_scopes": role_scopes,
            "role_scopes_configured": role_scopes_configured,
        }
    )

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

        # Persist to Postgres (source of truth)
        try:
            db = get_database()
            db.update_auth_roles(role_scopes)
        except Exception as exc:
            auth_logger.error("[auth] roles update failed (db) err=%s", exc)
            # Fallback: store in legacy file so UI keeps working
            if _write_auth_roles_file(role_scopes):
                auth_logger.info("[auth] roles update stored in auth_roles.json fallback")
                return web.json_response({"ok": True, "role_ids": role_ids, "role_scopes": role_scopes, "fallback": True})
            return web.json_response({"ok": False, "error": "save failed"}, status=500)

        # Optional: keep config file in sync for backwards compatibility
        try:
            _update_role_scopes(role_scopes)
            _update_role_ids(role_ids)
        except Exception:
            pass

        # Legacy file is now optional, but we still write it to help upgrades
        try:
            _write_auth_roles_file(role_scopes)
        except Exception:
            pass

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


@route("GET", "/admin/discord-users", scopes=["admin:web"])
@route("GET", "/admin/gpose/status")
async def gpose_status(req: web.Request):
    """Get current G-Pose contest state."""
    try:
        from bigtree.modules.gpose_contest import get_current_week, get_submissions, get_state
        state = get_state()
        week = get_current_week()
        submissions = get_submissions()
        return web.json_response({
            "ok": True,
            "has_active_contest": week is not None,
            "current_week": week.to_dict() if week else None,
            "submission_count": len(submissions),
            "state": state,
        })
    except ImportError:
        return web.json_response({"ok": False, "error": "gpose_contest module not found"}, status=500)


@route("GET", "/admin/gpose/config")
async def gpose_config(req: web.Request):
    """Get G-Pose contest configuration (role IDs, channel IDs)."""
    try:
        from bigtree.modules.gpose_contest import get_config
        cfg = get_config()
        return web.json_response({"ok": True, "config": cfg})
    except ImportError:
        return web.json_response({"ok": False, "error": "gpose_contest module not found"}, status=500)


@route("POST", "/admin/gpose/config")
async def gpose_config_update(req: web.Request):
    """Update G-Pose contest configuration."""
    try:
        from bigtree.modules.gpose_contest import set_config, get_config
        body = await req.json()
        allowed_keys = {
            "weekly_role_id", "monthly_role_id", "yearly_role_id",
            "submitter_role_id", "submissions_channel_id",
            "announcements_channel_id", "posers_hall_channel_id",
            "planning_channel_id", "voting_emoji",
        }
        updates = {k: v for k, v in body.items() if k in allowed_keys}
        # Convert string IDs to int
        int_fields = {"weekly_role_id", "monthly_role_id", "yearly_role_id",
                      "submitter_role_id", "submissions_channel_id",
                      "announcements_channel_id", "posers_hall_channel_id",
                      "planning_channel_id"}
        for k in int_fields:
            if k in updates:
                try:
                    updates[k] = int(updates[k])
                except (ValueError, TypeError):
                    updates[k] = None
        result = set_config(**updates)
        return web.json_response({"ok": True, "config": result})
    except ImportError:
        return web.json_response({"ok": False, "error": "gpose_contest module not found"}, status=500)


@route("POST", "/admin/gpose/start")
async def gpose_start(req: web.Request):
    """Start a new G-Pose contest week."""
    try:
        from bigtree.modules.gpose_contest import start_contest, get_current_week
        if get_current_week() is not None:
            return web.json_response({"ok": False, "error": "A contest is already in progress"}, status=409)
        body = await req.json()
        theme = (body.get("theme") or "Open").strip()
        if not theme:
            return web.json_response({"ok": False, "error": "theme is required"}, status=400)
        duration_days = float(body.get("duration_days", 7.0))
        week = body.get("week")
        month = body.get("month")
        year = body.get("year")
        result = start_contest(
            theme=theme,
            week=int(week) if week else None,
            month=int(month) if month else None,
            year=int(year) if year else None,
            duration_days=duration_days,
        )
        return web.json_response(result)
    except ImportError:
        return web.json_response({"ok": False, "error": "gpose_contest module not found"}, status=500)


@route("POST", "/admin/gpose/submit")
async def gpose_submit(req: web.Request):
    """Record a G-Pose submission for the current contest."""
    try:
        from bigtree.modules.gpose_contest import submit_entry
        body = await req.json()
        message_id = str(body.get("message_id") or "").strip()
        user_id = body.get("user_id")
        user_name = (body.get("user_name") or "unknown").strip()
        if not message_id:
            return web.json_response({"ok": False, "error": "message_id is required"}, status=400)
        if not user_id:
            return web.json_response({"ok": False, "error": "user_id is required"}, status=400)
        result = submit_entry(message_id, int(user_id), user_name)
        return web.json_response(result)
    except ImportError:
        return web.json_response({"ok": False, "error": "gpose_contest module not found"}, status=500)


@route("POST", "/admin/gpose/end")
async def gpose_end(req: web.Request):
    """End the current G-Pose contest (move to voting or close)."""
    try:
        from bigtree.modules.gpose_contest import end_contest
        body = await req.json()
        winner_user_id = body.get("winner_user_id")
        winner_message_id = body.get("winner_message_id")
        result = end_contest(
            winner_user_id=int(winner_user_id) if winner_user_id else None,
            winner_message_id=str(winner_message_id) if winner_message_id else None,
        )
        return web.json_response(result)
    except ImportError:
        return web.json_response({"ok": False, "error": "gpose_contest module not found"}, status=500)


@route("POST", "/admin/gpose/winner")
async def gpose_set_winner(req: web.Request):
    """Set the winner for a contest in voting state."""
    try:
        from bigtree.modules.gpose_contest import set_winner
        body = await req.json()
        user_id = body.get("user_id")
        message_id = str(body.get("message_id") or "").strip()
        if not user_id:
            return web.json_response({"ok": False, "error": "user_id is required"}, status=400)
        result = set_winner(int(user_id), message_id)
        return web.json_response(result)
    except ImportError:
        return web.json_response({"ok": False, "error": "gpose_contest module not found"}, status=500)


@route("GET", "/admin/gpose/leaderboard")
async def gpose_leaderboard(req: web.Request):
    """Get weekly, monthly, and yearly winners."""
    try:
        from bigtree.modules.gpose_contest import get_leaderboard
        limit = int(req.query.get("limit") or 50)
        result = get_leaderboard(limit=limit)
        return web.json_response({"ok": True, **result})
    except ImportError:
        return web.json_response({"ok": False, "error": "gpose_contest module not found"}, status=500)


@route("GET", "/admin/gpose/submissions")
async def gpose_submissions(req: web.Request):
    """Get current contest submissions (for voting)."""
    try:
        from bigtree.modules.gpose_contest import get_submissions, get_current_week
        week = get_current_week()
        submissions = get_submissions()
        return web.json_response({
            "ok": True,
            "submissions": submissions,
            "count": len(submissions),
            "week": week.to_dict() if week else None,
        })
    except ImportError:
        return web.json_response({"ok": False, "error": "gpose_contest module not found"}, status=500)


@route("POST", "/admin/gpose/grant-role")
async def gpose_grant_role(req: web.Request):
    """
    Grant or revoke a Discord role to a user.
    Request body: { "user_id": int, "role_id": int, "action": "add" | "remove" }
    """
    body = await req.json()
    user_id = body.get("user_id")
    role_id = body.get("role_id")
    action = (body.get("action") or "add").strip().lower()

    if not user_id or not role_id:
        return web.json_response({"ok": False, "error": "user_id and role_id are required"}, status=400)
    if action not in ("add", "remove"):
        return web.json_response({"ok": False, "error": "action must be 'add' or 'remove'"}, status=400)

    bot = getattr(bigtree, "bot", None)
    if not bot:
        return web.json_response({"ok": False, "error": "bot not ready"}, status=503)

    guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        return web.json_response({"ok": False, "error": "no guild found"}, status=500)

    member = guild.get_member(int(user_id))
    if not member:
        return web.json_response({"ok": False, "error": "member not found in guild"}, status=404)

    role = guild.get_role(int(role_id))
    if not role:
        return web.json_response({"ok": False, "error": "role not found"}, status=404)

    try:
        if action == "add":
            await member.add_roles(role, reason="G-Pose contest award")
        else:
            await member.remove_roles(role, reason="G-Pose contest cleanup")
        return web.json_response({
            "ok": True,
            "action": action,
            "user_id": int(user_id),
            "role_id": int(role_id),
            "role_name": role.name,
        })
    except Exception as e:
        bigtree.logger.warning(f"[gpose] grant_role failed: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


@route("POST", "/admin/gpose/reset", scopes=["admin:web"])
async def gpose_reset(req: web.Request):
    """Reset all G-Pose contest state. Admin only."""
    try:
        from bigtree.modules.gpose_contest import reset_state
        result = reset_state()
        return web.json_response(result)
    except ImportError:
        return web.json_response({"ok": False, "error": "gpose_contest module not found"}, status=500)


@route("POST", "/admin/gpose/message")
async def gpose_send_message(req: web.Request):
    """
    Send a G-Pose contest announcement message via the bot.
    Uses the configured announcements_channel_id unless overridden.
    Request body: { "content": str, "channel_id"?: int }
    """
    try:
        from bigtree.modules.gpose_contest import get_config
    except ImportError:
        return web.json_response({"ok": False, "error": "gpose_contest module not found"}, status=500)

    body = await req.json()
    content = (body.get("content") or "").strip()
    if not content:
        return web.json_response({"ok": False, "error": "content is required"}, status=400)

    bot = getattr(bigtree, "bot", None)
    if not bot:
        return web.json_response({"ok": False, "error": "bot not ready"}, status=503)

    channel_id = body.get("channel_id")
    if not channel_id:
        cfg = get_config()
        channel_id = cfg.get("announcements_channel_id")

    if not channel_id:
        return web.json_response({"ok": False, "error": "channel_id not configured"}, status=400)

    try:
        channel_id = int(channel_id)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "invalid channel_id"}, status=400)

    chan = bot.get_channel(channel_id)
    if not chan:
        return web.json_response({"ok": False, "error": "channel not found or not cached"}, status=404)

    try:
        msg = await chan.send(content)
        return web.json_response({"ok": True, "message_id": str(msg.id), "channel_id": channel_id})
    except Exception as e:
        bigtree.logger.warning(f"[gpose] message send failed: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


@route("GET", "/admin/gpose/monthly-candidates")
async def gpose_monthly_candidates(req: web.Request):
    """
    Get the 4 weekly winners for a given month — used to kick off monthly vote.
    Query params: year, month
    """
    try:
        from bigtree.modules.gpose_contest import get_weekly_winners_for_month
    except ImportError:
        return web.json_response({"ok": False, "error": "gpose_contest module not found"}, status=500)

    try:
        year = int(req.query.get("year") or datetime.now().year)
        month = int(req.query.get("month") or datetime.now().month)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "invalid year/month"}, status=400)

    winners = get_weekly_winners_for_month(year, month)
    return web.json_response({
        "ok": True,
        "year": year,
        "month": month,
        "weekly_winners": winners,
        "ready_for_monthly": len(winners) >= 4,
    })


async def admin_list_discord_users(_req: web.Request):
    """List all Discord users that have ever used /auth (or were observed) for use in UI pickers."""
    db = get_database()
    users = db.list_discord_users(limit=5000)
    return web.json_response({"ok": True, "users": users})


# ---- Pegas HMAC auth registration ----

@route("POST", "/admin/pegas/register", allow_public=True)
async def pegas_register(req: web.Request):
    """
    Register Pegas as an authenticated client with a shared HMAC secret.
    Only Dorbian (sender_id 212401699531390977) can register.
    
    Request body:
      { "secret": "<shared_secret>", "identity": "pegas" }
    
    The secret is stored in bigtree config (BOT.PEGAS_SHARED_SECRET).
    Future requests must include X-Pegas-Signature, X-Pegas-Timestamp, X-Pegas-Identity headers.
    """
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)

    secret = (body.get("secret") or "").strip()
    identity = (body.get("identity") or "pegas").strip()
    sender_id = body.get("sender_id", 212401699531390977)

    if not secret or len(secret) < 16:
        return web.json_response(
            {"ok": False, "error": "secret must be at least 16 characters"}, status=400
        )

    if not identity:
        return web.json_response({"ok": False, "error": "identity is required"}, status=400)

    # Verify sender is Dorbian (sender_id check from inbound metadata)
    inbound_sender = req.headers.get("X-Inbound-Sender-Id", "")
    if inbound_sender and inbound_sender != "212401699531390977":
        return web.json_response({"ok": False, "error": "Only Dorbian can register Pegas"}, status=403)

    from bigtree.inc.pegas_auth import store_secret
    ok = store_secret(secret, int(sender_id), identity)
    if not ok:
        return web.json_response({"ok": False, "error": "Failed to store secret"}, status=500)

    return web.json_response({
        "ok": True,
        "message": "Pegas registered successfully",
        "identity": identity,
        "hint": "Include X-Pegas-Signature, X-Pegas-Timestamp, X-Pegas-Identity headers on all future requests",
    })


@route("GET", "/admin/pegas/status", scopes=["admin:web"])
async def pegas_status(req: web.Request):
    """Check if Pegas auth is configured."""
    from bigtree.inc.pegas_auth import get_secret, get_identity, get_sender_id
    secret = get_secret()
    return web.json_response({
        "ok": True,
        "configured": secret is not None,
        "identity": get_identity(),
        "sender_id": get_sender_id(),
        "hint": "POST /admin/pegas/register to configure" if not secret else "Ready",
    })


@route("DELETE", "/admin/pegas/clear", scopes=["admin:web"])
async def pegas_clear(req: web.Request):
    """Remove the Pegas shared secret (logout Pegas)."""
    from bigtree.inc.pegas_auth import clear_secret
    clear_secret()
    return web.json_response({"ok": True, "message": "Pegas secret cleared"})


# ---- Discord message search ----

@route("GET", "/discord/channels/{channel_id}/messages", scopes=["discord:read", "bingo:admin"])
async def discord_channel_messages(req: web.Request) -> web.Response:
    """
    Fetch message history from a specific channel.
    
    Query params:
      limit: max messages to return (default 50, max 200)
      before: message ID to fetch before (for pagination)
      after: message ID to fetch after
    """
    bot = getattr(bigtree, "bot", None)
    if not bot:
        return web.json_response({"ok": False, "error": "bot not ready"}, status=503)

    channel_id_str = req.match_info.get("channel_id", "")
    try:
        channel_id = int(channel_id_str)
    except Exception:
        return web.json_response({"ok": False, "error": "channel_id must be an integer"}, status=400)

    try:
        limit = min(200, max(1, int(req.query.get("limit", 50))))
    except Exception:
        limit = 50

    before_id = req.query.get("before")
    after_id = req.query.get("after")

    chan = bot.get_channel(channel_id)
    if not chan:
        return web.json_response({"ok": False, "error": "channel not found"}, status=404)

    if not hasattr(chan, "history"):
        return web.json_response({"ok": False, "error": "channel type does not support history"}, status=400)

    try:
        messages = []
        after_obj = discord.Object(after_id) if after_id else None
        before_obj = discord.Object(before_id) if before_id else None

        history_iter = chan.history(limit=limit, before=before_obj, after=after_obj)
        async for msg in history_iter:
            messages.append({
                "id": str(msg.id),
                "author_id": str(msg.author.id),
                "author_name": msg.author.display_name,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat(),
                "channel_id": str(channel_id),
                "guild_id": str(msg.guild.id) if msg.guild else None,
                "attachments": [a.url for a in msg.attachments],
                "embeds": [e.to_dict() for e in msg.embeds],
                "jump_url": msg.jump_url,
            })
        return web.json_response({"ok": True, "messages": messages, "count": len(messages)})
    except Exception as e:
        bigtree.logger.warning(f"[discord] message history failed: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


@route("GET", "/discord/search", scopes=["discord:search", "bingo:admin"])
async def discord_search(req: web.Request) -> web.Response:
    """
    Search messages across channels.
    
    Query params:
      q: search query (required)
      channel_id: limit to specific channel (optional)
      user_id: filter by author (optional)
      limit: max results (default 50)
    """
    bot = getattr(bigtree, "bot", None)
    if not bot:
        return web.json_response({"ok": False, "error": "bot not ready"}, status=503)

    query = (req.query.get("q") or "").strip()
    if not query:
        return web.json_response({"ok": False, "error": "q (search query) is required"}, status=400)

    channel_id = req.query.get("channel_id")
    user_id = req.query.get("user_id")
    try:
        limit = min(200, max(1, int(req.query.get("limit", 50))))
    except Exception:
        limit = 50

    results = []

    # Determine which channels to search
    guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        return web.json_response({"ok": False, "error": "no guild found"}, status=500)

    target_channels = []
    if channel_id:
        try:
            ch = bot.get_channel(int(channel_id))
            if ch:
                target_channels = [ch]
        except Exception:
            pass
    else:
        for ch in guild.channels or []:
            if hasattr(ch, "history"):
                target_channels.append(ch)

    for chan in target_channels:
        try:
            # Search last N messages in channel
            count = 0
            async for msg in chan.history(limit=500):
                if count >= limit:
                    break
                # Filter by query
                if query.lower() not in msg.content.lower():
                    continue
                # Filter by user
                if user_id and str(msg.author.id) != str(user_id):
                    continue
                results.append({
                    "id": str(msg.id),
                    "author_id": str(msg.author.id),
                    "author_name": msg.author.display_name,
                    "content": msg.content[:500],  # truncate long messages
                    "timestamp": msg.created_at.isoformat(),
                    "channel_id": str(chan.id),
                    "channel_name": chan.name,
                    "jump_url": msg.jump_url,
                })
                count += 1
                if len(results) >= limit:
                    break
        except Exception as e:
            bigtree.logger.warning(f"[discord] search channel {chan.id} failed: {e}")
            continue

    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return web.json_response({"ok": True, "results": results, "count": len(results), "query": query})


@route("GET", "/discord/users/{user_id}/messages", scopes=["discord:search", "bingo:admin"])
async def discord_user_messages(req: web.Request) -> web.Response:
    """
    Get recent messages by a specific user across all accessible channels.
    
    Query params:
      limit: max messages per channel (default 20, max 100)
      channel_id: limit to specific channel (optional)
    """
    bot = getattr(bigtree, "bot", None)
    if not bot:
        return web.json_response({"ok": False, "error": "bot not ready"}, status=503)

    user_id_str = req.match_info.get("user_id", "")
    try:
        user_id = int(user_id_str)
    except Exception:
        return web.json_response({"ok": False, "error": "user_id must be an integer"}, status=400)

    try:
        limit = min(100, max(1, int(req.query.get("limit", 20))))
    except Exception:
        limit = 20

    channel_id = req.query.get("channel_id")

    guild = bot.guilds[0] if bot.guilds else None
    if not guild:
        return web.json_response({"ok": False, "error": "no guild found"}, status=500)

    target_channels = []
    if channel_id:
        try:
            ch = bot.get_channel(int(channel_id))
            if ch:
                target_channels = [ch]
        except Exception:
            pass
    else:
        for ch in guild.channels or []:
            if hasattr(ch, "history"):
                target_channels.append(ch)

    all_messages = []
    for chan in target_channels:
        try:
            channel_msgs = []
            async for msg in chan.history(limit=limit * 2):
                if str(msg.author.id) == str(user_id):
                    channel_msgs.append({
                        "id": str(msg.id),
                        "content": msg.content[:500],
                        "timestamp": msg.created_at.isoformat(),
                        "channel_id": str(chan.id),
                        "channel_name": chan.name,
                        "jump_url": msg.jump_url,
                    })
                    if len(channel_msgs) >= limit:
                        break
            all_messages.extend(channel_msgs)
        except Exception:
            continue

    all_messages.sort(key=lambda x: x["timestamp"], reverse=True)
    return web.json_response({
        "ok": True,
        "user_id": str(user_id),
        "messages": all_messages[:limit],
        "count": len(all_messages[:limit]),
    })


# ---- Content Request API (Pegas → Dorbian approval workflow) ----

@route("GET", "/admin/content/requests", scopes=["admin:web", "gpose:admin"])
async def list_content_requests(req: web.Request) -> web.Response:
    """
    List content requests, optionally filtered.
    Query params: status, type, limit
    """
    status = req.query.get("status")
    rtype = req.query.get("type")
    try:
        limit = min(100, int(req.query.get("limit", 50)))
    except Exception:
        limit = 50

    try:
        from bigtree.modules.content_requests import list_requests
        results = list_requests(status=status, request_type=rtype, limit=limit)
        return web.json_response({"ok": True, "requests": results, "count": len(results)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


@route("GET", "/admin/content/requests/pending", scopes=["admin:web", "gpose:admin"])
async def pending_content_requests(req: web.Request) -> web.Response:
    """List all pending (awaiting review) content requests."""
    try:
        from bigtree.modules.content_requests import pending_requests
        results = pending_requests()
        return web.json_response({"ok": True, "requests": results, "count": len(results)})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


@route("GET", "/admin/content/requests/{request_id}", scopes=["admin:web", "gpose:admin"])
async def get_content_request(req: web.Request) -> web.Response:
    """Get a single content request by ID."""
    try:
        rid = int(req.match_info.get("request_id", 0))
    except Exception:
        return web.json_response({"ok": False, "error": "invalid ID"}, status=400)

    try:
        from bigtree.modules.content_requests import get_request
        result = get_request(rid)
        if not result:
            return web.json_response({"ok": False, "error": "not found"}, status=404)
        return web.json_response({"ok": True, "request": result})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


@route("POST", "/admin/content/requests", scopes=["admin:web", "gpose:admin"])
async def create_content_request(req: web.Request) -> web.Response:
    """
    Create a new content request (Pegas proposes, status=pending).
    Body: { request_type, title, body, target_channel_id, target_channel_name, metadata }
    """
    try:
        data = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)

    rtype = data.get("request_type", "")
    title = data.get("title", "")
    body = data.get("body", "")
    target_channel_id = data.get("target_channel_id")
    target_channel_name = data.get("target_channel_name", "")
    metadata = data.get("metadata", {})

    if not rtype or not title:
        return web.json_response({"ok": False, "error": "request_type and title required"}, status=400)

    try:
        from bigtree.modules.content_requests import create_request
        result = create_request(
            request_type=rtype,
            title=title,
            body=body,
            target_channel_id=int(target_channel_id) if target_channel_id else None,
            target_channel_name=target_channel_name,
            metadata=metadata,
        )
        return web.json_response(result, status=201 if result.get("ok") else 400)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


@route("PATCH", "/admin/content/requests/{request_id}/status", scopes=["admin:web", "gpose:admin"])
async def update_content_request_status(req: web.Request) -> web.Response:
    """
    Update a request's status (approve/reject/cancel).
    Body: { status, reviewed_by (user_id), review_notes }
    """
    try:
        rid = int(req.match_info.get("request_id", 0))
    except Exception:
        return web.json_response({"ok": False, "error": "invalid ID"}, status=400)

    try:
        data = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)

    status = data.get("status", "")
    reviewed_by = data.get("reviewed_by")
    review_notes = data.get("review_notes", "")

    if not status:
        return web.json_response({"ok": False, "error": "status required"}, status=400)

    try:
        from bigtree.modules.content_requests import update_request_status
        result = update_request_status(
            request_id=rid,
            status=status,
            reviewed_by=int(reviewed_by) if reviewed_by else None,
            review_notes=review_notes,
        )
        return web.json_response(result, status=200 if result.get("ok") else 400)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


@route("POST", "/admin/content/requests/{request_id}/approve", scopes=["admin:web", "gpose:admin"])
async def approve_content_request(req: web.Request) -> web.Response:
    """
    Approve a request for posting.
    Body: { reviewed_by (user_id), review_notes }
    """
    try:
        rid = int(req.match_info.get("request_id", 0))
    except Exception:
        return web.json_response({"ok": False, "error": "invalid ID"}, status=400)

    try:
        data = await req.json()
    except Exception:
        data = {}
    reviewed_by = data.get("reviewed_by")
    notes = data.get("review_notes", "")

    try:
        from bigtree.modules.content_requests import approve_request
        result = approve_request(rid, reviewed_by=int(reviewed_by) if reviewed_by else None, notes=notes)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


@route("POST", "/admin/content/requests/{request_id}/reject", scopes=["admin:web", "gpose:admin"])
async def reject_content_request(req: web.Request) -> web.Response:
    """
    Reject a request.
    Body: { reviewed_by (user_id), review_notes }
    """
    try:
        rid = int(req.match_info.get("request_id", 0))
    except Exception:
        return web.json_response({"ok": False, "error": "invalid ID"}, status=400)

    try:
        data = await req.json()
    except Exception:
        data = {}
    reviewed_by = data.get("reviewed_by")
    notes = data.get("review_notes", "")

    try:
        from bigtree.modules.content_requests import reject_request
        result = reject_request(rid, reviewed_by=int(reviewed_by) if reviewed_by else None, notes=notes)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


@route("POST", "/admin/content/requests/{request_id}/post", scopes=["admin:web", "gpose:admin"])
async def post_content_request(req: web.Request) -> web.Response:
    """
    Post an approved request to its target channel via the bot.
    Body (optional): { force: true } to skip approved check.
    """
    try:
        rid = int(req.match_info.get("request_id", 0))
    except Exception:
        return web.json_response({"ok": False, "error": "invalid ID"}, status=400)

    try:
        from bigtree.modules.content_requests import get_request, mark_posted

        req_data = get_request(rid)
        if not req_data:
            return web.json_response({"ok": False, "error": "request not found"}, status=404)

        status = req_data.get("status", "")
        target_cid = req_data.get("target_channel_id")
        body = req_data.get("body", "")

        if not target_cid:
            return web.json_response({"ok": False, "error": "no target channel configured"}, status=400)

        bot = getattr(bigtree, "bot", None)
        if not bot:
            return web.json_response({"ok": False, "error": "bot not ready"}, status=503)

        chan = bot.get_channel(int(target_cid))
        if not chan:
            return web.json_response({"ok": False, "error": "target channel not found"}, status=404)

        # Send the message
        msg = await chan.send(body)
        mark_posted(rid)

        return web.json_response({
            "ok": True,
            "message": f"Posted to <#{target_cid}>",
            "jump_url": msg.jump_url,
            "message_id": str(msg.id),
        })
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


@route("DELETE", "/admin/content/requests/{request_id}", scopes=["admin:web", "gpose:admin"])
async def delete_content_request(req: web.Request) -> web.Response:
    """Delete a draft or cancelled request."""
    try:
        rid = int(req.match_info.get("request_id", 0))
    except Exception:
        return web.json_response({"ok": False, "error": "invalid ID"}, status=400)

    try:
        from bigtree.modules.content_requests import delete_request
        result = delete_request(rid)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)
